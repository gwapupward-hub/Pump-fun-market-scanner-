# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --upgrade pip wheel \
 && pip install ".[ai]"

FROM python:${PYTHON_VERSION}-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}" \
    AUTO_MIGRATE=true

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY docker/entrypoint.sh /usr/local/bin/pump-intel-entrypoint
RUN chmod +x /usr/local/bin/pump-intel-entrypoint && chown -R app:app /app

USER app

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD pump-intel healthcheck || exit 1

ENTRYPOINT ["/usr/local/bin/pump-intel-entrypoint"]
CMD ["pump-intel", "scheduler"]
