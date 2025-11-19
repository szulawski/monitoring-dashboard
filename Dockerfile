ARG APP_VERSION=local-dev

# Builder stage - install dependencies
FROM python:3.12-slim as builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install security updates
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# Final stage - minimal runtime image
FROM python:3.12-slim
ARG APP_VERSION
LABEL version="${APP_VERSION}" \
      maintainer="monitoring-dashboard" \
      description="Self-hosted runners monitoring dashboard"

WORKDIR /app

# Install security updates and dumb-init
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends dumb-init && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /app/instance && \
    chown -R appuser:appuser /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application files with proper ownership
COPY --chown=appuser:appuser ./app ./app
COPY --chown=appuser:appuser ./migrations ./migrations
COPY --chown=appuser:appuser run.py .
COPY --chown=appuser:appuser entrypoint.sh .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Switch to non-root user
USER appuser

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    APP_VERSION=${APP_VERSION} \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/healthcheck', timeout=5).raise_for_status()" || exit 1

# Use dumb-init to handle signals properly
ENTRYPOINT ["/usr/bin/dumb-init", "--", "./entrypoint.sh"]

CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:8000", "--log-level", "info", "--access-logfile", "-", "--error-logfile", "-", "run:app"]