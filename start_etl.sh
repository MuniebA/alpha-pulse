#!/bin/bash

# Start the Price Stream in the background
python etl/ingest_stream.py &

# Start the News Stream in the background
python etl/ingest_news.py &

# Start the Model Engine in the background
# We wait 10 seconds to ensure the database is ready and streams are initializing
sleep 10
python etl/model_engine.py &

# Keep the container running
wait