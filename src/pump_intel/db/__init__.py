"""Database helpers.

Connections are issued from a process-wide pool (`pump_intel.db.pool`). Helpers
in this module do **not** commit on their own — wrap calls in a `transaction()`
block (or `with get_pool().connection() as conn` / a connection borrowed
elsewhere). This makes multi-statement units atomic.
"""
from __future__ import annotations

import logging
from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from pump_intel.db.json import dumps_json, jsonb
from pump_intel.db.pool import get_pool, transaction

log = logging.getLogger(__name__)


@contextmanager
def cursor_dict(conn: psycopg.Connection) -> Generator[psycopg.Cursor[dict], None, None]:
    with conn.cursor(row_factory=dict_row) as cur:
        yield cur


def fetch_all_dict(
    conn: psycopg.Connection, sql: str, params: Sequence[object] | None = None
) -> list[dict]:
    with cursor_dict(conn) as cur:
        cur.execute(sql, [] if params is None else params)
        return list(cur.fetchall())


def fetch_one_dict(
    conn: psycopg.Connection, sql: str, params: Sequence[object] | None = None
) -> dict | None:
    with cursor_dict(conn) as cur:
        cur.execute(sql, [] if params is None else params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute(
    conn: psycopg.Connection, sql: str, params: Sequence[object] | None = None
) -> None:
    """Execute a single statement on *conn*. Caller controls the transaction boundary."""
    with conn.cursor() as cur:
        cur.execute(sql, [] if params is None else params)


def executemany(
    conn: psycopg.Connection, sql: str, rows: Iterable[Sequence[object]]
) -> int:
    rows_list = list(rows)
    if not rows_list:
        return 0
    with conn.cursor() as cur:
        cur.executemany(sql, rows_list)
    return len(rows_list)


def init_db() -> None:
    """Run alembic migrations up to head."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parents[3]
    cfg_path = repo_root / "alembic.ini"
    if not cfg_path.exists():
        # When installed as a wheel, alembic.ini ships at the package root.
        cfg_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    cfg = Config(str(cfg_path))
    command.upgrade(cfg, "head")


__all__ = [
    "cursor_dict",
    "dumps_json",
    "execute",
    "executemany",
    "fetch_all_dict",
    "fetch_one_dict",
    "get_pool",
    "init_db",
    "jsonb",
    "transaction",
]
