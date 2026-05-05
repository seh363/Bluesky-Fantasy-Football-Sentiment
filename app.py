import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import os
from supabase import create_client, Client

# --- Page Config (Must be the first Streamlit command) ---
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
    # Fetch all data for the global boards
    response = supabase.table("daily_sentiment").select("*").execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(by=['player_name', 'date'])
    return df

# --- UI & Dashboard ---
st.title("Bluesky NFL Player Sentiment")
st.markdown("What the Official App of Sports Thinks")
st.divider()

player_list = get_available_players()

if player_list:
    # Use columns to put the search bar on the left
    col1, col2 = st.columns([1, 2])
    with col1:
        default_idx = player_list.index("Jahan Dotson") if "Jahan Dotson" in player_list else 0
        player_name = st.selectbox("Search or Select a Player", options=player_list, index=default_idx)

    df = load_player_data(player_name)
    
    if not df.empty:
        latest_data = df.iloc[-1]
        
        # --- Top KPI Metric Cards (Formatted to 2 decimals) ---
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric(
                label="Current Sentiment Score", 
                value=f"{latest_data['average_sentiment']:.2f}", 
                delta=f"{latest_data['dod_change']:.2f}" if pd.notna(latest_data['dod_change']) else None
            )
        with m2:
            st.metric(
                label="7-Day Moving Average", 
                value=f"{latest_data['7_Day_SMA']:.2f}"
            )
        with m3:
            st.metric(
                label="Posts Analyzed (Latest)", 
                value=f"{latest_data['total_posts']:,}"
            )

        # --- Professional Plotly Chart ---
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=df['date'], y=df['average_sentiment'], 
            mode='lines+markers',
            name='Daily Sentiment',
            line=dict(color='rgba(150, 150, 150, 0.5)', width=2),
            marker=dict(size=6)
        ))

        fig.add_trace(go.Scatter(
            x=df['date'], y=df['7_Day_SMA'], 
            mode='lines',
            name='7-Day Trend (SMA)',
            line=dict(color='#1f77b4', width=4)
        ))

        fig.update_layout(
            title=f"Sentiment Momentum: {player_name}",
            xaxis_title=None, 
            yaxis_title="Sentiment Score (-1 to 1)",
            hovermode="x unified", 
            legend=dict(
                orientation="h", 
                yanchor="top", 
                y=-0.15, 
                xanchor="center", 
                x=0.5
            ), 
            margin=dict(l=0, r=0, t=50, b=50) 
        )
        
        fig.update_xaxes(
            tickformat="%Y-%m-%d", 
            showgrid=False 
        )

        st.plotly_chart(fig, use_container_width=True)
        
    # --- FETCH GLOBAL DATA ---
    all_df = load_all_data()
    
    if not all_df.empty:
        latest_date = all_df['date'].max()
        
        # --- SECTION: Global Top Movers (7-Day Shift) ---
        st.divider()
        st.subheader("Global Top Movers (Last 7 Days)")
        
        seven_days_ago = latest_date - pd.Timedelta(days=7)
        recent_df = all_df[all_df['date'] >= seven_days_ago].copy()
        
        grouped = recent_df.groupby('player_name')['average_sentiment']
        first_scores = grouped.first()
        last_scores = grouped.last()
        day_counts = grouped.count()
        
        valid_players = day_counts[day_counts > 1].index
        shifts_series = last_scores[valid_players] - first_scores[valid_players]
        
        shifts = shifts_series.reset_index()
        if not shifts.empty:
            shifts.columns = ['player_name', '7d_change']
            
            current_sentiment = recent_df.groupby('player_name').last().reset_index()[['player_name', 'average_sentiment']]
            movers_df = pd.merge(shifts, current_sentiment, on='player_name')
            
            # Rename columns for the UI
            movers_df = movers_df.rename(columns={
                'player_name': 'Player',
                'average_sentiment': 'Average Sentiment',
                '7d_change': '7 Day Change'
            })
            
            # Formatting to 2 decimals
            movers_df['Average Sentiment'] = movers_df['Average Sentiment'].round(2)
            movers_df['7 Day Change'] = movers_df['7 Day Change'].round(2)
            
            col_inc, col_dec = st.columns(2)
            with col_inc:
                st.write("**📈 Top Increases (7-Day)**")
                top_increases = movers_df.sort_values(by='7 Day Change', ascending=False).head(5)
                st.dataframe(top_increases[['Player', 'Average Sentiment', '7 Day Change']], hide_index=True)
                
            with col_dec:
                st.write("**📉 Top Decreases (7-Day)**")
                top_decreases = movers_df.sort_values(by='7 Day Change', ascending=True).head(5)
                st.dataframe(top_decreases[['Player', 'Average Sentiment', '7 Day Change']], hide_index=True)
        else:
            st.info("Not enough historical data yet to calculate 7-day shifts.")
            
        # --- NEW SECTION: Current Sentiment Extremes ---
        st.divider()
        st.subheader(f"Current Sentiment Extremes")
        
        latest_day_df = all_df[all_df['date'] == latest_date].copy()
        
        if not latest_day_df.empty:
            # Rename columns for the UI
            latest_day_df = latest_day_df.rename(columns={
                'player_name': 'Player',
                'average_sentiment': 'Average Sentiment'
            })
            
            # Formatting to 2 decimals
            latest_day_df['Average Sentiment'] = latest_day_df['Average Sentiment'].round(2)
            
            col_high, col_low = st.columns(2)
            with col_high:
                st.write("**🔥 Highest Sentiment**")
                highest = latest_day_df.sort_values(by='Average Sentiment', ascending=False).head(5)
                st.dataframe(highest[['Player', 'Average Sentiment']], hide_index=True)
                
            with col_low:
                st.write("**🧊 Lowest Sentiment**")
                lowest = latest_day_df.sort_values(by='Average Sentiment', ascending=True).head(5)
                st.dataframe(lowest[['Player', 'Average Sentiment']], hide_index=True)

else:
    st.info("Awaiting initial data load. Ensure your database has populated.")
