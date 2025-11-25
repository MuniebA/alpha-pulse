import time
import pandas as pd
from sqlalchemy import create_engine, text
from prophet import Prophet
import logging
import os

# List of symbols to forecast
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

# --- CONFIGURATION ---
# Defaults to 'localhost' if not running in Docker
db_host = os.getenv("DB_HOST", "localhost")
DB_URL = f"postgresql://user:password@{db_host}:5432/alpha_db"


TRAINING_WINDOW_MINUTES = 60  # Look back 60 minutes
FORECAST_HORIZON = 5         # Predict next 5 minutes

engine = create_engine(DB_URL)

# Suppress Prophet's noisy logs
logging.getLogger('cmdstanpy').setLevel(logging.WARNING)
logging.getLogger('prophet').setLevel(logging.WARNING)

def fetch_training_data(symbol):
    """Fetches data for a SPECIFIC symbol."""
    query = text(f"""
        SELECT bucket_time, close, sentiment_score
        FROM market_candles
        WHERE bucket_time >= NOW() - INTERVAL '{TRAINING_WINDOW_MINUTES} minutes'
        AND symbol = :symbol
        ORDER BY bucket_time ASC
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"symbol": symbol})
    return df

def prepare_data(df):
    """
    The "Data Science Task": Handle Missing Data (Gaps).
    """
    if df.empty:
        return df

    # 1. Renaming for Prophet (ds = time, y = target)
    df = df.rename(columns={'bucket_time': 'ds', 'close': 'y'})
    
    # 2. Ensure 'ds' is datetime
    # Ensure we drop timezone info to match the DB format
    df['ds'] = pd.to_datetime(df['ds']).dt.tz_localize(None)
    
    # 3. FIX GAPS (The Resume Bullet Point)
    # We set the time as index, resample to 1 minute, and Forward Fill
    df = df.set_index('ds').resample('1min').ffill().reset_index()
    
    # 4. Handle Sentiment (Fill NaNs with 0 if sentiment didn't arrive)
    df['sentiment_score'] = df['sentiment_score'].fillna(0.0)
    
    return df

def generate_forecast():
    print("🧠 Starting Forecast Cycle...")
    
    for symbol in SYMBOLS:
        print(f"   > Processing {symbol}...", end=" ")
        
        raw_df = fetch_training_data(symbol)
        if len(raw_df) < 20:
            print("Not enough data yet.")
            continue # Skip to next symbol

        df = prepare_data(raw_df)
        
        # ... (The rest of the Prophet logic stays the same) ...
        model = Prophet(interval_width=0.95)
        model.add_regressor('sentiment_score')
        model.fit(df)
        
        future = model.make_future_dataframe(periods=FORECAST_HORIZON, freq='min')
        future['sentiment_score'] = df['sentiment_score'].iloc[-1]
        forecast = model.predict(future)
        
        # Filter for future only
        last_actual_time = df['ds'].iloc[-1]
        future_forecast = forecast[forecast['ds'] > last_actual_time]
        
        if not future_forecast.empty:
            save_forecast(symbol, future_forecast) # <--- Pass symbol here
            print(f"Saved!")

def save_forecast(symbol, forecast_df):
    with engine.connect() as conn:
        for _, row in forecast_df.iterrows():
            query = text("""
                INSERT INTO forecast_logs (forecast_time, predicted_price, lower_bound, upper_bound, symbol)
                VALUES (:time, :price, :low, :high, :symbol)
            """)
            conn.execute(query, {
                "time": row['ds'],
                "price": row['yhat'],
                "low": row['yhat_lower'],
                "high": row['yhat_upper'],
                "symbol": symbol # <--- Save the symbol
            })
            conn.commit()

if __name__ == "__main__":
    print(" Forecast Engine Started...")
    while True:
        try:
            generate_forecast()
            # Run every minute
            time.sleep(60)
        except Exception as e:
            print(f" Model Error: {e}")
            time.sleep(60)