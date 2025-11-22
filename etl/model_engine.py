import time
import pandas as pd
from sqlalchemy import create_engine, text
from prophet import Prophet
import logging

# --- CONFIGURATION ---
DB_URL = "postgresql://user:password@localhost:5432/alpha_db"
TRAINING_WINDOW_MINUTES = 60  # Look back 60 minutes
FORECAST_HORIZON = 10         # Predict next 10 minutes

engine = create_engine(DB_URL)

# Suppress Prophet's noisy logs
logging.getLogger('cmdstanpy').setLevel(logging.WARNING)
logging.getLogger('prophet').setLevel(logging.WARNING)

def fetch_training_data():
    """
    Fetches the last 60 minutes of clean candle data.
    """
    query = text(f"""
        SELECT bucket_time, close, sentiment_score
        FROM market_candles
        WHERE bucket_time >= NOW() - INTERVAL '{TRAINING_WINDOW_MINUTES} minutes'
        ORDER BY bucket_time ASC
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    
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
    print(" Training Model...", end=" ")
    
    # 1. Get Data
    raw_df = fetch_training_data()
    if len(raw_df) < 20:
        print(" Not enough data yet (Need > 20 mins). Waiting...")
        return

    # 2. Clean Data
    df = prepare_data(raw_df)

    # 3. Train Prophet Model
    model = Prophet(interval_width=0.95)  # 95% Confidence Interval
    model.add_regressor('sentiment_score')
    model.fit(df)

    # 4. Create Future Dataframe (10 mins ahead)
    future = model.make_future_dataframe(periods=FORECAST_HORIZON, freq='min')
    
    # Assumption: Future sentiment stays the same as the last known sentiment
    last_sentiment = df['sentiment_score'].iloc[-1]
    future['sentiment_score'] = last_sentiment

    # 5. Predict
    forecast = model.predict(future)
    
    # 6. Save ONLY the future predictions to DB
    # We filter for times that are *after* our last known actual data
    last_actual_time = df['ds'].iloc[-1]
    future_forecast = forecast[forecast['ds'] > last_actual_time]
    
    save_forecast(future_forecast)
    print(f" Prediction Saved! (Next target: ${future_forecast['yhat'].iloc[-1]:.2f})")

def save_forecast(forecast_df):
    with engine.connect() as conn:
        for _, row in forecast_df.iterrows():
            query = text("""
                INSERT INTO forecast_logs (forecast_time, predicted_price, lower_bound, upper_bound)
                VALUES (:time, :price, :low, :high)
            """)
            conn.execute(query, {
                "time": row['ds'],
                "price": row['yhat'],
                "low": row['yhat_lower'],
                "high": row['yhat_upper']
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