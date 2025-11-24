# Alpha-Pulse

AI-powered quantitative trading dashboard and real-time data pipeline for cryptocurrency markets.

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

- Collects real-time price ticks via WebSocket (Binance).
- Polls news sources and computes sentiment scores (VADER).
- Stores raw and aggregated data in PostgreSQL.
- Retrains a forecasting model (Prophet) on a rolling window and publishes forecasts.
- Displays live metrics and charts on a Streamlit dashboard.

## Architecture

The system is organized into logical layers:

- **Ingestion**: WebSocket price stream and RSS-based NLP stream.
- **Storage**: PostgreSQL for raw ticks, 1-minute aggregations, and forecast logs.
- **ML Engine**: Periodic retraining (every minute) using a 60-minute rolling window and forecasting the next 60 minutes.
- **Visualization**: Streamlit dashboard with charts and confidence intervals.

### Components

- `etl/ingest_stream.py` — real-time price ingestion.
- `etl/ingest_news.py` — news polling and sentiment scoring.
- `etl/model_engine.py` — prepares data, retrains Prophet, and writes forecasts.
- `dashboard/app.py` — Streamlit app displaying live results.

## Key engineering challenges

- **WebSocket reliability** — handled with an asyncio reconnection loop and exponential/backoff strategy to keep ingestion resilient to drops.
- **Noisy social data** — heuristic filters (account age, deduplication, sanitization) reduce spam influence on sentiment signals.
- **Concept drift** — a 60-minute rolling window balances responsiveness and stability; forward-filling addresses short gaps due to latency.

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

## Contributing

Issues and PRs are welcome. For big changes, open an issue first to discuss the approach.

## License

MIT License
