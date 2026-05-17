from __future__ import annotations

import atexit
import logging
import threading
from collections.abc import Generator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

from pump_intel.config import get_settings

log = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def get_pool() -> ConnectionPool:
    """Return a process-wide lazily-initialised psycopg connection pool."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                s = get_settings()
                _pool = ConnectionPool(
                    conninfo=s.database_url,
                    min_size=s.db_pool_min_size,
                    max_size=s.db_pool_max_size,
                    timeout=s.db_pool_timeout_s,
                    kwargs={"application_name": "pump-intel"},
                    open=True,
                )
                atexit.register(_close_pool)
                log.info(
                    "db pool opened",
                    extra={"min_size": s.db_pool_min_size, "max_size": s.db_pool_max_size},
                )
    return _pool


def _close_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:  # pragma: no cover — best-effort on shutdown
            log.exception("error closing db pool")
        finally:
            _pool = None


@contextmanager
def transaction() -> Generator[psycopg.Connection, None, None]:
    """Borrow a connection from the pool, wrap the block in a single transaction.

    Commits on clean exit, rolls back on any exception, always returns the
    connection to the pool.
    """
    pool = get_pool()
    with pool.connection() as conn:
        # psycopg's pool.connection() commits on clean exit and rolls back on error.
        yield conn


__all__ = ["get_pool", "transaction"]
