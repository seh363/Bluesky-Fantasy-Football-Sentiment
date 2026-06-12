import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import os
from supabase import create_client, Client

# --- Page Config ---
st.set_page_config(
    page_title="Bluesky NFL Sentiment",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Inter:wght@300;400;500&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #090e1a !important;
    color: #e2e8f0 !important;
}

.stApp { background-color: #090e1a !important; }

/* ── Hide streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 2rem 2rem 2rem !important; max-width: 1400px !important; }

/* ── Nav bar ── */
.nav-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.25rem 0 1rem 0;
    border-bottom: 1px solid #1e2d47;
    margin-bottom: 2rem;
}
.nav-logo {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.4rem;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: -0.5px;
}
.nav-logo span { color: #00d4aa; }
.nav-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #0f2027;
    border: 1px solid #00d4aa33;
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 0.72rem;
    color: #00d4aa;
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 500;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.pulse-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #00d4aa;
    animation: pulse-glow 2s ease-in-out infinite;
}
@keyframes pulse-glow {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 #00d4aa55; }
    50% { opacity: 0.6; box-shadow: 0 0 0 5px #00d4aa00; }
}

/* ── Section headers ── */
.section-eyebrow {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #00d4aa;
    margin-bottom: 0.3rem;
}
.section-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.35rem;
    font-weight: 700;
    color: #f1f5f9;
    margin-bottom: 1.25rem;
    letter-spacing: -0.3px;
}

