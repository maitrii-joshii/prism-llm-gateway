# ============================================================
# Stage 1: Builder
# ============================================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install dependencies into a separate directory.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Copy application code.
COPY . .


# ============================================================
# Stage 2: Production
# ============================================================
FROM python:3.12-slim AS production

# Create non-root user for security.
RUN groupadd -r prism && useradd -r -g prism prism

WORKDIR /app

# Copy dependencies into the system-wide Python installation.
COPY --from=builder /install/ /usr/local/

# Copy application code.
COPY --from=builder /app .

# Application environment defaults.
ENV PORT=3000 \
    PRISM_PORT=3000 \
    PRISM_LOG_LEVEL=INFO \
    PRISM_CONFIG_DIR=/app/data \
    PRISM_DB_PATH=/app/dbdata/prism.db

# SQLite lives in its own directory so a volume can persist it without
# shadowing the read-only starter data in /app/data.
RUN mkdir -p /app/dbdata && chown -R prism:prism /app

# Expose gateway port.
EXPOSE 3000

# Health check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, os; port=os.environ.get('PORT', '3000'); urllib.request.urlopen(f'http://localhost:{port}/health', timeout=3)" || exit 1

# Run as non-root user.
USER prism

# Start gateway with dynamic port support.
CMD ["sh", "-c", "python -m uvicorn prism.main:app --host 0.0.0.0 --port ${PORT:-3000}"]
