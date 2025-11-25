import os
from sqlalchemy import create_engine, text

# --- CONFIGURATION ---
# Defaults to 'localhost' if running locally
db_host = os.getenv("DB_HOST", "localhost")
DB_URL = f"postgresql://user:password@{db_host}:5432/alpha_db"

def reset_database():
    print(f"🔌 Connecting to database at {DB_URL}...")
    try:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            print("🗑️  Wiping all data...")
            
            # Wipes all data and resets the ID counters to 1
            conn.execute(text("TRUNCATE TABLE raw_ticks RESTART IDENTITY;"))
            conn.execute(text("TRUNCATE TABLE market_candles RESTART IDENTITY;"))
            conn.execute(text("TRUNCATE TABLE forecast_logs RESTART IDENTITY;"))
            
            conn.commit()
            print("✅ Database successfully wiped and reset!")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    # Confirmation safety check
    confirm = input("⚠️  WARNING: This will DELETE ALL DATA. Type 'yes' to confirm: ")
    if confirm.lower() == "yes":
        reset_database()
    else:
        print("🚫 Operation cancelled.")