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

def get_player_list():
    response = supabase.table("tracked_players").select("player_name").execute()
    return [p['player_name'] for p in response.data]

def map_roberta_to_scale(result):
    label = str(result['label']).lower().strip()
    score = float(result['score'])
    if label in ['positive', 'label_2']: return score
    elif label in ['negative', 'label_0']: return -score
    else: return 0.0

def process_player(player_name):
    print(f"🔍 Processing: {player_name}")
    
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    
    start_of_yesterday = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_yesterday = datetime.combine(yesterday, datetime.max.time()).replace(tzinfo=timezone.utc)

    search_query = f'"{player_name}"'
    valid_posts = []
    cursor = None

    try:
        # --- 1. Cursor Pagination ---
        # Loop through up to 5 pages (500 posts) to ensure we reach yesterday's data
        for _ in range(5):
            response = bsky_client.app.bsky.feed.search_posts(
                params={'q': search_query, 'limit': 100, 'sort': 'latest', 'cursor': cursor}
            )
            posts = response.posts
            if not posts:
                break
            
            reached_older_posts = False

            for post in posts:
                text = post.record.text
                clean_text = text.replace('\n', ' ')
                
                if player_name.lower() not in clean_text.lower():
                    continue

                post_time = parser.isoparse(post.record.created_at)
                if post_time.tzinfo is None:
                    post_time = post_time.replace(tzinfo=timezone.utc)
                
                # If we hit posts older than yesterday, stop paginating entirely
                if post_time < start_of_yesterday:
                    reached_older_posts = True
                    break

                if not (start_of_yesterday <= post_time <= end_of_yesterday):
                    continue

                # Noise Filter
                noise_keywords = [
                    'jersey', 'uniform', 'kit', 'signed', 'autograph', 
                    'trading card', 'panini', 'rookie card', 'patch', 'helmet',
                    'buy', 'sell', 'ebay', 'prizm', 'optic', 
                    'eventbrite', 'tickets', 'stubhub',
                    'audiobook', 'audio book', 'kindle',
                    'giveaway', 'contest', 'promo'
                ]
                if any(keyword in clean_text.lower() for keyword in noise_keywords):
                    continue
                
                # Append valid posts to list for Batch Inference
                valid_posts.append({"raw": text, "clean": clean_text[:512]})
            
            # Break the page loop if we've traveled far enough back in time
            if reached_older_posts or not response.cursor:
                break
                
            cursor = response.cursor

        if not valid_posts:
            print(f"🕒 No verified scouting posts for {player_name} on {yesterday}.")
            return

        # --- 2. Batch Inference ---
        texts_to_analyze = [p["clean"] for p in valid_posts]
        try:
            # Send the entire list of strings to PyTorch at once
            model_results = sentiment_task(texts_to_analyze)
        except Exception as e:
            print(f"⚠️ Model error during batch inference: {e}")
            return

        total_sentiment = 0
        max_pos_score = -1.1 
        max_pos_text = ""
        min_neg_score = 1.1  
        min_neg_text = ""

        # Map results back to the original text
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
            "date": yesterday.isoformat(), 
            "top_pos_text": max_pos_text,
            "top_pos_score": round(max_pos_score, 4),
            "top_neg_text": min_neg_text,
            "top_neg_score": round(min_neg_score, 4)
        }

        supabase.table("daily_sentiment").upsert(data).execute()
        print(f"✅ Saved {player_name} ({count} posts). Score: {avg_sentiment:.4f}")

    except InvokeTimeoutError:
        print(f"🕒 Timeout: Bluesky search took too long for {player_name}.")
    except Exception as e:
        print(f"❌ Error processing {player_name}: {e}")

if __name__ == "__main__":
    players = get_player_list()
    print(f"🚀 Starting RoBERTa-powered daily worker for {len(players)} players...")
    
    for player in players:
        process_player(player)
        time.sleep(1) 
        
    print("🏁 Worker finished successfully.")
