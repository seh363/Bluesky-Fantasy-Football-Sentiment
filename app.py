import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import os
from supabase import create_client, Client

# --- Page Config ---
st.set_page_config(page_title="Bluesky NFL Player Sentiment", layout="wide")

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
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(by='date')
        df['7_Day_SMA'] = df['average_sentiment'].rolling(window=7, min_periods=1).mean()
        df['dod_change'] = df['average_sentiment'].diff()
    return df

@st.cache_data(ttl=3600)
def load_all_data():
    response = supabase.table("daily_sentiment").select("*").execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(by=['player_name', 'date'])
    return df

# --- UI & Dashboard ---
st.title("Bluesky NFL Player Sentiment")
st.markdown('What the "Official App of Sports" Thinks')
st.markdown('**Created by [Stephen Hoopes](https://bsky.app/profile/stephenhoopes.bsky.social)**')

with st.expander("ℹ️ How to read these sentiment scores"):
    st.markdown("""
    This dashboard uses Natural Language Processing (NLP) to read daily Bluesky posts and assign them a mathematical score. 
    
    **The Scale (-1.0 to 1.0):**
    * **🟢 1.0 (Extremely Positive):** Pure hype or breakout predictions.
    * **⚪ 0.0 (Neutral):** Fact-based news or updates.
    * **🔴 -1.0 (Extremely Negative):** Heavy criticism or panic.
    """)

st.divider()

player_list = get_available_players()

if player_list:
    # --- UI LAYOUT: Head-to-Head Selection and Timeframe ---
    col1, col2 = st.columns([2, 1])
    with col1:
        # Multiselect allows for head-to-head comparison
        default_players = ["Jahan Dotson"] if "Jahan Dotson" in player_list else [player_list[0]]
        selected_players = st.multiselect(
            "Head-to-Head Player Comparison", 
            options=player_list, 
            default=default_players,
            max_selections=3
        )
    with col2:
        timeframe = st.selectbox("Timeframe", options=["Last 14 Days", "Last 30 Days", "All Time"], index=1)

    if selected_players:
        # --- CHART BUILDING ---
        st.subheader("Sentiment Momentum Comparison")
        fig = go.Figure()
        
        # Color palette for consistent comparison
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
        
        # We'll use this to display KPI cards for the first selected player
        primary_df = None

        for i, player in enumerate(selected_players):
            df = load_player_data(player)
            if not df.empty:
                if i == 0: primary_df = df
                
                # Apply date filter
                max_date = df['date'].max()
                if timeframe == "Last 14 Days":
                    cutoff = max_date - pd.Timedelta(days=14)
                    chart_df = df[df['date'] >= cutoff]
                elif timeframe == "Last 30 Days":
                    cutoff = max_date - pd.Timedelta(days=30)
                    chart_df = df[df['date'] >= cutoff]
                else:
                    chart_df = df
                
                # Add Trend Line (SMA)
                fig.add_trace(go.Scatter(
                    x=chart_df['date'], y=chart_df['7_Day_SMA'],
                    mode='lines',
                    name=f"{player} (7-Day Trend)",
                    line=dict(color=colors[i], width=4)
                ))
                
                # Only add raw data points if 1 player is selected (prevents clutter)
                if len(selected_players) == 1:
                    fig.add_trace(go.Scatter(
                        x=chart_df['date'], y=chart_df['average_sentiment'],
                        mode='lines+markers',
                        name=f"{player} (Daily)",
                        line=dict(color='rgba(150, 150, 150, 0.3)', width=2),
                        marker=dict(size=6)
                    ))

        fig.update_layout(
            xaxis_title=None, 
            yaxis_title="Sentiment Score (-1 to 1)",
            hovermode="x unified", 
            legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5), 
            margin=dict(l=0, r=0, t=20, b=50) 
        )
        fig.update_xaxes(tickformat="%Y-%m-%d", showgrid=False)
        st.plotly_chart(fig, use_container_width=True)

        # --- KPI Metrics for the Primary Player ---
        if primary_df is not None:
            latest = primary_df.iloc[-1]
            st.write(f"**Snapshot: {selected_players[0]}**")
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Current Sentiment", f"{latest['average_sentiment']:.2f}", 
                          delta=f"{latest['dod_change']:.2f}" if pd.notna(latest['dod_change']) else None)
            with m2:
                st.metric("7-Day Trend", f"{latest['7_Day_SMA']:.2f}")
            with m3:
                st.metric("Recent Posts", f"{latest['total_posts']:,}")

    # --- GLOBAL DATA SECTIONS ---
    all_df = load_all_data()
    if not all_df.empty:
        latest_date = all_df['date'].max()
        
        # SECTION: Biggest Sentiment Changes
        st.divider()
        st.subheader("Biggest Sentiment Changes (Last 7 Days)")
        
        seven_days_ago = latest_date - pd.Timedelta(days=7)
        recent_df = all_df[all_df['date'] >= seven_days_ago].copy()
        grouped = recent_df.groupby('player_name')['average_sentiment']
        
        shifts = (grouped.last() - grouped.first()).reset_index()
        day_counts = grouped.count().reset_index()
        
        valid_players = day_counts[day_counts['average_sentiment'] > 1]['player_name']
        shifts = shifts[shifts['player_name'].isin(valid_players)]
        
        if not shifts.empty:
            shifts.columns = ['Player', '7 Day Change']
            current = recent_df.groupby('player_name').last().reset_index()[['player_name', 'average_sentiment']]
            current.columns = ['Player', 'Average Sentiment']
            movers_df = pd.merge(shifts, current, on='Player')
            
            movers_df['Average Sentiment'] = movers_df['Average Sentiment'].round(2)
            movers_df['7 Day Change'] = movers_df['7 Day Change'].round(2)
            
            c1, c2 = st.columns(2)
            with c1:
                st.write("**📈 Top Increases**")
                st.dataframe(movers_df.sort_values(by='7 Day Change', ascending=False).head(5), hide_index=True)
            with c2:
                st.write("**📉 Top Decreases**")
                st.dataframe(movers_df.sort_values(by='7 Day Change', ascending=True).head(5), hide_index=True)

        # SECTION: Extremes
        st.divider()
        st.subheader("Current Sentiment Extremes")
        latest_day = all_df[all_df['date'] == latest_date].copy()
        if not latest_day.empty:
            latest_day = latest_day.rename(columns={'player_name': 'Player', 'average_sentiment': 'Average Sentiment'})
            latest_day['Average Sentiment'] = latest_day['Average Sentiment'].round(2)
            
            c_high, c_low = st.columns(2)
            with c_high:
                st.write("**🔥 Highest Sentiment**")
                st.dataframe(latest_day.sort_values(by='Average Sentiment', ascending=False).head(5)[['Player', 'Average Sentiment']], hide_index=True)
            with c_low:
                st.write("**🧊 Lowest Sentiment**")
                st.dataframe(latest_day.sort_values(by='Average Sentiment', ascending=True).head(5)[['Player', 'Average Sentiment']], hide_index=True)
else:
    st.info("Awaiting initial data load.")
