from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row


def connect(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, row_factory=dict_row)


def migrate(conn: psycopg.Connection) -> None:
    from importlib.resources import files

    sql = files("pump_intel.db").joinpath("schema.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


@contextmanager
def db_transaction(conn: psycopg.Connection):
    old_autocommit = conn.autocommit
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = old_autocommit


def json_dumps_safe(obj: Any) -> str:
    return json.dumps(obj, default=str)
