# =============================================================================
# Stage 1: Build Frontend SPA
# =============================================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# =============================================================================
# Stage 2: Build Python Dependency Wheels
# =============================================================================
FROM python:3.11-slim AS python-builder
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

# =============================================================================
# Stage 3: Production Runtime
# =============================================================================
FROM python:3.11-slim AS runtime
WORKDIR /app

# Create unprivileged system user and group (UID:GID 1000:1000)
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -s /bin/false -m -d /home/appuser appuser

# Install pre-built wheels
COPY --from=python-builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* && \
    rm -rf /wheels

# Copy built frontend assets
COPY --from=frontend-builder /build/dist ./frontend/dist

# Copy application source code and scripts
COPY src/ ./src/
COPY scripts/ ./scripts/

# Create application data and temporary directories owned by appuser
RUN mkdir -p /app/data /tmp && \
    chown -R appuser:appuser /app/data /tmp

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    PORT=8000 \
    DATABASE_PATH=/app/data/index.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; res = urllib.request.urlopen('http://localhost:8000/health', timeout=5); sys.exit(0 if res.getcode() == 200 else 1)"

USER appuser

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
