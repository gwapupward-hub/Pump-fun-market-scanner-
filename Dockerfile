FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY pump_intel ./pump_intel
COPY fixtures ./fixtures

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

# Default: long-running 24h scheduler (override for one-shot: python3 -m pump_intel.cli run-once)
CMD ["python3", "-m", "pump_intel.cli", "serve-scheduler"]
