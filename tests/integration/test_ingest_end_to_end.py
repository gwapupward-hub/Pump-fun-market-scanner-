from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from httpx import Response

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pump_coins.json"


@pytest.fixture()
def pump_api(monkeypatch):
    """Mount respx mocks for the Pump API. Disables Solana RPC."""
    monkeypatch.setenv("PUMP_API_BASE", "https://pump.test")
    monkeypatch.delenv("SOLANA_RPC_URL", raising=False)
    from pump_intel.config import get_settings

    get_settings.cache_clear()

    coins = json.loads(FIXTURE.read_text())
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://pump.test/sol-price").mock(return_value=Response(200, json={"solPrice": 200.0}))
        # Single page: respond with all coins on the first call, empty list on subsequent.
        mock.get("https://pump.test/coins").mock(
            side_effect=[
                Response(200, json=coins),
                Response(200, json=[]),
            ]
        )
        yield mock


@pytest.mark.asyncio
async def test_ingest_writes_tokens_and_snapshots(pump_api, db_conn):
    from pump_intel.ingestion.service import ingest_latest_coins

    stats = await ingest_latest_coins()
    assert stats["raw_coins"] == 5
    # 2 coins should be rejected (bad timestamp, missing creator).
    assert stats["rejected_coins"] == 2
    assert stats["unique_mints"] == 3
    assert stats["snapshots_written"] == 3

    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM tokens")
        assert cur.fetchone()[0] == 3
        cur.execute("SELECT COUNT(*) FROM token_snapshots")
        assert cur.fetchone()[0] == 3
        cur.execute("SELECT COUNT(*) FROM token_socials")
        # 3 mints × 3 platforms.
        assert cur.fetchone()[0] == 9


@pytest.mark.asyncio
async def test_ingest_is_idempotent_via_staleness(pump_api, db_conn):
    from pump_intel.ingestion.service import ingest_latest_coins

    await ingest_latest_coins()
    # Re-mount the same mocks for the second pass.
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM token_snapshots")
        first = cur.fetchone()[0]

    stats2 = await ingest_latest_coins()
    # Default stale window is 86400s → no new snapshot rows on the second run.
    assert stats2["snapshots_written"] == 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM token_snapshots")
        assert cur.fetchone()[0] == first
