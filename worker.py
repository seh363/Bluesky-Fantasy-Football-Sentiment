import os
import time
from datetime import datetime, timedelta, timezone
from dateutil import parser  # New library for robust date parsing
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
    try:
        response = bsky_client.app.bsky.feed.search_posts(params={'q': player_name, 'limit': 100})
        posts = response.posts
        if not posts: return

        total_sentiment = 0
        count = 0
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=1)

        # Initialize trackers for best/worst posts
        max_pos_score = -1.1 # Lower than any possible score
        max_pos_text = ""
        min_neg_score = 1.1  # Higher than any possible score
        min_neg_text = ""

        for post in posts:
            # ... (keep your existing timestamp cleaning and cutoff logic here) ...
            
            text = post.record.text
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

        if count == 0: return

        avg_sentiment = total_sentiment / count
        
        # Add the featured posts to your data dictionary
        data = {
            "player_name": player_name,
            "average_sentiment": round(avg_sentiment, 4),
            "total_posts": count,
            "date": datetime.now().date().isoformat(),
            "top_pos_text": max_pos_text,
            "top_pos_score": round(max_pos_score, 4),
            "top_neg_text": min_neg_text,
            "top_neg_score": round(min_neg_score, 4)
        }

        supabase.table("daily_sentiment").upsert(data).execute()
        print(f"✅ Saved {player_name} with featured posts.")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    players = get_player_list()
    print(f"🚀 Starting daily worker for {len(players)} players...")
    
    for player in players:
        process_player(player)
        time.sleep(1) 
        
    print("🏁 Worker finished successfully.")
