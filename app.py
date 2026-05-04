import streamlit as st
import plotly.express as px
import pandas as pd
import os
from supabase import create_client, Client

# --- 1. Database Connection ---
@st.cache_resource
def init_connection():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- 2. Data Fetching Functions ---
@st.cache_data(ttl=3600)
def get_available_players():
    # Fetch just the player names to populate our dropdown menu
    response = supabase.table("daily_sentiment").select("player_name").execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        # Get unique names and sort them alphabetically
        return sorted(df['player_name'].unique().tolist())
    return ["Jahan Dotson"] # Fallback if DB is empty

@st.cache_data(ttl=3600)
def load_player_data(player):
    # Fetch data for the specific player chosen in the dropdown
    response = supabase.table("daily_sentiment").select("*").eq("player_name", player).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.sort_values(by='date')
    return df

@st.cache_data(ttl=3600)
def load_all_data():
    # Fetch all data so we can calculate the global top movers
    response = supabase.table("daily_sentiment").select("*").execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date']).dt.date
        # Sort by player, then date, so the .diff() math calculates correctly
        df = df.sort_values(by=['player_name', 'date'])
    return df

# --- 3. UI & Dashboard ---
st.title("NFL Player Sentiment Analyzer")
st.write("Track public sentiment over time based on Bluesky posts.")

# Get the list of all players in the DB
player_list = get_available_players()

# NEW: Searchable Dropdown
# If Jahan Dotson is in the database, make him the default, otherwise default to the first player in the list
default_index = player_list.index("Jahan Dotson") if "Jahan Dotson" in player_list else 0
player_name = st.selectbox("Search or Select a Player", options=player_list, index=default_index)

if st.button("Analyze Player Trend"):
    with st.spinner("Loading data..."):
        
        # --- TOP SECTION: Individual Player Trend ---
        df = load_player_data(player_name)
        
        if df.empty:
            st.warning(f"No data available for {player_name}.")
        else:
            fig = px.line(df, x='date', y='average_sentiment', 
                          title=f"Sentiment Over Time: {player_name}",
                          markers=True)
            fig.add_hline(y=0, line_dash="dash", line_color="red")
            fig.update_layout(yaxis_title="Average Sentiment Score (-1 to 1)", xaxis_title="Date")
            st.plotly_chart(fig, use_container_width=True)

# --- BOTTOM SECTION: Global Top Movers (Independent) ---
st.divider() # Adds a nice visual line to separate the sections

all_df = load_all_data()

if not all_df.empty:
    # Find the most recent date in the entire database
    latest_date = all_df['date'].max()
    st.subheader(f"Global Top Movers (Latest Data: {latest_date})")
    
    # Calculate day-over-day changes for EVERY player
    all_df['sentiment_change'] = all_df.groupby('player_name')['average_sentiment'].diff()
    
    # Filter down to just the most recent day to see who moved the most *today*
    latest_shifts = all_df[all_df['date'] == latest_date].dropna(subset=['sentiment_change']).copy()
    
    if not latest_shifts.empty:
        latest_shifts['average_sentiment'] = latest_shifts['average_sentiment'].round(3)
        latest_shifts['sentiment_change'] = latest_shifts['sentiment_change'].round(3)
        
        col_inc, col_dec = st.columns(2)
        with col_inc:
            st.write("**📈 Top Increases Across NFL**")
            top_increases = latest_shifts.sort_values(by='sentiment_change', ascending=False).head(5)
            st.dataframe(top_increases[['player_name', 'average_sentiment', 'sentiment_change']], hide_index=True)
            
        with col_dec:
            st.write("**📉 Top Decreases Across NFL**")
            top_decreases = latest_shifts.sort_values(by='sentiment_change', ascending=True).head(5)
            st.dataframe(top_decreases[['player_name', 'average_sentiment', 'sentiment_change']], hide_index=True)
    else:
        st.info("Not enough historical data yet to calculate day-over-day global shifts. Check back tomorrow!")
