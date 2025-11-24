import asyncio
import websockets
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
import os


# --- CONFIGURATION ---
# Defaults to 'localhost' if not running in Docker
db_host = os.getenv("DB_HOST", "localhost")
DB_URL = f"postgresql://user:password@{db_host}:5432/alpha_db"

BINANCE_URL = "wss://stream.binance.com:9443/ws/btcusdt@trade"

# --- DATABASE CONNECTION ---
engine = create_engine(DB_URL)

# --- GLOBAL STATE (In-Memory Aggregation) ---
# This holds our data while we wait for the minute to finish
current_candle = {
    'open': None,
    'high': float('-inf'),
    'low': float('inf'),
    'close': None,
    'volume': 0.0,
    'start_time': None,
    'trade_count': 0
}

def save_raw_tick(tick_data):
    """
    Saves the raw dirty JSON data immediately to the audit table.
    """
    try:
        with engine.connect() as conn:
            query = text("""
                INSERT INTO raw_ticks (symbol, price, quantity, trade_time)
                VALUES (:symbol, :price, :quantity, :time)
            """)
            conn.execute(query, {
                "symbol": tick_data['s'],
                "price": float(tick_data['p']),
                "quantity": float(tick_data['q']),
                "time": datetime.fromtimestamp(tick_data['T'] / 1000)
            })
            conn.commit()
    except Exception as e:
        print(f"⚠️ Error saving raw tick: {e}")

def save_candle_to_db(candle_data):
    """
    Saves the clean, aggregated 1-minute candle to the DB.
    """
    try:
        with engine.connect() as conn:
            query = text("""
                INSERT INTO market_candles (
                    bucket_time, symbol, open, high, low, close, volume, trade_count
                ) VALUES (
                    :time, :symbol, :open, :high, :low, :close, :volume, :count
                ) ON CONFLICT (bucket_time, symbol) DO NOTHING
            """)
            conn.execute(query, {
                "time": candle_data['start_time'],
                "symbol": "BTCUSDT",
                "open": candle_data['open'],
                "high": candle_data['high'],
                "low": candle_data['low'],
                "close": candle_data['close'],
                "volume": candle_data['volume'],
                "count": candle_data['trade_count']
            })
            conn.commit()
        
        print(f"[INFO] Candle Saved: {candle_data['start_time']} | Close: ${candle_data['close']}")
        
    except Exception as e:
        print(f"Error saving candle: {e}")

async def process_message(msg):
    """
    Turn 1,000 fast trades into 1 clean 'candle'.
    """
    global current_candle
    
    # 1. Parse Data
    data = json.loads(msg)
    price = float(data['p'])
    qty = float(data['q'])
    # Convert ms timestamp to seconds
    # Force UTC Timezone
    trade_time = datetime.fromtimestamp(data['T'] / 1000, timezone.utc)
    # Remove the timezone info before saving (Postgres 'timestamp without time zone' expects naive time)
    trade_minute = trade_time.replace(second=0, microsecond=0, tzinfo=None)

    # 2. Logic - Is this a new minute?
    # If start_time is None, it's the first trade we've ever seen. Initialize it.
    if current_candle['start_time'] is None:
        current_candle['start_time'] = trade_minute

    # If the new trade belongs to a FUTURE minute, the old minute is done.
    if trade_minute > current_candle['start_time']:
        # A. Save the COMPLETED candle
        save_candle_to_db(current_candle)

        # B. Reset for the NEW minute
        current_candle = {
            'open': price,      # Open is the price of the first trade of the new minute
            'high': price,
            'low': price,
            'close': price,
            'volume': qty,
            'start_time': trade_minute,
            'trade_count': 1
        }
        print(f"New Minute Started: {trade_minute}")
    
    else:
        # C. Still the SAME minute - Just update stats
        if current_candle['open'] is None: 
            current_candle['open'] = price # Handle very first initialization
            
        current_candle['high'] = max(current_candle['high'], price)
        current_candle['low'] = min(current_candle['low'], price)
        current_candle['close'] = price  # Close is always the latest price
        current_candle['volume'] += qty
        current_candle['trade_count'] += 1

async def connect_to_stream():
    print(f"Connecting to {BINANCE_URL}...")
    
    while True:
        try:
            async with websockets.connect(BINANCE_URL) as websocket:
                print("Connected to Binance Stream!")
                
                while True:
                    message = await websocket.recv()
                    
                    # 1. Save Raw Tick (Audit Trail - Phase 1 Requirement)
                    data = json.loads(message)
                    save_raw_tick(data)
                    
                    # 2. Aggregate Candle (Clean Data - Phase 3 Requirement)
                    await process_message(message)

        except (websockets.ConnectionClosed, Exception) as e:
            print(f"[ERROR] Connection dropped: {e}")
            print("Retrying in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(connect_to_stream())
    except KeyboardInterrupt:
        print("Stopping Stream...")