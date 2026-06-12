import os
import time
import logging
from datetime import datetime, timedelta, timezone
from dateutil import parser
from atproto import Client, Request
from atproto_client.exceptions import InvokeTimeoutError
from httpx import Timeout
from supabase import create_client
from transformers import pipeline

# --- Logging setup ---
# Suppress architectural warnings from transformers
logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)

# All worker output goes to both stdout and a dated log file
target_date_str = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(f"worker_{target_date_str}.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# --- Configuration ---
BSKY_HANDLE = os.environ.get("BSKY_HANDLE")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not all([BSKY_HANDLE, BSKY_PASSWORD, SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError("❌ Missing environment variables")

# Initialize Supabase and Bluesky
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
custom_request = Request(timeout=Timeout(timeout=30.0))
bsky_client = Client(request=custom_request)
bsky_client.login(BSKY_HANDLE, BSKY_PASSWORD)

log.info("⏳ Loading RoBERTa model...")
sentiment_task = pipeline(
    "sentiment-analysis",
    model="cardiffnlp/twitter-roberta-base-sentiment-latest",
    tokenizer="cardiffnlp/twitter-roberta-base-sentiment-latest",
    device=-1,
    truncation=True,   # let the tokenizer handle length, not a character slice
    max_length=512
)

MAX_RETRIES = 3
MAX_PAGES = 50        # hard ceiling: 50 pages × 100 posts = 5,000 posts per player
INFERENCE_BATCH = 64  # chunk size for batch inference to avoid OOM on large post counts

# ---------------------------------------------------------------------------
# Noise keywords — posts containing any of these are excluded from sentiment.
# Organised into groups for easy maintenance.
# ---------------------------------------------------------------------------
NOISE_KEYWORDS = [
    # Merchandise / collectibles
    'jersey', 'uniform', 'kit', 'signed', 'autograph',
    'trading card', 'panini', 'rookie card', 'patch', 'helmet',
    'prizm', 'optic', 'topps', 'bowman', 'donruss', 'mosaic',

    # Commerce / spam
    'buy', 'sell', 'ebay', 'amazon', 'shop', 'store', 'discount',
    'coupon', 'promo', 'giveaway', 'contest', 'sweepstakes', 'free shipping',

    # Ticketing / events
    'eventbrite', 'tickets', 'stubhub', 'seatgeek', 'vivid seats',

    # Media products
    'audiobook', 'audio book', 'kindle', 'podcast', 'subscribe', 'patreon',

    # Political — player names occasionally collide with political figures
    # or posts use player names as metaphors in political arguments.
    'democrat', 'republican', 'gop', 'maga', 'trump', 'biden', 'harris',
    'pelosi', 'congress', 'senate', 'election', 'ballot', 'vote', 'voting',
    'liberal', 'conservative', 'left wing', 'right wing', 'political',
    'legislation', 'policy', 'white house', 'president', 'governor',
    'immigration', 'abortion', 'gun control', 'second amendment',
    'woke', 'pronouns', 'cancel culture', 'deep state',
]


def get_player_list():
    response = supabase.table("tracked_players").select("player_name").execute()
    return [p['player_name'] for p in response.data]


def map_roberta_to_scale(result):
    label = str(result['label']).lower().strip()
    score = float(result['score'])
    if label in ['positive', 'label_2']:
        return score
    elif label in ['negative', 'label_0']:
        return -score
    else:
        return 0.0


def fetch_page(search_query, cursor):
    """Fetch a single page of posts with exponential backoff retry.
    Re-authenticates automatically if the session has expired."""
    for attempt in range(MAX_RETRIES):
        try:
            response = bsky_client.app.bsky.feed.search_posts(
                params={'q': search_query, 'limit': 100, 'sort': 'latest', 'cursor': cursor}
            )
            return response
        except InvokeTimeoutError:
            if attempt < MAX_RETRIES - 1:
                wait = 2 ** attempt
                log.warning(f"  ⚠️ Timeout on attempt {attempt + 1}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                log.error(f"  🕒 All {MAX_RETRIES} retries exhausted, skipping page.")
                return None
        except Exception as e:
            err = str(e).lower()
            if "expired" in err or "auth" in err or "unauthorized" in err:
                log.warning("  🔑 Session expired, re-authenticating...")
                try:
                    bsky_client.login(BSKY_HANDLE, BSKY_PASSWORD)
                    # Retry immediately after re-auth
                    continue
                except Exception as re_auth_err:
                    log.error(f"  ❌ Re-authentication failed: {re_auth_err}")
                    return None
            log.error(f"  ❌ Unexpected error fetching page: {e}")
            return None


def run_inference_in_batches(texts):
    """Run sentiment inference in fixed-size chunks to avoid OOM on large post counts."""
    results = []
    for i in range(0, len(texts), INFERENCE_BATCH):
        chunk = texts[i:i + INFERENCE_BATCH]
        results.extend(sentiment_task(chunk))
    return results


def process_player(player_name, target_date):
    """Collect, filter, and score all posts for one player on target_date.
    Returns True on success, False on failure."""
    log.info(f"🔍 Processing: {player_name} for {target_date}")

    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day   = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    search_query  = f'"{player_name}"'
    valid_posts   = []
    filtered_count = 0
    seen_uris     = set()   # deduplicate across pages
    cursor        = None

    try:
        # ── 1. Paginated post collection ────────────────────────────────────────
        for page_num in range(MAX_PAGES):
            response = fetch_page(search_query, cursor)
            if response is None or not response.posts:
                break

            oldest_post_time = None

            for post in response.posts:
                # Deduplicate — cursor drift can return the same post on two pages
                if post.uri in seen_uris:
                    continue
                seen_uris.add(post.uri)

                text       = post.record.text
                clean_text = text.replace('\n', ' ')

                # Must explicitly mention the player by name
                if player_name.lower() not in clean_text.lower():
                    continue

                post_time = parser.isoparse(post.record.created_at)
                if post_time.tzinfo is None:
                    post_time = post_time.replace(tzinfo=timezone.utc)

                # Track oldest post on this page.
                # We intentionally do NOT break on the first old post — Bluesky's
                # "latest" sort is not perfectly guaranteed, so late-indexed or
                # reposted content can appear out of order.
                if oldest_post_time is None or post_time < oldest_post_time:
                    oldest_post_time = post_time

                # Skip posts outside target window
                if not (start_of_day <= post_time <= end_of_day):
                    continue

                # Noise filter
                lower_text = clean_text.lower()
                if any(kw in lower_text for kw in NOISE_KEYWORDS):
                    filtered_count += 1
                    continue

                # Pass raw text — tokenizer handles truncation via truncation=True
                valid_posts.append({"raw": text, "clean": clean_text})

            # Stop paginating once the oldest post on this page predates our window
            if oldest_post_time and oldest_post_time < start_of_day:
                log.info(f"  ↩️ Reached posts older than {target_date} on page {page_num + 1}, stopping.")
                break

            if not response.cursor:
                break

            cursor = response.cursor

        if not valid_posts:
            log.info(f"  🕒 No valid posts for {player_name} on {target_date}. "
                     f"(Filtered out: {filtered_count})")
            return True  # not an error — just a quiet day

        # ── 2. Batch inference ──────────────────────────────────────────────────
        texts_to_analyze = [p["clean"] for p in valid_posts]
        try:
            model_results = run_inference_in_batches(texts_to_analyze)
        except Exception as e:
            log.error(f"  ⚠️ Model error during batch inference: {e}")
            return False

        total_sentiment = 0.0
        max_pos_score   = -1.1
        max_pos_text    = ""
        min_neg_score   =  1.1
        min_neg_text    = ""

        for post_data, result in zip(valid_posts, model_results):
            score = map_roberta_to_scale(result)
            text  = post_data["raw"]

            if score > max_pos_score:
                max_pos_score = score
                max_pos_text  = text
            if score < min_neg_score:
                min_neg_score = score
                min_neg_text  = text

            total_sentiment += score

        count         = len(valid_posts)
        avg_sentiment = total_sentiment / count

        data = {
            "player_name":       player_name,
            "average_sentiment": round(avg_sentiment, 4),
            "total_posts":       count,
            "date":              target_date.isoformat(),
            "top_pos_text":      max_pos_text,
            "top_pos_score":     round(max_pos_score, 4),
            "top_neg_text":      min_neg_text,
            "top_neg_score":     round(min_neg_score, 4),
        }

        # ── 3. Persist to Supabase ──────────────────────────────────────────────
        try:
            supabase.table("daily_sentiment").upsert(data).execute()
            log.info(f"  ✅ Saved {player_name} | Valid: {count} | "
                     f"Filtered: {filtered_count} | Score: {avg_sentiment:.4f}")
        except Exception as e:
            log.error(f"  ❌ Supabase write failed for {player_name}: {e}")
            return False

        return True

    except Exception as e:
        log.error(f"  ❌ Error processing {player_name}: {e}")
        return False


if __name__ == "__main__":
    # Compute target_date once so all players use the same UTC day
    # even if the run crosses midnight.
    target_date = datetime.now(timezone.utc).date() - timedelta(days=1)

    players = get_player_list()
    log.info(f"🚀 Starting RoBERTa-powered daily worker for {len(players)} players "
             f"(target date: {target_date})...")

    failed_players = []

    for player in players:
        success = process_player(player, target_date)
        if not success:
            failed_players.append(player)
        time.sleep(3)  # pause between players to reduce rate-limiting risk

    if failed_players:
        log.warning(f"⚠️ {len(failed_players)} player(s) failed: {', '.join(failed_players)}")
    else:
        log.info("🏁 All players processed successfully.")
