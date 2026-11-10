# Production Container for Sui DeepBookV3 & Cetus Multi-Pair Arbitrage Engine
# Continuous Deployment on Railway (Frankfurt europe-west3)

FROM python:3.11-slim

# Prevent Python from writing bytecode and enable unbuffered standard streams
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PYTHONPATH=/app

WORKDIR /app

# Install minimal OS dependencies for network operations and curl healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt aiohttp

# Copy application source code
COPY . /app/

# Create dedicated non-root user and group for hardened production execution
RUN groupadd -r trader && useradd -r -g trader -d /app -s /sbin/nologin trader && \
    chown -R trader:trader /app

# Switch to non-root user
USER trader

# Expose Railway supervision port
EXPOSE 8080

# Health check matching GET /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# Production Entrypoint
CMD ["python", "venues/sui_bot_runner.py"]
