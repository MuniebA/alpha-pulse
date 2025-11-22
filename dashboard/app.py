import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
import time

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Alpha-Pulse Terminal", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

DB_URL = "postgresql://user:password@localhost:5432/alpha_db"

@st.cache_resource
def get_engine():
    return create_engine(DB_URL)

engine = get_engine()

# --- TIME FILTERS ---
TIME_RANGES = {
    "15M": "15 minutes",
    "30M": "30 minutes",
    "1H": "60 minutes",
    "1D": "24 hours",
    "1W": "7 days",
    "ALL": "ALL"
}

def load_data(interval_code):
    """Fetch clean OHLC data and ONLY the latest forecast batch."""
    
    if interval_code == "ALL":
        time_clause = ""
        limit_clause = "LIMIT 50000"
    else:
        time_clause = f"WHERE bucket_time >= NOW() - INTERVAL '{interval_code}'"
        limit_clause = ""

    # 1. Fetch Market Data
    # Added 'volume' to SELECT so the table at the bottom works
    query_market = text(f"""
        SELECT bucket_time, open, high, low, close, sentiment_score, volume
        FROM market_candles
        {time_clause}
        ORDER BY bucket_time ASC
        {limit_clause}
    """)
    
    # 2. Fetch ONLY The Latest Forecast Batch
    query_forecast = text("""
        WITH LatestRun AS (
            SELECT MAX(execution_time) as max_exec FROM forecast_logs
        )
        SELECT forecast_time, predicted_price, lower_bound, upper_bound
        FROM forecast_logs, LatestRun
        WHERE execution_time = LatestRun.max_exec
        ORDER BY forecast_time ASC
    """)
    
    with engine.connect() as conn:
        df_market = pd.read_sql(query_market, conn)
        df_forecast = pd.read_sql(query_forecast, conn)
        
        # Force Datetime objects to be UTC-aware/clean
        if not df_market.empty:
            df_market['bucket_time'] = pd.to_datetime(df_market['bucket_time'])
        if not df_forecast.empty:
            df_forecast['forecast_time'] = pd.to_datetime(df_forecast['forecast_time'])

    return df_market, df_forecast

# --- MAIN APP ---
st.title("⚡ Alpha-Pulse: Quant Trading Dashboard")

# 1. Filter Widget
selected_range = st.radio(
    "Range:", 
    options=["15M", "30M", "1H", "1D", "1W", "ALL"], 
    index=1, # Default to 30M
    horizontal=True,
    key="time_selector"
)

# 2. Data Loading
interval_val = TIME_RANGES[selected_range]
df_market, df_forecast = load_data(interval_val)

if df_market.empty:
    st.warning(f"⏳ Waiting for data pipeline... (View: {selected_range})")
    time.sleep(2)
    st.rerun()

# 3. Metrics Calculation
# We calculate these BEFORE using them in the UI
latest_close = df_market['close'].iloc[-1]
latest_open = df_market['open'].iloc[-1]
diff = latest_close - latest_open
pct = (diff / latest_open) * 100
sentiment = df_market['sentiment_score'].iloc[-1]  # <--- THIS DEFINES 'sentiment'

# 4. Visual Stitching
# Connects the green candles to the yellow forecast line
if not df_market.empty and not df_forecast.empty:
    last_actual_time = df_market['bucket_time'].iloc[-1]
    last_actual_price = df_market['close'].iloc[-1]
    
    bridge_row = pd.DataFrame({
        'forecast_time': [last_actual_time], 
        'predicted_price': [last_actual_price],
        'lower_bound': [last_actual_price],
        'upper_bound': [last_actual_price]
    })
    df_forecast = pd.concat([bridge_row, df_forecast], ignore_index=True)

# 5. Render Metrics
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

kpi1.metric(
    "Bitcoin Price", 
    f"${latest_close:,.2f}", 
    f"{diff:+.2f} ({pct:+.2f}%)"
)

# Logic for Sentiment Label
sent_label = "Neutral"
if sentiment > 0.05: 
    sent_label = "Bullish"
elif sentiment < -0.05: 
    sent_label = "Bearish"

kpi2.metric(
    "Sentiment", 
    f"{sentiment:.4f}", 
    sent_label
)

kpi3.metric("Status", "Online 🟢", f"View: {selected_range}")

# Anomaly Logic
is_anomaly = False
if not df_forecast.empty:
    check_idx = 1 if len(df_forecast) > 1 else 0
    first_pred = df_forecast.iloc[check_idx]
    
    if latest_close < first_pred['lower_bound'] or latest_close > first_pred['upper_bound']:
        is_anomaly = True

if is_anomaly:
    kpi4.error("⚠️ ANOMALY DETECTED")
else:
    kpi4.success("✅ Market Normal")

# --- CHARTING ---
st.subheader("Market Analysis & AI Projection")

fig = go.Figure()

# A. Confidence Band
fig.add_trace(go.Scatter(
    x=df_forecast['forecast_time'],
    y=df_forecast['lower_bound'],
    mode='lines',
    line=dict(width=0),
    showlegend=False,
    hoverinfo='skip'
))
fig.add_trace(go.Scatter(
    x=df_forecast['forecast_time'],
    y=df_forecast['upper_bound'],
    mode='lines',
    line=dict(width=0),
    fill='tonexty',
    fillcolor='rgba(0, 200, 255, 0.15)',
    name='Confidence (95%)',
    hoverinfo='skip'
))

# B. Actual Price
fig.add_trace(go.Candlestick(
    x=df_market['bucket_time'],
    open=df_market['open'], high=df_market['high'],
    low=df_market['low'], close=df_market['close'],
    name='BTC Actual',
    increasing_line_color='#26a69a', 
    decreasing_line_color='#ef5350'
))

# C. AI Prediction
fig.add_trace(go.Scatter(
    x=df_forecast['forecast_time'],
    y=df_forecast['predicted_price'],
    mode='lines',
    name='AI Forecast',
    line=dict(color='#C0C0F0', width=2)
))

fig.update_layout(
    template="plotly_dark",
    height=600,
    xaxis_rangeslider_visible=False,
    hovermode="x unified",
    margin=dict(l=10, r=10, t=10, b=10),
    legend=dict(orientation="h", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
    xaxis=dict(type='date')
)

st.plotly_chart(fig, use_container_width=True, key="chart_widget")

# --- TABLES ---
st.markdown("### 📋 Raw Data Feed")
c1, c2 = st.columns(2)
with c1:
    st.caption("Recent Market Data")
    # Ensuring all columns exist before displaying
    cols_to_show = ['bucket_time', 'close', 'volume', 'sentiment_score']
    st.dataframe(
        df_market.tail(10)[cols_to_show].sort_values('bucket_time', ascending=False), 
        use_container_width=True
    )
with c2:
    st.caption("Latest AI Forecast")
    st.dataframe(
        df_forecast.tail(10)[['forecast_time', 'predicted_price', 'lower_bound', 'upper_bound']], 
        use_container_width=True
    )

# Auto-Refresh
time.sleep(2)
st.rerun()