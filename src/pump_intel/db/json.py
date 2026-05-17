from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def _default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def dumps_json(obj: Any) -> str:
    return json.dumps(obj, default=_default, ensure_ascii=False, separators=(",", ":"))


def jsonb(obj: Any):
    """Wrap *obj* for safe JSONB insertion via psycopg `Json` with Decimal/datetime handling."""
    from psycopg.types.json import Json

    return Json(obj, dumps=dumps_json)
