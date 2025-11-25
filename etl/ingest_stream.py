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

# List of symbols to track (Lower case for Binance URL)
SYMBOLS = ["btcusdt", "ethusdt", "solusdt", "xrpusdt"]
# Construct combined stream URL (e.g. stream?streams=btcusdt@trade/ethusdt@trade)
STREAMS = "/".join([f"{s}@trade" for s in SYMBOLS])
BINANCE_URL = f"wss://stream.binance.com:9443/stream?streams={STREAMS}"

# --- DATABASE CONNECTION ---
engine = create_engine(DB_URL)

# --- GLOBAL STATE (Multi-Symbol Aggregation) ---
# Key: Symbol (e.g., 'BTCUSDT'), Value: Candle Dict
active_candles = {}

def get_empty_candle():
    return {
        'open': None, 'high': float('-inf'), 'low': float('inf'),
        'close': None, 'volume': 0.0, 'start_time': None, 'trade_count': 0
    }

def save_raw_tick(tick_data):
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

def save_candle_to_db(symbol, candle_data):
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
                "symbol": symbol,  # <--- NOW DYNAMIC
                "open": candle_data['open'],
                "high": candle_data['high'],
                "low": candle_data['low'],
                "close": candle_data['close'],
                "volume": candle_data['volume'],
                "count": candle_data['trade_count']
            })
            conn.commit()
        print(f"✅ [{symbol}] Candle Saved: {candle_data['start_time']} | Close: ${candle_data['close']}")
    except Exception as e:
        print(f"❌ Error saving candle: {e}")

async def process_message(msg):
    global active_candles
    
    # Parse Combined Stream Data
    # Format: {"stream": "btcusdt@trade", "data": {...}}
    payload = json.loads(msg)
    data = payload['data']
    
    symbol = data['s'] # e.g., "BTCUSDT"
    price = float(data['p'])
    qty = float(data['q'])
    
    # Force UTC Timezone
    trade_time = datetime.fromtimestamp(data['T'] / 1000, timezone.utc)
    trade_minute = trade_time.replace(second=0, microsecond=0, tzinfo=None)

    # Initialize state for this symbol if it doesn't exist yet
    if symbol not in active_candles:
        active_candles[symbol] = get_empty_candle()

    current = active_candles[symbol]

    # 1. Logic - Is this a new minute?
    if current['start_time'] is None:
        current['start_time'] = trade_minute

    if trade_minute > current['start_time']:
        # Save completed candle for this specific symbol
        save_candle_to_db(symbol, current)
        
        # Reset for new minute
        active_candles[symbol] = {
            'open': price, 'high': price, 'low': price, 'close': price,
            'volume': qty, 'start_time': trade_minute, 'trade_count': 1
        }
        print(f"🔄 [{symbol}] New Minute: {trade_minute}")
    else:
        # Update existing candle
        if current['open'] is None: current['open'] = price
        current['high'] = max(current['high'], price)
        current['low'] = min(current['low'], price)
        current['close'] = price
        current['volume'] += qty
        current['trade_count'] += 1

async def connect_to_stream():
    print(f"Connecting to multi-stream: {BINANCE_URL}...")
    while True:
        try:
            async with websockets.connect(BINANCE_URL) as websocket:
                print("✅ Connected to Binance Multi-Stream!")
                while True:
                    message = await websocket.recv()
                    # Note: save_raw_tick logic is now best handled inside process_message 
                    # because we need to parse the 'data' wrapper first.
                    # So we just call process_message.
                    await process_message(message)
        except (websockets.ConnectionClosed, Exception) as e:
            print(f"❌ Connection lost: {e}. Retrying in 5s...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(connect_to_stream())
    except KeyboardInterrupt:
        print("Stopping Stream...")