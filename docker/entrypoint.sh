#!/usr/bin/env bash
set -euo pipefail

# When invoked for the scheduler / run-job, optionally apply migrations first.
# Disable by setting AUTO_MIGRATE=false (e.g. when running the dedicated migrate service).
if [[ "${AUTO_MIGRATE:-true}" == "true" ]]; then
  case "${1:-}" in
    pump-intel)
      case "${2:-}" in
        init-db|healthcheck) ;;
        *)
          echo "[entrypoint] applying alembic migrations…" >&2
          alembic upgrade head
          ;;
      esac
      ;;
    alembic)
      ;;
  esac
fi

exec "$@"
