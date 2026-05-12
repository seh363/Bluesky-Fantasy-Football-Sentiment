import os
import time
from datetime import datetime, timedelta, timezone
from dateutil import parser
from atproto import Client, Request
from atproto_client.exceptions import InvokeTimeoutError
from httpx import Timeout
from supabase import create_client

# 1. Import VADER instead of TextBlob
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

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

# Initialize Supabase, Bluesky, and VADER
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

custom_request = Request(timeout=Timeout(timeout=30.0))
bsky_client = Client(request=custom_request)
bsky_client.login(BSKY_HANDLE, BSKY_PASSWORD)

# 2. Initialize the VADER analyzer
analyzer = SentimentIntensityAnalyzer()

def get_player_list():
    response = supabase.table("tracked_players").select("player_name").execute()
    return [p['player_name'] for p in response.data]

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
            text_lower = text.lower()
            
            if player_name.lower() not in text_lower:
                continue

            post_time = parser.isoparse(post.record.created_at)
            if post_time.tzinfo is None:
                post_time = post_time.replace(tzinfo=timezone.utc)
            
            if not (start_of_yesterday <= post_time <= end_of_yesterday):
                continue

            # --- 3. NEW VADER SENTIMENT LOGIC ---
            # VADER returns a dictionary. The 'compound' score is the metric 
            # normalized between -1.0 (most extreme negative) and +1.0 (most extreme positive).
            sentiment_dict = analyzer.polarity_scores(text)
            score = sentiment_dict['compound']
            
            if score > max_pos_score:
                max_pos_score = score
                max_pos_text = text
            
            if score < min_neg_score:
                min_neg_score = score
                min_neg_text = text

            total_sentiment += score
            count += 1

        if count == 0:
            print(f"🕒 No relevant full-name mentions specifically for yesterday ({yesterday}).")
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
        print(f"✅ Saved {player_name} for {yesterday} ({count} verified posts).")

    except InvokeTimeoutError:
        print(f"🕒 Timeout: Bluesky search took too long for {player_name}.")
    except Exception as e:
        print(f"❌ Error processing {player_name}: {e}")

if __name__ == "__main__":
    players = get_player_list()
    print(f"🚀 Starting daily worker for {len(players)} players...")
    
    for player in players:
        process_player(player)
        time.sleep(1) 
        
    print("🏁 Worker finished successfully.")
