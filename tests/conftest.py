import pathlib

import pytest

from pump_intel.db.session import reset_engine


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_engine()
    root = pathlib.Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PUMP_INGEST_SOURCE", "fixture")
    monkeypatch.setenv("PUMP_INGEST_FIXTURE_PATH", str(root / "fixtures" / "sample_coins.json"))
    monkeypatch.setenv("AI_SUMMARY_ENABLED", "false")
