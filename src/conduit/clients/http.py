"""Shared HTTP plumbing: one place that knows how to fail properly.

Every outbound call goes through :class:`HttpService`, which gives it a
connection pool, a rate limiter, retries with jittered backoff and a circuit
breaker -- and, crucially, translates HTTP status codes into the *right kind*
of exception so callers can tell "no results" apart from "the tracker is
rate-limiting you" or "your API key is wrong".
"""

from __future__ import annotations

from typing import Any

import httpx

from ..logs import get_logger
from ..util.resilience import (
    CircuitBreaker,
    PermanentError,
    RateLimited,
    RateLimiter,
    RetryPolicy,
    TransientError,
    retry,
)

log = get_logger("http")

DEFAULT_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)


class NotFound(PermanentError):
    """The resource does not exist (404)."""


class HttpService:
    """A configured httpx client for one upstream service."""

    def __init__(
        self,
        name: str,
        base_url: str = "",
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 20.0,
        rate_per_minute: int = 0,
        verify: bool = True,
        retry_policy: RetryPolicy | None = None,
        breaker_threshold: int = 5,
        breaker_recovery: float = 60.0,
        follow_redirects: bool = True,
        connect_timeout: float = 5.0,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.limiter = RateLimiter(rate_per_minute)
        self.breaker = CircuitBreaker(
            name, threshold=breaker_threshold, recovery_seconds=breaker_recovery
        )
        self.retry_policy = retry_policy or RetryPolicy()
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers or {},
            # A host that cannot complete a TCP handshake in five seconds is
            # not about to serve a search either. Waiting ten made a struggling
            # tracker cost 30+ seconds once retries were applied.
            timeout=httpx.Timeout(timeout, connect=min(timeout, connect_timeout)),
            verify=verify,
            limits=DEFAULT_LIMITS,
            follow_redirects=follow_redirects,
        )

    # -- lifecycle ----------------------------------------------------------
    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> HttpService:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    def health(self) -> dict[str, Any]:
        return self.breaker.snapshot()

    # -- core ---------------------------------------------------------------
    async def request(
        self,
        method: str,
        url: str,
        *,
        allow_404: bool = False,
        policy: RetryPolicy | None = None,
        **kwargs: Any,
    ) -> httpx.Response | None:
        """Perform a request with the full resilience stack applied.

        Returns ``None`` only when ``allow_404`` is set and the resource is
        genuinely missing -- every other failure raises. Pass ``policy`` to
        override retries for a call that must stay snappy (anything a user is
        waiting on) rather than thorough.
        """

        async def attempt() -> httpx.Response | None:
            await self.limiter.acquire()
            try:
                response = await self._client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise TransientError(f"{self.name}: {type(exc).__name__}: {exc}") from exc
            except httpx.HTTPError as exc:
                raise TransientError(f"{self.name}: {exc}") from exc
            return self._check(response, allow_404=allow_404)

        return await self.breaker.call(
            lambda: retry(
                attempt,
                policy=policy or self.retry_policy,
                name=f"{self.name} {method} {url}",
            )
        )

    def _check(self, response: httpx.Response, *, allow_404: bool) -> httpx.Response | None:
        status = response.status_code
        if status < 400:
            return response
        if status == 404:
            if allow_404:
                return None
            raise NotFound(f"{self.name}: 404 for {response.request.url}")
        if status == 429:
            retry_after = response.headers.get("Retry-After")
            wait: float | None = None
            if retry_after:
                try:
                    wait = float(retry_after)
                except ValueError:
                    wait = None
            raise RateLimited(f"{self.name}: rate limited", retry_after=wait)
        if status in (401, 403):
            raise PermanentError(
                f"{self.name}: authentication rejected ({status}). Check the API key."
            )
        if status in (400, 422):
            raise PermanentError(
                f"{self.name}: bad request ({status}): {response.text[:200]}"
            )
        raise TransientError(f"{self.name}: HTTP {status}: {response.text[:200]}")

    # -- convenience --------------------------------------------------------
    async def get_json(self, url: str, *, allow_404: bool = False, **kwargs: Any) -> Any:
        response = await self.request("GET", url, allow_404=allow_404, **kwargs)
        if response is None:
            return None
        return _parse_json(self.name, response)

    async def post_json(self, url: str, *, allow_404: bool = False, **kwargs: Any) -> Any:
        response = await self.request("POST", url, allow_404=allow_404, **kwargs)
        if response is None:
            return None
        return _parse_json(self.name, response)

    async def get_bytes(self, url: str, *, allow_404: bool = False, **kwargs: Any) -> bytes | None:
        response = await self.request("GET", url, allow_404=allow_404, **kwargs)
        return response.content if response is not None else None


def _parse_json(service: str, response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        snippet = response.text[:200].replace("\n", " ")
        raise TransientError(f"{service}: response was not JSON: {snippet}") from exc