/* ── KPI cards ── */
.kpi-grid { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
.kpi-card {
    flex: 1;
    background: #111827;
    border: 1px solid #1e2d47;
    border-radius: 14px;
    padding: 1.1rem 1.4rem;
    position: relative;
    overflow: hidden;
    transition: border-color 0.2s;
}
.kpi-card:hover { border-color: #00d4aa55; }
.kpi-card.primary { border-color: #00d4aa44; }
.kpi-card.primary::before {
    content: '';
    position: absolute;
    top: -40px; right: -40px;
    width: 100px; height: 100px;
    background: radial-gradient(circle, #00d4aa18 0%, transparent 70%);
    border-radius: 50%;
}
.kpi-label {
    font-size: 0.7rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 0.4rem;
    font-family: 'Space Grotesk', sans-serif;
}
.kpi-value {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: -1px;
    line-height: 1;
}
.kpi-value.positive { color: #00d4aa; }
.kpi-value.negative { color: #f43f5e; }
.kpi-delta {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.78rem;
    font-weight: 500;
    margin-top: 0.3rem;
}
.kpi-delta.up { color: #00d4aa; }
.kpi-delta.down { color: #f43f5e; }
.kpi-delta.flat { color: #64748b; }

/* ── Chart container ── */
.chart-container {
    background: #111827;
    border: 1px solid #1e2d47;
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}

/* ── Controls row ── */
.controls-row {
    display: flex;
    align-items: flex-end;
    gap: 1rem;
    margin-bottom: 1.25rem;
}

/* ── Streamlit widget overrides ── */
.stMultiSelect > div > div {
    background: #111827 !important;
    border: 1px solid #1e2d47 !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
}
.stMultiSelect > div > div:focus-within { border-color: #00d4aa !important; }

.stSelectbox > div > div {
    background: #111827 !important;
    border: 1px solid #1e2d47 !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
}

[data-baseweb="tag"] {
    background: #0f2027 !important;
    border: 1px solid #00d4aa44 !important;
    color: #00d4aa !important;
    border-radius: 6px !important;
}

label[data-testid="stWidgetLabel"] {
    color: #94a3b8 !important;
    font-size: 0.75rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
    font-family: 'Space Grotesk', sans-serif !important;
}

/* ── Divider ── */
.stDivider { border-color: #1e2d47 !important; }
hr { border-color: #1e2d47 !important; }

/* ── Movers table ── */
.movers-card {
    background: #111827;
    border: 1px solid #1e2d47;
    border-radius: 14px;
    padding: 1.25rem 1.4rem;
    margin-bottom: 1rem;
}
.movers-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.85rem;
    font-weight: 600;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.movers-title.rise { color: #00d4aa; }
.movers-title.fall { color: #f43f5e; }

/* ── Dataframe styling ── */
.stDataFrame {
    border: none !important;
}
.stDataFrame > div {
    background: transparent !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    background: #111827 !important;
    border: 1px solid #1e2d47 !important;
    border-radius: 10px !important;
    color: #94a3b8 !important;
    font-size: 0.82rem !important;
}
.streamlit-expanderContent {
    background: #111827 !important;
    border: 1px solid #1e2d47 !important;
    border-top: none !important;
    border-radius: 0 0 10px 10px !important;
    color: #94a3b8 !important;
    font-size: 0.85rem !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #0d1424 !important;
    border-right: 1px solid #1e2d47 !important;
}
[data-testid="stSidebar"] a { color: #00d4aa !important; }
[data-testid="stSidebar"] .stMarkdown { color: #94a3b8 !important; }

/* ── Button ── */
.stButton > button {
    background: #111827 !important;
    border: 1px solid #1e2d47 !important;
    color: #94a3b8 !important;
    border-radius: 8px !important;
    font-size: 0.8rem !important;
    font-family: 'Space Grotesk', sans-serif !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    border-color: #00d4aa55 !important;
    color: #00d4aa !important;
    background: #0f2027 !important;
}

/* ── Sentiment bar chip ── */
.sentiment-bar {
    display: inline-block;
    height: 4px;
    border-radius: 2px;
    background: linear-gradient(90deg, #f43f5e, #64748b, #00d4aa);
    width: 100%;
    position: relative;
    margin-top: 2px;
}

/* ── Score guide chips ── */
.score-guide {
    display: flex;
    gap: 1rem;
    margin-top: 0.5rem;
}
.score-chip {
    background: #0d1424;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 0.72rem;
    font-family: 'Space Grotesk', sans-serif;
    border: 1px solid #1e2d47;
}
.score-chip.pos { color: #00d4aa; border-color: #00d4aa33; }
.score-chip.neu { color: #94a3b8; }
.score-chip.neg { color: #f43f5e; border-color: #f43f5e33; }
</style>
""", unsafe_allow_html=True)

# ── Data connection ─────────────────────────────────────────────────────────────
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

# ── Nav bar ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="nav-bar">
    <div>
        <div class="nav-logo">Bluesky <span>NFL Sentiment</span></div>
        <div style="font-family:'Inter',sans-serif; font-size:0.78rem; color:#475569; margin-top:3px; font-style:italic;">What the 'Official App of Sports' Thinks</div>
    </div>
    <div class="nav-badge">
        <div class="pulse-dot"></div>
        Live · Updated Daily
    </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### About")
    st.markdown("**Stephen Hoopes**")
    st.markdown("[Bluesky](https://bsky.app/profile/stephenhoopes.bsky.social) · [4for4 Articles](https://www.4for4.com/users/stephen-hoopes/author-page)")
    st.divider()
    if st.button("↺  Refresh data"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.markdown("""
<div style="font-size:0.75rem; color:#475569; line-height:1.6;">
Sentiment is calculated daily from Bluesky posts using NLP. Scores range from <span style="color:#f43f5e">−1.0 (strongly negative)</span> to <span style="color:#00d4aa">+1.0 (strongly positive)</span>. The chart line shows a 7-day rolling average to smooth daily noise.
</div>
""", unsafe_allow_html=True)

# ── Score guide strip ────────────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1.75rem; flex-wrap:wrap;">
    <span style="font-size:0.7rem; color:#475569; font-family:'Space Grotesk',sans-serif; text-transform:uppercase; letter-spacing:0.08em; font-weight:500;">Sentiment scale</span>
    <span class="score-chip pos">+1.0 Peak hype</span>
    <span class="score-chip neu">0.0 Neutral</span>
    <span class="score-chip neg">−1.0 Heavy criticism</span>
    <span style="font-size:0.7rem; color:#334155; margin-left:auto;">Chart line = 7-day trend</span>
</div>
""", unsafe_allow_html=True)

# ── Main dashboard ───────────────────────────────────────────────────────────────
player_list = get_available_players()

if player_list:
    # Controls
    col_select, col_time, col_spacer = st.columns([3, 1.2, 2])
    with col_select:
        default_players = ["Jahan Dotson"] if "Jahan Dotson" in player_list else [player_list[0]]
        selected_players = st.multiselect(
            "Compare players (up to 3)",
            options=player_list,
            default=default_players,
            max_selections=3
        )
    with col_time:
        timeframe = st.selectbox(
            "Time window",
            options=["14 days", "30 days", "All time"],
            index=1
        )

    if selected_players:
        # ── KPI strip ────────────────────────────────────────────────────────────
        primary_player = selected_players[0]
        primary_df_full = load_player_data(primary_player)

        if not primary_df_full.empty:
            latest = primary_df_full.iloc[-1]
            sentiment_val = latest['average_sentiment']
            sma_val = latest['7_Day_SMA']
            dod = latest['dod_change'] if pd.notna(latest['dod_change']) else 0
            posts = int(latest['total_posts'])

            val_class = "positive" if sentiment_val >= 0.05 else ("negative" if sentiment_val <= -0.05 else "")
            delta_class = "up" if dod > 0 else ("down" if dod < 0 else "flat")
            delta_arrow = "▲" if dod > 0 else ("▼" if dod < 0 else "—")

            st.markdown(f"""
<div class="kpi-grid">
    <div class="kpi-card primary">
        <div class="kpi-label">Current Sentiment · {primary_player}</div>
        <div class="kpi-value {val_class}">{sentiment_val:+.2f}</div>
        <div class="kpi-delta {delta_class}">{delta_arrow} {abs(dod):.2f} day-over-day</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">7-Day Trend</div>
        <div class="kpi-value">{sma_val:+.2f}</div>
        <div class="kpi-delta {'up' if sma_val > 0 else 'down' if sma_val < 0 else 'flat'}">rolling average</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Posts Today</div>
        <div class="kpi-value">{posts:,}</div>
        <div class="kpi-delta flat">Bluesky mentions</div>
    </div>
</div>
""", unsafe_allow_html=True)

        # ── Chart ──────────────────────────────────────────────────────────────────
        COLORS = ['#00d4aa', '#f59e0b', '#818cf8']

        fig = go.Figure()

        # Zero line zone
        fig.add_hrect(
            y0=-0.05, y1=0.05,
            line_width=0,
            fillcolor="rgba(30,45,71,0.13)",
            layer="below"
        )

        # Sentiment zone fills for single player
        if len(selected_players) == 1:
            df_full = load_player_data(selected_players[0])
            if not df_full.empty:
                max_date = df_full['date'].max()
                if timeframe == "14 days":
                    chart_df = df_full[df_full['date'] >= max_date - pd.Timedelta(days=14)]
                elif timeframe == "30 days":
                    chart_df = df_full[df_full['date'] >= max_date - pd.Timedelta(days=30)]
                else:
                    chart_df = df_full

                # Positive fill
                fig.add_trace(go.Scatter(
                    x=chart_df['date'], y=chart_df['7_Day_SMA'].clip(lower=0),
                    fill='tozeroy',
                    fillcolor='rgba(0,212,170,0.07)',
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo='skip'
                ))
                # Negative fill
                fig.add_trace(go.Scatter(
                    x=chart_df['date'], y=chart_df['7_Day_SMA'].clip(upper=0),
                    fill='tozeroy',
                    fillcolor='rgba(244,63,94,0.07)',
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo='skip'
                ))
                # Daily dots
                fig.add_trace(go.Scatter(
                    x=chart_df['date'],
                    y=chart_df['average_sentiment'],
                    mode='markers',
                    name='Daily score',
                    marker=dict(
                        size=6,
                        color=chart_df['average_sentiment'],
                        colorscale=[[0, '#f43f5e'], [0.5, '#475569'], [1, '#00d4aa']],
                        cmin=-1, cmax=1,
                        opacity=0.55,
                        line=dict(width=0)
                    ),
                    hovertemplate='<b>%{x|%b %d}</b><br>Score: %{y:.3f}<extra></extra>'
                ))

        # Trend lines (all players)
        for i, player in enumerate(selected_players):
            df = load_player_data(player)
            if not df.empty:
                max_date = df['date'].max()
                if timeframe == "14 days":
                    chart_df = df[df['date'] >= max_date - pd.Timedelta(days=14)]
                elif timeframe == "30 days":
                    chart_df = df[df['date'] >= max_date - pd.Timedelta(days=30)]
                else:
                    chart_df = df

                fig.add_trace(go.Scatter(
                    x=chart_df['date'],
                    y=chart_df['7_Day_SMA'],
                    mode='lines',
                    name=f"{player}",
                    line=dict(color=COLORS[i], width=3, shape='spline'),
                    hovertemplate=f'<b>{player}</b><br>%{{x|%b %d}}<br>Trend: %{{y:.3f}}<extra></extra>'
                ))

        fig.update_layout(
            height=380,
            plot_bgcolor='#111827',
            paper_bgcolor='#111827',
            font=dict(family='Space Grotesk', color='#94a3b8', size=12),
            xaxis=dict(
                showgrid=False,
                zeroline=False,
                color='#475569',
                tickfont=dict(size=11, color='#475569'),
                fixedrange=True,
                showline=False,
            ),
            yaxis=dict(
                range=[-1.1, 1.1],
                gridcolor='#1e2d47',
                gridwidth=1,
                zeroline=True,
                zerolinecolor='#2d3d56',
                zerolinewidth=1.5,
                tickformat='.2f',
                color='#475569',
                tickfont=dict(size=11, color='#475569'),
                fixedrange=True,
                title=dict(text='Sentiment Score', font=dict(color='#475569', size=11)),
            ),
            hovermode='x unified',
            legend=dict(
                orientation='h',
                yanchor='bottom', y=1.02,
                xanchor='left', x=0,
                font=dict(color='#94a3b8', size=12),
                bgcolor='rgba(0,0,0,0)',
                borderwidth=0
            ),
            margin=dict(l=10, r=10, t=10, b=10),
            dragmode=False
        )

        # Wrap chart in styled container
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Movers Section ──────────────────────────────────────────────────────────
    all_df = load_all_data()
    if not all_df.empty:
        latest_date = all_df['date'].max()
        seven_days_ago = latest_date - pd.Timedelta(days=7)
        recent_df = all_df[all_df['date'] >= seven_days_ago].copy()
        grouped = recent_df.groupby('player_name')['average_sentiment']
        shifts = (grouped.last() - grouped.first()).reset_index()
        day_counts = grouped.count().reset_index()
        valid_players = day_counts[day_counts['average_sentiment'] > 1]['player_name']
        shifts = shifts[shifts['player_name'].isin(valid_players)]

        if not shifts.empty:
            shifts.columns = ['Player', 'Δ 7 Days']
            current = recent_df.groupby('player_name').last().reset_index()[['player_name', 'average_sentiment']]
            current.columns = ['Player', 'Score']
            movers_df = pd.merge(shifts, current, on='Player')

            st.markdown("""
<div style="margin-bottom:0.5rem;">
    <div class="section-eyebrow">Weekly movers</div>
    <div class="section-title">Biggest Sentiment Shifts — Last 7 Days</div>
</div>
""", unsafe_allow_html=True)

            col_rise, col_fall = st.columns(2, gap="medium")

            with col_rise:
                st.markdown('<div class="movers-card">', unsafe_allow_html=True)
                st.markdown('<div class="movers-title rise">📈 Rising</div>', unsafe_allow_html=True)
                risers = movers_df.sort_values('Δ 7 Days', ascending=False).head(5).reset_index(drop=True)
                def color_pos(val):
                    try:
                        v = min(max(float(val) / 0.5, 0), 1)
                        g = int(80 + 172 * v)
                        return f'color: rgb(0,{g},120); font-weight: 600;'
                    except:
                        return ''
                st.dataframe(
                    risers.style
                        .format({'Δ 7 Days': '{:+.2f}', 'Score': '{:+.2f}'})
                        .map(color_pos, subset=['Δ 7 Days'])
                        .set_properties(**{
                            'background-color': 'transparent',
                            'color': '#e2e8f0',
                            'font-family': 'Space Grotesk, sans-serif',
                            'font-size': '13px',
                        }),
                    hide_index=True,
                    use_container_width=True
                )
                st.markdown('</div>', unsafe_allow_html=True)

            with col_fall:
                st.markdown('<div class="movers-card">', unsafe_allow_html=True)
                st.markdown('<div class="movers-title fall">📉 Falling</div>', unsafe_allow_html=True)
                fallers = movers_df.sort_values('Δ 7 Days', ascending=True).head(5).reset_index(drop=True)
                def color_neg(val):
                    try:
                        v = min(max(float(val) / -0.5, 0), 1)
                        r = int(150 + 94 * v)
                        return f'color: rgb({r},40,80); font-weight: 600;'
                    except:
                        return ''
                st.dataframe(
                    fallers.style
                        .format({'Δ 7 Days': '{:+.2f}', 'Score': '{:+.2f}'})
                        .map(color_neg, subset=['Δ 7 Days'])
                        .set_properties(**{
                            'background-color': 'transparent',
                            'color': '#e2e8f0',
                            'font-family': 'Space Grotesk, sans-serif',
                            'font-size': '13px',
                        }),
                    hide_index=True,
                    use_container_width=True
                )
                st.markdown('</div>', unsafe_allow_html=True)

        # ── Today's Extremes ────────────────────────────────────────────────────
        latest_day = all_df[all_df['date'] == latest_date].copy()
        if not latest_day.empty:
            latest_day = latest_day.rename(columns={
                'player_name': 'Player',
                'average_sentiment': 'Score',
                'top_pos_text': 'Most Positive Post',
                'top_neg_text': 'Most Negative Post'
            })

            st.markdown("""
<div style="margin-top:1.75rem; margin-bottom:0.5rem;">
    <div class="section-eyebrow">Today's snapshot</div>
    <div class="section-title">Sentiment Extremes</div>
</div>
""", unsafe_allow_html=True)

            col_hot, col_cold = st.columns(2, gap="medium")

            with col_hot:
                st.markdown('<div class="movers-card">', unsafe_allow_html=True)
                st.markdown('<div class="movers-title rise">🔥 Highest Sentiment</div>', unsafe_allow_html=True)
                high_df = latest_day.sort_values('Score', ascending=False).head(5)
                def color_score_pos(val):
                    try:
                        v = min(max(float(val), 0), 1)
                        g = int(80 + 172 * v)
                        return f'color: rgb(0,{g},120); font-weight: 600;'
                    except:
                        return ''
                st.dataframe(
                    high_df[['Player', 'Score', 'Most Positive Post']]
                        .style.format({'Score': '{:+.2f}'})
                        .map(color_score_pos, subset=['Score'])
                        .set_properties(**{
                            'background-color': 'transparent',
                            'color': '#e2e8f0',
                            'font-family': 'Space Grotesk, sans-serif',
                            'font-size': '13px',
                        }),
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Most Positive Post": st.column_config.TextColumn("Most Positive Post", width="large")
                    }
                )
                st.markdown('</div>', unsafe_allow_html=True)

            with col_cold:
                st.markdown('<div class="movers-card">', unsafe_allow_html=True)
                st.markdown('<div class="movers-title fall">🧊 Lowest Sentiment</div>', unsafe_allow_html=True)
                low_df = latest_day.sort_values('Score', ascending=True).head(5)
                def color_score_neg(val):
                    try:
                        v = min(max(float(val) / -1, 0), 1)
                        r = int(150 + 94 * v)
                        return f'color: rgb({r},40,80); font-weight: 600;'
                    except:
                        return ''
                st.dataframe(
                    low_df[['Player', 'Score', 'Most Negative Post']]
                        .style.format({'Score': '{:+.2f}'})
                        .map(color_score_neg, subset=['Score'])
                        .set_properties(**{
                            'background-color': 'transparent',
                            'color': '#e2e8f0',
                            'font-family': 'Space Grotesk, sans-serif',
                            'font-size': '13px',
                        }),
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Most Negative Post": st.column_config.TextColumn("Most Negative Post", width="large")
                    }
                )
                st.markdown('</div>', unsafe_allow_html=True)

# ── Footer ───────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:3rem; padding-top:1.25rem; border-top:1px solid #1e2d47; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem;">
    <span style="font-family:'Space Grotesk',sans-serif; font-size:0.72rem; color:#334155;">
        Bluesky NFL Sentiment · Data sourced from Bluesky · Updated daily
    </span>
    <span style="font-family:'Space Grotesk',sans-serif; font-size:0.72rem; color:#334155;">
        Built by <a href="https://bsky.app/profile/stephenhoopes.bsky.social" style="color:#00d4aa; text-decoration:none;">Stephen Hoopes</a>
    </span>
</div>
""", unsafe_allow_html=True)
