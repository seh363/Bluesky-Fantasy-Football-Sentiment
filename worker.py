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
    """Searches Bluesky, filters for last 24h, and saves sentiment."""
    print(f"🔍 Processing: {player_name}")
    
    try:
        response = bsky_client.app.bsky.feed.search_posts(params={
            'q': player_name,
            'limit': 100
        })
        
        posts = response.posts
        if not posts:
            print(f"⚠️ No posts found for {player_name}")
            return

        total_sentiment = 0
        count = 0
        
        # Define our 24-hour window
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=1)

        for post in posts:
            # parser.isoparse handles nanoseconds and varied offsets automatically
            post_time = parser.isoparse(post.record.created_at)
            
            # Ensure the post_time is timezone-aware for comparison
            if post_time.tzinfo is None:
                post_time = post_time.replace(tzinfo=timezone.utc)

            # Filter: Only count posts from the last 24 hours
            if post_time < cutoff_time:
                continue

            text = post.record.text
            analysis = TextBlob(text)
            total_sentiment += analysis.sentiment.polarity
            count += 1

        if count == 0:
            print(f"🕒 No recent posts (last 24h) for {player_name}. Skipping save.")
            return

        avg_sentiment = total_sentiment / count
        
        data = {
            "player_name": player_name,
            "average_sentiment": round(avg_sentiment, 4),
            "total_posts": count,
            "date": datetime.now().date().isoformat()
        }

        supabase.table("daily_sentiment").upsert(data).execute()
        print(f"✅ Saved {player_name}: {avg_sentiment:.2f} ({count} posts)")

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
