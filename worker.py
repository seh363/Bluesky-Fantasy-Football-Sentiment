import os
import time
from datetime import datetime, timedelta, timezone
from dateutil import parser
from atproto import Client, Request
from atproto_client.exceptions import InvokeTimeoutError
from httpx import Timeout
from supabase import create_client

# 1. Import Transformers for the RoBERTa model
from transformers import pipeline

# --- Configuration ---
BSKY_HANDLE = os.environ.get("BSKY_HANDLE")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not all([BSKY_HANDLE, BSKY_PASSWORD, SUPABASE_URL, SUPABASE_KEY]):
    missing = [name for name, val in {
        "BSKY_HANDLE": BSKY_HANDLE,
        "BSKY_PASSWORD": BSKY_PASSWORD,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY
    }.items() if not val]
    raise ValueError(f"❌ Missing environment variables: {', '.join(missing)}")

# Initialize Supabase and Bluesky
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

custom_request = Request(timeout=Timeout(timeout=30.0))
bsky_client = Client(request=custom_request)
bsky_client.login(BSKY_HANDLE, BSKY_PASSWORD)

# 2. Initialize the RoBERTa Sentiment Pipeline
# This model understands social media nuance (emojis, sarcasm, and slang)
print("⏳ Loading RoBERTa model (this may take a moment on first run)...")
sentiment_task = pipeline(
    "sentiment-analysis", 
    model="cardiffnlp/twitter-roberta-base-sentiment-latest",
    tokenizer="cardiffnlp/twitter-roberta-base-sentiment-latest",
    device=-1 # Use -1 for CPU; change to 0 if your environment has a GPU
)

def get_player_list():
    response = supabase.table("tracked_players").select("player_name").execute()
    return [p['player_name'] for p in response.data]

def map_roberta_to_scale(result):
    """
    Converts RoBERTa label/score to the dashboard's -1.0 to 1.0 scale.
    """
    label = result['label']
    score = result['score']
    
    if label == 'positive':
        return score
    elif label == 'negative':
        return -score
    else:
        # Neutral posts stay at 0.0
        return 0.0

def process_player(player_name):
    print(f"🔍 Processing: {player_name}")
    
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    
    start_of_yesterday = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_yesterday = datetime.combine(yesterday, datetime.max.time()).replace(tzinfo=timezone.utc)

    search_query = f'"{player_name}"'

    try:
        response = bsky_client.app.bsky.feed.search_posts(params={'q': search_query, 'limit': 100})
        posts = response.posts
        if not posts:
            print(f"🕒 No posts found for {player_name}.")
            return

        total_sentiment = 0
        count = 0

        max_pos_score = -1.1 
        max_pos_text = ""
        min_neg_score = 1.1  
        min_neg_text = ""

        for post in posts:
            text = post.record.text
            # Basic cleaning for the model
            clean_text = text.replace('\n', ' ')
            
            if player_name.lower() not in clean_text.lower():
                continue

            post_time = parser.isoparse(post.record.created_at)
            if post_time.tzinfo is None:
                post_time = post_time.replace(tzinfo=timezone.utc)
            
            if not (start_of_yesterday <= post_time <= end_of_yesterday):
                continue

            # --- 3. RoBERTa SENTIMENT LOGIC ---
            try:
                # Truncating to 512 characters as that's the standard model limit
                model_result = sentiment_task(clean_text[:512])[0]
                score = map_roberta_to_scale(model_result)
                
                if score > max_pos_score:
                    max_pos_score = score
                    max_pos_text = text
                
                if score < min_neg_score:
                    min_neg_score = score
                    min_neg_text = text

                total_sentiment += score
                count += 1
            except Exception as e:
                print(f"⚠️ Model error on post: {e}")
                continue

        if count == 0:
            print(f"🕒 No verified posts for {player_name} on {yesterday}.")
            return

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
