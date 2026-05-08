import os
import time
from datetime import datetime
from atproto import Client
from atproto_client.exceptions import InvokeTimeoutError
from supabase import create_client
from textblob import TextBlob

# --- Configuration ---
BSKY_HANDLE = os.environ.get("BSKY_HANDLE")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # Updated to match your GitHub Secret

# Safety Check: Ensure all environment variables are present
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

# Initialize Bluesky with an increased timeout (30 seconds)
bsky_client = Client(request_timeout=30.0)
bsky_client.login(BSKY_HANDLE, BSKY_PASSWORD)

def get_player_list():
    """Fetches the list of players to track from Supabase."""
    response = supabase.table("players").select("name").execute()
    return [p['name'] for p in response.data]

def process_player(player_name):
    """Searches Bluesky for a player, calculates sentiment, and saves to Supabase."""
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

        for post in posts:
            text = post.record.text
            analysis = TextBlob(text)
            total_sentiment += analysis.sentiment.polarity
            count += 1

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
        print(f"🕒 Timeout for {player_name}. Skipping...")
    except Exception as e:
        print(f"❌ Error processing {player_name}: {e}")

if __name__ == "__main__":
    players = get_player_list()
    print(f"🚀 Starting daily worker for {len(players)} players...")
    
    for player in players:
        process_player(player)
        time.sleep(1) 
        
    print("🏁 Worker finished successfully.")
