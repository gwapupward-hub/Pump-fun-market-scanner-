#!/bin/sh
set -eu
python -m pump_intel init-db
exec "$@"
