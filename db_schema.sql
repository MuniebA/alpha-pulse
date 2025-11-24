-- ==========================================
-- Alpha-Pulse Database Schema
-- ==========================================

-- 1. RAW TICKS TABLE (The "Audit Trail")
-- This stores every single raw trade message exactly as it comes in from the WebSocket.
-- We use DOUBLE PRECISION for price/qty to handle crypto decimals accurately.
-- This table grows very fast, so in a real production environment, you would partition it by day.
CREATE TABLE IF NOT EXISTS raw_ticks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,     -- e.g., 'BTCUSDT'
    price DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    trade_time TIMESTAMP,            -- Time the trade happened on Binance
    ingest_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- Time we received it (for latency checks)
);

-- 2. MARKET CANDLES TABLE (The "Clean Data")
-- This stores the aggregated 1-minute bars (OHLCV).
-- This is the source of truth for the ML model and the Dashboard.
CREATE TABLE IF NOT EXISTS market_candles (
    bucket_time TIMESTAMP NOT NULL,  -- e.g., 2025-11-20 12:01:00 (Start of the minute)
    symbol VARCHAR(20) NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION DEFAULT 0,
    trade_count INT DEFAULT 0,
    sentiment_score FLOAT DEFAULT 0, -- Populated by the NLP service (ingest_news.py)
    
    -- Composite Primary Key: Ensures we don't have duplicate candles for the same time+symbol
    PRIMARY KEY (bucket_time, symbol)
);

-- 3. FORECAST LOGS TABLE (The "AI Output")
-- Stores the predictions made by your Prophet model.
-- 'execution_time' allows us to track how the model's opinion changes over time.
CREATE TABLE IF NOT EXISTS forecast_logs (
    id SERIAL PRIMARY KEY,
    execution_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- When the model ran
    forecast_time TIMESTAMP NOT NULL,                   -- The future time we are predicting
    predicted_price DOUBLE PRECISION NOT NULL,
    lower_bound DOUBLE PRECISION,                       -- Confidence Interval (Low)
    upper_bound DOUBLE PRECISION                        -- Confidence Interval (High)
);

-- ==========================================
-- OPTIONAL: Indexes for Performance
-- ==========================================

-- Index for faster querying of recent candles (used by Dashboard & ML Engine)
CREATE INDEX IF NOT EXISTS idx_candles_time ON market_candles (bucket_time DESC);

-- Index for querying forecasts by execution batch
CREATE INDEX IF NOT EXISTS idx_forecast_exec ON forecast_logs (execution_time DESC);