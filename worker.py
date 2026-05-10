import os
import time
from datetime import datetime, timedelta, timezone
from dateutil import parser  # Library for robust date parsing
from atproto import Client, Request
from atproto_client.exceptions import InvokeTimeoutError
from httpx import Timeout
from supabase import create_client
from textblob import TextBlob

# --- Configuration ---
BSKY_HANDLE = os.environ.get("BSKY_HANDLE")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Safety Check
if not all([BSKY_HANDLE, BSKY_PASSWORD, SUPABASE_URL, SUPABASE_KEY]):
    missing = [name for name, val in {
        "BSKY_HANDLE": BSKY_HANDLE,
        "BSKY_PASSWORD": BSKY_PASSWORD,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY
    }.items() if not val]
    raise ValueError(f"❌ Missing environment variables: {', '.join(missing)}")

# Initialize Supabase
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Bluesky
custom_request = Request(timeout=Timeout(timeout=30.0))
bsky_client = Client(request=custom_request)
bsky_client.login(BSKY_HANDLE, BSKY_PASSWORD)

def get_player_list():
    """Fetches the players from the 'tracked_players' table."""
    response = supabase.table("tracked_players").select("player_name").execute()
    return [p['player_name'] for p in response.data]

def process_player(player_name):
    print(f"🔍 Processing: {player_name}")
    
    # 1. Define the "Fixed" Previous Day Window (Yesterday 00:00:00 to 23:59:59 UTC)
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    
    start_of_yesterday = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_yesterday = datetime.combine(yesterday, datetime.max.time()).replace(tzinfo=timezone.utc)

    # Search for exact phrase match
    search_query = f'"{player_name}"'

    try:
        # Grabbing 100 posts (you can increase this to 200 if volume drops too much)
        response = bsky_client.app.bsky.feed.search_posts(params={'q': search_query, 'limit': 100})
        posts = response.posts
        if not posts:
            print(f"🕒 No posts found for {player_name}.")
            return

        total_sentiment = 0
        count = 0

        # Initialize trackers for best/worst posts
        max_pos_score = -1.1 # Lower than any possible score
        max_pos_text = ""
        min_neg_score = 1.1  # Higher than any possible score
        min_neg_text = ""

        for post in posts:
            text = post.record.text
            text_lower = text.lower()
            
            # --- FILTER 1: Explicit Full-Name Match ---
            if player_name.lower() not in text_lower:
                continue

            # --- FILTER 2: Strict Calendar Day (Yesterday Only) ---
            post_time = parser.isoparse(post.record.created_at)
            if post_time.tzinfo is None:
                post_time = post_time.replace(tzinfo=timezone.utc)
            
            if not (start_of_yesterday <= post_time <= end_of_yesterday):
                continue

            # --- SENTIMENT ANALYSIS ---
            analysis = TextBlob(text)
            score = analysis.sentiment.polarity
            
            # Track the most positive post
            if score > max_pos_score:
                max_pos_score = score
                max_pos_text = text
            
            # Track the most negative post
            if score < min_neg_score:
                min_neg_score = score
                min_neg_text = text

            total_sentiment += score
            count += 1

        if count == 0:
            print(f"🕒 No relevant full-name mentions specifically for yesterday ({yesterday}).")
            return

        avg_sentiment = total_sentiment / count
        
        # Prepare the data dictionary
        data = {
            "player_name": player_name,
            "average_sentiment": round(avg_sentiment, 4),
            "total_posts": count,
            "date": yesterday.isoformat(), # Assign strictly to yesterday's date
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
