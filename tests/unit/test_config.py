from __future__ import annotations


def test_blank_openai_envvars_coerce_to_none(monkeypatch):
    """docker-compose interpolates unset env vars as `""`. Without coercion,
    OpenAI(base_url="") would 404 at request time.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@x:5432/x")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "   ")

    from pump_intel.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    assert s.openai_api_key is None
    assert s.openai_base_url is None


def test_blank_solana_url_coerces_to_none(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@x:5432/x")
    monkeypatch.setenv("SOLANA_RPC_URL", "")

    from pump_intel.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    assert s.solana_rpc_url is None
