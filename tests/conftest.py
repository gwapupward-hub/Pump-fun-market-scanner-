from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True, scope="session")
def _set_default_env() -> None:
    """Make `get_settings()` constructible in tests that don't talk to the DB."""
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    # Disable any inherited OPENAI_API_KEY so unit tests stay offline.
    os.environ.pop("OPENAI_API_KEY", None)
    # Reset the settings cache after env mutations.
    from pump_intel.config import get_settings

    get_settings.cache_clear()


FIXTURES = Path(__file__).parent / "fixtures"
