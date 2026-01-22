#!/bin/bash

# Start bb_notes with Docker Compose

set -e

echo "Starting bb_notes..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Warning: .env file not found. Creating from template..."
    cat > .env << EOF
BACKBOARD_API_KEY=your_api_key_here
BACKBOARD_BASE_URL=https://app.backboard.io/api
FLASK_ENV=development
EOF
    echo "Please edit .env file with your configuration before running again."
    exit 1
fi

# Start with docker compose
docker compose up --build
