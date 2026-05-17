from __future__ import annotations

from pathlib import Path

import psycopg


def apply_schema(dsn: str, schema_path: Path | None = None) -> None:
    if schema_path is None:
        schema_path = Path(__file__).resolve().parent / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
