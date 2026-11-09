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
    PRISM_DB_PATH=/app/data/prism.db

# Create data directory for SQLite persistence.
RUN mkdir -p /app/data && chown -R prism:prism /app/data

# Expose gateway port.
EXPOSE 3000

# Health check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health', timeout=3)" || exit 1

# Run as non-root user.
USER prism

# Start gateway.
CMD ["python", "-m", "uvicorn", "prism.main:app", "--host", "0.0.0.0", "--port", "3000"]
