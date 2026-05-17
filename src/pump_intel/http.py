from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

import httpx

log = logging.getLogger(__name__)

T = TypeVar("T")

_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class RetryExhaustedError(RuntimeError):
    """Raised when an HTTP operation exhausts its retry budget."""


def _should_retry(exc: BaseException | None, status: int | None) -> bool:
    if exc is not None:
        return isinstance(exc, (httpx.TransportError, httpx.RemoteProtocolError, httpx.TimeoutException))
    return status is not None and status in _RETRYABLE_STATUS


def _sleep_seconds(attempt: int, base_delay: float, max_delay: float = 30.0) -> float:
    """Exponential backoff with full jitter."""
    exp = min(max_delay, base_delay * (2 ** (attempt - 1)))
    return random.uniform(0.0, exp)


def with_retry(
    *,
    attempts: int,
    base_delay: float,
    op_name: str = "http",
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator: retries an async callable on transient HTTP failures.

    The wrapped callable should perform a single HTTP request and either return
    its result or raise. If the result is an `httpx.Response` with a retryable
    status code, it is treated as a transient failure.
    """

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: BaseException | None = None
            for attempt in range(1, attempts + 1):
                try:
                    result = await fn(*args, **kwargs)
                except httpx.HTTPError as exc:
                    last_exc = exc
                    if attempt >= attempts or not _should_retry(exc, None):
                        raise
                    delay = _sleep_seconds(attempt, base_delay)
                    log.warning(
                        "%s attempt %d/%d failed: %s — retrying in %.2fs",
                        op_name, attempt, attempts, exc, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                if isinstance(result, httpx.Response) and result.status_code in _RETRYABLE_STATUS:
                    if attempt >= attempts:
                        return result
                    delay = _sleep_seconds(attempt, base_delay)
                    log.warning(
                        "%s attempt %d/%d returned %d — retrying in %.2fs",
                        op_name, attempt, attempts, result.status_code, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                return result
            assert last_exc is not None
            raise RetryExhaustedError(f"{op_name} exhausted {attempts} attempts") from last_exc

        return wrapper

    return decorator
