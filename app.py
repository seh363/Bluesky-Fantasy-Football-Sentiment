import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import os
from supabase import create_client, Client

# --- Page Config (Must be the first Streamlit command) ---
st.set_page_config(page_title="NFL Sentiment Dashboard", layout="wide")

@st.cache_resource
def init_connection():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)

supabase = init_connection()

@st.cache_data(ttl=3600)
def get_available_players():
    response = supabase.table("daily_sentiment").select("player_name").execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        return sorted(df['player_name'].unique().tolist())
    return []

@st.cache_data(ttl=3600)
def load_player_data(player):
    response = supabase.table("daily_sentiment").select("*").eq("player_name", player).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        # Convert to datetime and sort
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(by='date')
        
        # Calculate the 7-Day Simple Moving Average (SMA)
        df['7_Day_SMA'] = df['average_sentiment'].rolling(window=7, min_periods=1).mean()
        
        # Calculate day-over-day changes for the metric cards
        df['dod_change'] = df['average_sentiment'].diff()
    return df

# --- UI & Dashboard ---
st.title("🏈 NFL Player Sentiment Analyzer")
st.markdown("Track high-signal public sentiment shifts based on Bluesky discussions.")
st.divider()

player_list = get_available_players()

if player_list:
    # Use columns to put the search bar on the left, keeping the UI tight
    col1, col2 = st.columns([1, 2])
    with col1:
        default_idx = player_list.index("Jahan Dotson") if "Jahan Dotson" in player_list else 0
        player_name = st.selectbox("Search or Select a Player", options=player_list, index=default_idx)

    df = load_player_data(player_name)
    
    if not df.empty:
        latest_data = df.iloc[-1]
        
        # --- Top KPI Metric Cards ---
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric(
                label="Current Sentiment Score", 
                value=f"{latest_data['average_sentiment']:.3f}", 
                delta=f"{latest_data['dod_change']:.3f}" if pd.notna(latest_data['dod_change']) else None
            )
        with m2:
            st.metric(
                label="7-Day Moving Average", 
                value=f"{latest_data['7_Day_SMA']:.3f}"
            )
        with m3:
            st.metric(
                label="Posts Analyzed (Latest)", 
                value=f"{latest_data['total_posts']:,}"
            )

        # --- Professional Plotly Chart ---
        fig = go.Figure()

        # 1. The Raw Daily Sentiment (Faded out slightly)
        fig.add_trace(go.Scatter(
            x=df['date'], y=df['average_sentiment'], 
            mode='lines+markers',
            name='Daily Sentiment',
            line=dict(color='rgba(150, 150, 150, 0.5)', width=2),
            marker=dict(size=6)
        ))

        # 2. The 7-Day Moving Average (Bold and clear)
        fig.add_trace(go.Scatter(
            x=df['date'], y=df['7_Day_SMA'], 
            mode='lines',
            name='7-Day Trend (SMA)',
            line=dict(color='#1f77b4', width=4)
        ))

        # Formatting the Layout
        fig.update_layout(
            title=f"Sentiment Momentum: {player_name}",
            xaxis_title=None, # Cleaner without text explicitly saying "Date"
            yaxis_title="Sentiment Score (-1 to 1)",
            hovermode="x unified", # Shows all data for a specific day in one neat hover box
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), # Moves legend to top
            margin=dict(l=0, r=0, t=40, b=0) # Tightens the margins
        )
        
        # Fix the X-Axis formatting (Forces YYYY-MM-DD HH:MM)
        fig.update_xaxes(
            tickformat="%Y-%m-%d %H:%M",
            showgrid=False # Removes vertical grid lines for a cleaner look
        )

        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Awaiting initial data load. Ensure your database has populated.")
