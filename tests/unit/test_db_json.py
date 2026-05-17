from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from pump_intel.db.json import dumps_json


def test_dumps_handles_decimal_and_datetime():
    payload = {
        "amount": Decimal("3.14159"),
        "when": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
        "day": date(2024, 1, 2),
        "uuid": UUID("12345678-1234-5678-1234-567812345678"),
        "set": {1, 2, 3},
        "bytes": b"\xc3\xa9",
    }
    out = dumps_json(payload)
    parsed = json.loads(out)
    assert parsed["amount"] == 3.14159
    assert parsed["when"].startswith("2024-01-02T03:04:05")
    assert parsed["day"] == "2024-01-02"
    assert parsed["uuid"] == "12345678-1234-5678-1234-567812345678"
    assert sorted(parsed["set"]) == [1, 2, 3]
    assert parsed["bytes"] == "é"


def test_dumps_raises_on_truly_unserialisable():
    class Weird:
        pass

    with pytest.raises(TypeError):
        dumps_json({"x": Weird()})
