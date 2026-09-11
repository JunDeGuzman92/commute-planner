FROM python:3.14-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/

# Create data directory (GTFS will be downloaded at startup)
RUN mkdir -p data

ENV PYTHONPATH=/app
EXPOSE 8080

# Download GTFS on first run, then start server
CMD cd /app/backend && python gtfs_loader.py && python go_loader.py && python -m uvicorn api:app --host 0.0.0.0 --port ${PORT:-8080}
