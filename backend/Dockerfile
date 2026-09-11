FROM python:3.14-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/

# Build the transit database at image build time (DRT + GO).
# This bakes ~50MB of GTFS into the image but means cold starts only
# need to load SQLite into memory, not download and parse feeds.
RUN mkdir -p data
WORKDIR /app/backend
RUN python gtfs_loader.py && python go_loader.py

ENV PYTHONPATH=/app
EXPOSE 8080

# Server starts immediately; router loads in background during lifespan
# so /health answers Railway's healthcheck right away.
CMD cd /app/backend && python -m uvicorn api:app --host 0.0.0.0 --port ${PORT:-8080}
