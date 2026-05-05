import os
import time
from datetime import datetime, timedelta, timezone
from atproto import Client
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from supabase import create_client, Client as SupabaseClient

# 1. Securely load API Keys from environment variables
BSKY_HANDLE = os.environ.get("BSKY_HANDLE")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # This MUST be the service_role key

# Initialize Clients
bsky_client = Client()
bsky_client.login(BSKY_HANDLE, BSKY_PASSWORD)
supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)
analyzer = SentimentIntensityAnalyzer()

# 2. Define the target date (Yesterday)
# If this runs at 2 AM on Tuesday, we want to fetch all of Monday's posts
yesterday = datetime.now(timezone.utc) - timedelta(days=1)
target_date_str = yesterday.strftime('%Y-%m-%d')

# Instead of a hardcoded list, fetch the active roster from Supabase
response = supabase.table("tracked_players").select("player_name").execute()

# Extract just the names into a Python list
nfl_players = [row['player_name'] for row in response.data]

print(f"Loaded {len(nfl_players)} players from database. Starting pipeline...")

def process_player(player_name):
    print(f"Processing {player_name} for {target_date_str}...")
    posts_analyzed = 0
    total_sentiment = 0
    cursor = None
    
    while True:
        response = bsky_client.app.bsky.feed.search_posts(params={
            'q': player_name,
            'since': f"{target_date_str}T00:00:00Z", 
            'until': f"{target_date_str}T23:59:59Z",
            'limit': 100,
            'cursor': cursor
        })
        
        for post in response.posts:
            # Calculate sentiment for each post
            score = analyzer.polarity_scores(post.record.text)
            total_sentiment += score['compound']
            posts_analyzed += 1
            
        cursor = response.cursor
        
        # Rate Limit Circuit Breaker: If we pull 10,000 posts, stop and move to next player
        if not cursor or posts_analyzed >= 10000:
            break
            
        # Optional: Add a tiny pause to avoid hammering the Bluesky API
        time.sleep(0.5) 
        
    # 4. Calculate final average and push to Supabase
    if posts_analyzed > 0:
        average_sentiment = total_sentiment / posts_analyzed
        
        # Structure the data exactly as your Supabase table expects it
        data_to_insert = {
            "date": target_date_str,
            "player_name": player_name,
            "average_sentiment": round(average_sentiment, 4),
            "total_posts": posts_analyzed
        }
        
        # Insert the row into Supabase
        supabase.table("daily_sentiment").upsert(data_to_insert).execute()
        print(f"Success: {player_name} | Sentiment: {average_sentiment:.3f} | Posts: {posts_analyzed}")
    else:
        print(f"No posts found for {player_name}.")

# 5. Run the loop
if __name__ == "__main__":
    for player in nfl_players:
        process_player(player)
        # Sleep for 5 seconds between players to respect Bluesky rate limits
        time.sleep(5) 
    
    print("Nightly data pipeline complete.")
