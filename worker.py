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

# Suppress architectural warnings from transformers
logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)

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

print("⏳ Loading RoBERTa model...")
sentiment_task = pipeline(
    "sentiment-analysis",
    model="cardiffnlp/twitter-roberta-base-sentiment-latest",
    tokenizer="cardiffnlp/twitter-roberta-base-sentiment-latest",
    device=-1
)

MAX_RETRIES = 3
MAX_PAGES = 50  # hard ceiling: 50 pages × 100 posts = 5,000 posts per player

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
    """Fetch a single page of posts with exponential backoff retry."""
    for attempt in range(MAX_RETRIES):
        try:
            response = bsky_client.app.bsky.feed.search_posts(
                params={'q': search_query, 'limit': 100, 'sort': 'latest', 'cursor': cursor}
            )
            return response
        except InvokeTimeoutError:
            if attempt < MAX_RETRIES - 1:
                wait = 2 ** attempt
                print(f"  ⚠️ Timeout on attempt {attempt + 1}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  🕒 All {MAX_RETRIES} retries exhausted, skipping page.")
                return None
        except Exception as e:
            print(f"  ❌ Unexpected error fetching page: {e}")
            return None

def process_player(player_name, target_date):
    print(f"🔍 Processing: {player_name} for {target_date}")

    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    search_query = f'"{player_name}"'
    valid_posts = []
    filtered_count = 0
    cursor = None

    noise_keywords = [
        'jersey', 'uniform', 'kit', 'signed', 'autograph',
        'trading card', 'panini', 'rookie card', 'patch', 'helmet',
        'buy', 'sell', 'ebay', 'prizm', 'optic',
        'eventbrite', 'tickets', 'stubhub',
        'audiobook', 'audio book', 'kindle',
        'giveaway', 'contest', 'promo'
    ]

    try:
        for page_num in range(MAX_PAGES):
            response = fetch_page(search_query, cursor)
            if response is None or not response.posts:
                break

            oldest_post_time = None

            for post in response.posts:
                text = post.record.text
                clean_text = text.replace('\n', ' ')

                # Must mention the player name
                if player_name.lower() not in clean_text.lower():
                    continue

                post_time = parser.isoparse(post.record.created_at)
                if post_time.tzinfo is None:
                    post_time = post_time.replace(tzinfo=timezone.utc)

                # Track the oldest post on this page to decide whether to paginate further.
                # We process all posts on the page first (don't break early) because Bluesky's
                # "latest" sort is not perfectly guaranteed — late-indexed or reposted content
                # can appear out of order, so breaking on the first old post risks missing
                # valid yesterday posts later on the same page.
                if oldest_post_time is None or post_time < oldest_post_time:
                    oldest_post_time = post_time

                # Skip posts outside our target window
                if not (start_of_day <= post_time <= end_of_day):
                    continue

                # Noise filter
                if any(keyword in clean_text.lower() for keyword in noise_keywords):
                    filtered_count += 1
                    continue

                valid_posts.append({"raw": text, "clean": clean_text[:512]})

            # Only paginate further if the oldest post on this page is still within
            # or after our target date. Once we're seeing posts older than target_date,
            # there's nothing useful left to fetch.
            if oldest_post_time and oldest_post_time < start_of_day:
                print(f"  ↩️ Reached posts older than {target_date} on page {page_num + 1}, stopping.")
                break

            if not response.cursor:
                break

            cursor = response.cursor

        if not valid_posts:
            print(f"  🕒 No valid posts for {player_name} on {target_date}. "
                  f"(Filtered out: {filtered_count})")
            return

        # --- Batch Inference ---
        texts_to_analyze = [p["clean"] for p in valid_posts]
        try:
            model_results = sentiment_task(texts_to_analyze)
        except Exception as e:
            print(f"  ⚠️ Model error during batch inference: {e}")
            return

        total_sentiment = 0
        max_pos_score = -1.1
        max_pos_text = ""
        min_neg_score = 1.1
        min_neg_text = ""

        for post_data, result in zip(valid_posts, model_results):
            score = map_roberta_to_scale(result)
            text = post_data["raw"]

            if score > max_pos_score:
                max_pos_score = score
                max_pos_text = text

            if score < min_neg_score:
                min_neg_score = score
                min_neg_text = text

            total_sentiment += score

        count = len(valid_posts)
        avg_sentiment = total_sentiment / count

        data = {
            "player_name": player_name,
            "average_sentiment": round(avg_sentiment, 4),
            "total_posts": count,
            "date": target_date.isoformat(),
            "top_pos_text": max_pos_text,
            "top_pos_score": round(max_pos_score, 4),
            "top_neg_text": min_neg_text,
            "top_neg_score": round(min_neg_score, 4)
        }

        supabase.table("daily_sentiment").upsert(data).execute()
        print(f"  ✅ Saved {player_name} | Valid: {count} | Filtered: {filtered_count} | "
              f"Score: {avg_sentiment:.4f}")

    except Exception as e:
        print(f"  ❌ Error processing {player_name}: {e}")


if __name__ == "__main__":
    # Compute target_date once so all players are measured against the same day,
    # even if the run crosses midnight.
    target_date = datetime.now(timezone.utc).date() - timedelta(days=1)

    players = get_player_list()
    print(f"🚀 Starting RoBERTa-powered daily worker for {len(players)} players "
          f"(target date: {target_date})...")

    for player in players:
        process_player(player, target_date)
        time.sleep(3)  # increased from 1s to reduce risk of rate limiting

    print("🏁 Worker finished successfully.")
