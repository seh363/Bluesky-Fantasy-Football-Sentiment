import streamlit as st
import plotly.express as px
import pandas as pd
import os # <--- NEW: Import the OS library
from supabase import create_client, Client

# --- 1. Database Connection ---
@st.cache_resource
def init_connection():
    # Try to get keys from Render's Environment Variables first
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")

    # If they are blank (meaning you are running it locally on your laptop), fallback to st.secrets
    if not url or not key:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_ANON_KEY"]

    return create_client(url, key)

supabase = init_connection()

# ... (the rest of your app.py code stays exactly the same) ...

# --- 2. Data Fetching ---
# st.cache_data remembers the query results so it doesn't spam your database on every click
@st.cache_data(ttl=3600) # Cache clears every hour
def load_data(player):
    # Query Supabase: Select all rows where player_name matches
    response = supabase.table("daily_sentiment").select("*").eq("player_name", player).execute()
    
    df = pd.DataFrame(response.data)
    if not df.empty:
        # Ensure dates are formatted correctly and sorted chronologically
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.sort_values(by='date')
    return df

# --- 3. UI & Dashboard ---
st.title("NFL Player Sentiment Analyzer")
st.write("Track public sentiment over time based on Bluesky posts.")

# User Input
player_name = st.text_input("Enter Player Name", value="Jahan Dotson")

if st.button("Analyze Sentiment"):
    with st.spinner("Loading data from database..."):
        
        # 1. Fetch from Supabase
        df = load_data(player_name)
        
        if df.empty:
            st.warning(f"No data available for {player_name}. (They may not be in the nightly tracking list yet).")
        else:
            # Calculate day-over-day changes
            df['sentiment_change'] = df['average_sentiment'].diff()
            
            # 2. Graph the Results
            fig = px.line(df, x='date', y='average_sentiment', 
                          title=f"Sentiment Over Time: {player_name}",
                          markers=True)
            
            fig.add_hline(y=0, line_dash="dash", line_color="red")
            fig.update_layout(yaxis_title="Average Sentiment Score (-1 to 1)", xaxis_title="Date")
            
            st.plotly_chart(fig, use_container_width=True)
            
            # 3. Display the Biggest Shifts
            st.subheader("Biggest Daily Sentiment Shifts")
            shifts_df = df.dropna(subset=['sentiment_change']).copy()
            shifts_df['average_sentiment'] = shifts_df['average_sentiment'].round(3)
            shifts_df['sentiment_change'] = shifts_df['sentiment_change'].round(3)
            
            col_inc, col_dec = st.columns(2)
            with col_inc:
                st.write("**📈 Top Increases**")
                top_increases = shifts_df.sort_values(by='sentiment_change', ascending=False).head(3)
                st.dataframe(top_increases[['date', 'average_sentiment', 'sentiment_change']], hide_index=True)
                
            with col_dec:
                st.write("**📉 Top Decreases**")
                top_decreases = shifts_df.sort_values(by='sentiment_change', ascending=True).head(3)
                st.dataframe(top_decreases[['date', 'average_sentiment', 'sentiment_change']], hide_index=True)

            # 4. Show the Raw Database Records
            with st.expander("View Raw Database Records"):
                # We drop the 'id' column just to make the table look cleaner for the user
                st.dataframe(df[['date', 'average_sentiment', 'total_posts']].sort_values(by='date', ascending=False), hide_index=True)
