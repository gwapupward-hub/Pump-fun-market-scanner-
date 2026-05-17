from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator, Iterable, Sequence

import psycopg
from psycopg.rows import dict_row

from pump_intel.config import get_settings

log = logging.getLogger(__name__)


def connect():
    settings = get_settings()
    return psycopg.connect(settings.database_url)


@contextmanager
def cursor_dict(conn) -> Generator:
    with conn.cursor(row_factory=dict_row) as cur:
        yield cur


def apply_schema(conn) -> None:
    """Apply bundled SQL schema if tables are missing."""
    from importlib.resources import files

    sql_text = files("pump_intel").joinpath("schema.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql_text)
    conn.commit()


def init_db() -> None:
    with connect() as conn:
        apply_schema(conn)


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.tokens')")
        row = cur.fetchone()
    if row is None or row[0] is None:
        log.info("Applying initial schema")
        apply_schema(conn)


def fetch_all_dict(conn, sql: str, params: Sequence[object] | None = None) -> list[dict]:
    with cursor_dict(conn) as cur:
        cur.execute(sql, [] if params is None else params)
        return list(cur.fetchall())


def fetch_one_dict(conn, sql: str, params: Sequence[object] | None = None) -> dict | None:
    with cursor_dict(conn) as cur:
        cur.execute(sql, [] if params is None else params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute(conn, sql: str, params: Sequence[object] | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(sql, [] if params is None else params)
    conn.commit()


def executemany(conn, sql: str, rows: Iterable[Sequence[object]]) -> None:
    rows_list = list(rows)
    if not rows_list:
        return
    with conn.cursor() as cur:
        cur.executemany(sql, rows_list)
    conn.commit()
