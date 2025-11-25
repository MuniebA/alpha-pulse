import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
import time
import os


# --- SIDEBAR CONFIGURATION ---
st.sidebar.title("⚙️ Settings")
selected_symbol = st.sidebar.selectbox(
    "Select Asset",
    ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"],
    index=0
)


# --- CONFIGURATION ---
st.set_page_config(
    page_title="Alpha-Pulse Terminal", 
    layout="wide",
    initial_sidebar_state="collapsed"
)


# Defaults to 'localhost' if not running in Docker
db_host = os.getenv("DB_HOST", "localhost")
DB_URL = f"postgresql://user:password@{db_host}:5432/alpha_db"

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

def load_data(interval_code, symbol):
    """Fetch clean OHLC data and a continuous forecast history."""
    
    if interval_code == "ALL":
        time_clause = ""
        limit_clause = "LIMIT 50000"
    else:
        time_clause = f"WHERE bucket_time >= NOW() - INTERVAL '{interval_code}'"
        limit_clause = ""

    # 1. Fetch Market Data
    # Add "AND symbol = :symbol"
    query_market = text(f"""
        SELECT bucket_time, open, high, low, close, sentiment_score, volume
        FROM market_candles
        {time_clause} AND symbol = :symbol
        ORDER BY bucket_time ASC
        {limit_clause}
    """)
    
    # 2. Fetch Forecast Data (The "Continuous Line" Fix)
    # We use DISTINCT ON to grab the LATEST prediction made for every specific timestamp.
    # This means if the AI predicted "10:05" five times (at 10:00, 10:01, etc.),
    # we only take the most recent opinion it had.
    if interval_code == "ALL":
        fc_time = ""
    else:
        # We look a bit further ahead for the forecast (+60 mins) to show future curve
        fc_time = f"WHERE forecast_time >= NOW() - INTERVAL '{interval_code}'"

    query_forecast = text(f"""
        SELECT DISTINCT ON (forecast_time) 
            forecast_time, predicted_price, lower_bound, upper_bound, execution_time
        FROM forecast_logs
        {fc_time} AND symbol = :symbol
        ORDER BY forecast_time, execution_time DESC
        {limit_clause}
    """)
    
    with engine.connect() as conn:
        # Pass {"symbol": symbol} to both calls
        df_market = pd.read_sql(query_market, conn, params={"symbol": symbol})
        df_forecast = pd.read_sql(query_forecast, conn, params={"symbol": symbol})
        
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
    index=2, # Default to 1H to see context
    horizontal=True,
    key="time_selector"
)

# 2. Data Loading
interval_val = TIME_RANGES[selected_range]
df_market, df_forecast = load_data(interval_val, selected_symbol) # Pass selected_symbol

if df_market.empty:
    st.warning(f"⏳ Waiting for data pipeline... (View: {selected_range})")
    time.sleep(2)
    st.rerun()

# 3. Metrics Calculation
latest_close = df_market['close'].iloc[-1]
latest_open = df_market['open'].iloc[-1]
diff = latest_close - latest_open
pct = (diff / latest_open) * 100
sentiment = df_market['sentiment_score'].iloc[-1]

# 4. Visual Stitching (Connecting the Lines)
# We connect the green line (Actuals) to the yellow line (Forecast)
# only if there is a gap between them.
if not df_market.empty and not df_forecast.empty:
    last_actual_time = df_market['bucket_time'].iloc[-1]
    last_actual_price = df_market['close'].iloc[-1]
    
    # Check if the forecast starts AFTER the actuals end
    if df_forecast['forecast_time'].iloc[0] > last_actual_time:
        bridge_row = pd.DataFrame({
            'forecast_time': [last_actual_time], 
            'predicted_price': [last_actual_price],
            'lower_bound': [last_actual_price],
            'upper_bound': [last_actual_price]
        })
        df_forecast = pd.concat([bridge_row, df_forecast], ignore_index=True).sort_values('forecast_time')

# 5. Render Metrics
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

kpi1.metric(f"{selected_symbol} Price", f"${latest_close:,.2f}", f"{diff:+.2f} ({pct:+.2f}%)")

sent_label = "Neutral"
if sentiment > 0.05: sent_label = "Bullish"
elif sentiment < -0.05: sent_label = "Bearish"

kpi2.metric("Sentiment", f"{sentiment:.4f}", sent_label)

kpi3.metric("Forecast Model", "Prophet (60m)", "Active 🟢")

# Anomaly Logic
is_anomaly = False
if not df_forecast.empty:
    # Check against the prediction for the CURRENT time
    current_pred = df_forecast[df_forecast['forecast_time'] == df_market['bucket_time'].iloc[-1]]
    if not current_pred.empty:
        lower = current_pred['lower_bound'].iloc[0]
        upper = current_pred['upper_bound'].iloc[0]
        if latest_close < lower or latest_close > upper:
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
    x=df_forecast['forecast_time'], y=df_forecast['lower_bound'],
    mode='lines', line=dict(width=0), showlegend=False, hoverinfo='skip'
))
fig.add_trace(go.Scatter(
    x=df_forecast['forecast_time'], y=df_forecast['upper_bound'],
    mode='lines', line=dict(width=0), fill='tonexty',
    fillcolor='rgba(0, 200, 255, 0.1)', name='Confidence (95%)', hoverinfo='skip'
))

# B. Actual Price
fig.add_trace(go.Candlestick(
    x=df_market['bucket_time'],
    open=df_market['open'], high=df_market['high'],
    low=df_market['low'], close=df_market['close'],
    name='BTC Actual',
    increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
))

# C. AI Forecast
fig.add_trace(go.Scatter(
    x=df_forecast['forecast_time'], y=df_forecast['predicted_price'],
    mode='lines', name='AI Forecast',
    line=dict(color='#C0C0F0', width=2)
))

fig.update_layout(
    template="plotly_dark", height=600,
    xaxis_rangeslider_visible=False, hovermode="x unified",
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
    st.dataframe(df_market.tail(10)[['bucket_time', 'close', 'volume', 'sentiment_score']].sort_values('bucket_time', ascending=False), use_container_width=True)
with c2:
    st.caption("Extended AI Forecast")
    st.dataframe(df_forecast.tail(10)[['forecast_time', 'predicted_price', 'lower_bound', 'upper_bound']], use_container_width=True)

# Auto-Refresh
time.sleep(2)
st.rerun()