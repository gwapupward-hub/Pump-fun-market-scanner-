FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64
RUN curl -fsSL -o /usr/local/bin/supercronic "$SUPERCRONIC_URL" \
    && chmod +x /usr/local/bin/supercronic

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY crontab ./crontab
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "pump_intel.run_daily"]
