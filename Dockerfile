# Use a lightweight Python image
FROM python:3.9-slim

# Install system dependencies required for psycopg2 (Postgres driver)
RUN apt-get update && apt-get install -y \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY etl/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Default command (can be overridden in docker-compose)
CMD ["bash"]