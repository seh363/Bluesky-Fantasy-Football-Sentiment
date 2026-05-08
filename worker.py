import os
import time
from datetime import datetime, timedelta
from atproto import Client
from atproto_client.exceptions import InvokeTimeoutError
from supabase import create_client
from textblob import TextBlob

# --- Configuration ---
BSKY_HANDLE = os.environ.get("BSKY_HANDLE")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")

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
        # Search for posts from the last 24 hours
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
            # TextBlob sentiment is -1.0 to 1.0
            total_sentiment += analysis.sentiment.polarity
            count += 1

        avg_sentiment = total_sentiment / count
        
        # Prepare data for Supabase
        data = {
            "player_name": player_name,
            "average_sentiment": round(avg_sentiment, 4),
            "total_posts": count,
            "date": datetime.now().date().isoformat()
        }

        # Upsert data (Update if player+date exists, else Insert)
        supabase.table("daily_sentiment").upsert(data).execute()
        print(f"✅ Saved {player_name}: {avg_sentiment:.2f} ({count} posts)")

    except InvokeTimeoutError:
        print(f"🕒 Timeout: Bluesky API took too long for {player_name}. Skipping...")
    except Exception as e:
        print(f"❌ Error processing {player_name}: {e}")

if __name__ == "__main__":
    players = get_player_list()
    print(f"🚀 Starting daily worker for {len(players)} players...")
    
    for player in players:
        process_player(player)
        # 1-second delay to avoid rate-limiting and API fatigue
        time.sleep(1) 
        
    print("🏁 Worker finished successfully.")
