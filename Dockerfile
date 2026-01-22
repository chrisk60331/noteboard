FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./
COPY uv.lock* ./

# Install dependencies
RUN if [ -f uv.lock ]; then uv sync --frozen; else uv sync; fi

# Copy application code
COPY . .

# Expose port
EXPOSE 9000

# Run the application
CMD ["uv", "run", "python", "run.py"]
