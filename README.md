# Alpha-Pulse

AI-powered quantitative trading dashboard and real-time data pipeline for cryptocurrency markets.

<img width="1894" height="824" alt="image" src="https://github.com/user-attachments/assets/9fed6503-3c58-4d43-9555-94d99bfda526" />


Alpha-Pulse ingests live market data and news sentiment, runs a rolling-window forecasting model, and serves visualizations through a Streamlit dashboard.

## Table of contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Key engineering challenges](#key-engineering-challenges)
- [Setup & Run](#setup--run)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Contributing](#contributing)

## Overview

This project demonstrates a full-stack, containerized pipeline that:

- Collects real-time price ticks via WebSocket (Binance) for multiple assets (BTC, ETH, SOL, XRP).
- Polls news sources and computes sentiment scores (VADER).
- Stores raw and aggregated data in PostgreSQL.
- Retrains a forecasting model (Prophet) on a rolling window and publishes forecasts.
- Displays live metrics and charts on a Streamlit dashboard with a multi-currency selector.

## Architecture

The system is organized into logical layers:

- **Ingestion**: WebSocket price stream and RSS-based NLP stream.
- **Storage**: PostgreSQL for raw ticks, 1-minute aggregations, and forecast logs.
- **ML Engine**: Periodic retraining (every minute) using a 60-minute rolling window and forecasting the next 60 minutes.
- **Visualization**: Streamlit dashboard with charts, confidence intervals, and dynamic asset selection.

### Components

- `etl/ingest_stream.py` — real-time price ingestion for multiple cryptocurrency pairs.
- `etl/ingest_news.py` — news polling and sentiment scoring.
- `etl/model_engine.py` — prepares data, retrains Prophet, and writes forecasts.
- `dashboard/app.py` — Streamlit app displaying live results with filtering options.

## Key engineering challenges

- **WebSocket reliability** — handled with an asyncio reconnection loop and exponential/backoff strategy to keep ingestion resilient to drops.
- **Noisy social data** — heuristic filters (account age, deduplication, sanitization) reduce spam influence on sentiment signals.
- **Concept drift** — a 60-minute rolling window balances responsiveness and stability; forward-filling addresses short gaps due to latency.
- **Multi-Asset Scaling** — designed the schema and pipeline to handle concurrent data streams for different assets without blocking or cross-contamination.

## Setup & Run

Prerequisites:

- Docker & Docker Compose
- (Optional) Python 3.9+ for running components locally

Clone the repo:

```powershell
git clone https://github.com/MuniebA/alpha-pulse.git
cd alpha-pulse
```

Start the stack with Docker Compose:

```powershell
docker-compose up --build -d
```

Open the dashboard in your browser:

```text
http://localhost:8501
```

Notes:

- If you prefer to run pieces locally (without Docker), create a Python virtualenv and install `etl/requirements.txt`.
- The Postgres data directory is present in `pgdata/` for local development.

## Tech stack

- Python 3.9+
- PostgreSQL
- Docker & Docker Compose
- Prophet (for forecasting)
- Streamlit & Plotly
- AsyncIO & WebSockets

## Project structure

- `dashboard/` — Streamlit app
- `etl/` — ingestion and ML engine scripts
- `pgdata/` — local Postgres data directory
- `sql/` — DB Schema

## Contributing

Issues and PRs are welcome. For big changes, open an issue first to discuss the approach.

## License

MIT License
