import feedparser
import time
import datetime
from bs4 import BeautifulSoup
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sqlalchemy import create_engine, text
import os

# --- CONFIGURATION ---
# "Dirty" Data Sources (RSS Feeds)
RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cryptopotato.com/feed/"
]

# Defaults to 'localhost' if not running in Docker
db_host = os.getenv("DB_HOST", "localhost")
DB_URL = f"postgresql://user:password@{db_host}:5432/alpha_db"

# --- SETUP ---
analyzer = SentimentIntensityAnalyzer()
engine = create_engine(DB_URL)

# --- STATE ---
seen_links = set()
current_minute = None
sentiment_buffer = []

def clean_html(dirty_html):
    """
    Phase 2 Goal: Handle messy text data.
    Strips HTML tags (<p>, <a>, <div>) to get raw text.
    """
    soup = BeautifulSoup(dirty_html, "html.parser")
    text = soup.get_text(separator=" ")
    return text.strip()

def update_db_sentiment(bucket_time, avg_score):
    """
    Updates ALL candles matching this time with the global sentiment score.
    """
    try:
        time.sleep(2)
        with engine.connect() as conn:
            # Removed "AND symbol = 'BTCUSDT'"
            # This ensures BTC, ETH, SOL, and XRP candles ALL get the score
            query = text("""
                UPDATE market_candles 
                SET sentiment_score = :score
                WHERE bucket_time = :time 
            """)
            result = conn.execute(query, {
                "score": avg_score,
                "time": bucket_time
            })
            conn.commit()
            
            if result.rowcount > 0:
                print(f"✅ [NEWS] Updated {result.rowcount} candles | Score: {avg_score:.4f}")
            else:
                print(f"⚠️ [NEWS] No candles found for {bucket_time}.")

    except Exception as e:
        print(f"❌ [NEWS] DB Error: {e}")

def process_news_stream():
    global current_minute, sentiment_buffer, seen_links
    print("Polling RSS Feeds for Crypto News...")
    
    while True:
        try:
            # 1. Time Management
            # Force UTC
            now = datetime.datetime.now(datetime.timezone.utc)
            minute_bucket = now.replace(second=0, microsecond=0, tzinfo=None)
            # minute_bucket = now.replace(second=0, microsecond=0)
            
            # Initialize if first run
            if current_minute is None:
                current_minute = minute_bucket

            # 2. Check if we moved to a NEW minute
            if minute_bucket > current_minute:
                # Calculate Average Sentiment for the minute that just finished
                if sentiment_buffer:
                    avg_score = sum(sentiment_buffer) / len(sentiment_buffer)
                    print(f"Minute {current_minute} finished. Avg Sentiment: {avg_score:.4f}")
                    update_db_sentiment(current_minute, avg_score)
                
                # Reset for the new minute
                current_minute = minute_bucket
                sentiment_buffer = []
                print(f"Starting News Bucket: {current_minute}")

            # 3. Poll Feeds (The "Scraping" part)
            for url in RSS_FEEDS:
                feed = feedparser.parse(url)
                
                for entry in feed.entries:
                    # Deduplication Filter (The "Data Science Task")
                    if entry.link in seen_links:
                        continue
                    
                    seen_links.add(entry.link)
                    
                    # Dirty Data Cleaning
                    raw_title = entry.title
                    raw_summary = getattr(entry, 'summary', '')
                    
                    clean_summary = clean_html(raw_summary)
                    full_text = f"{raw_title} {clean_summary}"
                    
                    # Sentiment Scoring
                    score = analyzer.polarity_scores(full_text)['compound']
                    sentiment_buffer.append(score)
                    
                    print(f"   New Article: {raw_title[:50]}... (Score: {score})")

            # Wait 30 seconds before polling again to avoid spamming
            time.sleep(30)

        except Exception as e:
            print(f"Error polling feeds: {e}")
            time.sleep(30)

if __name__ == "__main__":
    process_news_stream()