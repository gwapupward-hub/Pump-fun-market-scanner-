from __future__ import annotations

import httpx
import pytest

from pump_intel.http import RetryExhaustedError, with_retry


@pytest.mark.asyncio
async def test_retries_transient_errors():
    calls = 0

    @with_retry(attempts=3, base_delay=0.01, op_name="test")
    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectError("boom")
        return "ok"

    assert await flaky() == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_exhausts_and_raises():
    @with_retry(attempts=2, base_delay=0.01, op_name="test")
    async def always_fails():
        raise httpx.ConnectError("nope")

    with pytest.raises((httpx.ConnectError, RetryExhaustedError)):
        await always_fails()


@pytest.mark.asyncio
async def test_retries_on_5xx_response():
    calls = 0

    def _resp(status: int) -> httpx.Response:
        return httpx.Response(status_code=status, request=httpx.Request("GET", "http://t"))

    @with_retry(attempts=3, base_delay=0.01, op_name="test")
    async def flaky():
        nonlocal calls
        calls += 1
        return _resp(503) if calls < 3 else _resp(200)

    resp = await flaky()
    assert calls == 3
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_non_retryable_returned_as_is():
    @with_retry(attempts=3, base_delay=0.01, op_name="test")
    async def returns_400():
        return httpx.Response(status_code=400, request=httpx.Request("GET", "http://t"))

    resp = await returns_400()
    assert resp.status_code == 400
