# syntax=docker/dockerfile:1

FROM python:3.10-slim

# Prevent Python from writing pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# system deps (add if you need ffmpeg, build-essential, libgl1 etc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY ui/requirements.txt ./ui/requirements.txt

# Install pip dependencies (use --no-cache-dir in production)
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r ui/requirements.txt

# Copy the UI code
COPY ui/ ./ui/

# Add entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose common ports (Streamlit default 8501, FastAPI/Flask default 8000)
EXPOSE 8501 8000

# Default env vars (can be overridden at runtime)
ENV APP_MODULE="app:app" \
    APP_TYPE="streamlit" \
    PORT=8501 \
    PYTHONPATH="/app/ui"

# Entrypoint handles which server to start
ENTRYPOINT ["/entrypoint.sh"]
