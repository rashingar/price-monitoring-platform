from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import httpx

from ..fetcher import CRAWL_TIMEOUT, ElectronetFetcher, FetchError, USER_AGENT
from ..models import FetchResult


class SkroutzFetchStatus(str, Enum):
    OK = "ok"
    BLOCKED_BY_CHALLENGE = "blocked_by_challenge"


@dataclass(slots=True)
class SkroutzFetchResult:
    url: str
    final_url: str
    html: str
    status_code: int
    method: str = "httpx"
    fallback_used: bool = False
    status: SkroutzFetchStatus = SkroutzFetchStatus.OK
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def blocked_reason(self) -> str:
        if self.status == SkroutzFetchStatus.BLOCKED_BY_CHALLENGE:
            return self.status.value
        return ""

    @property
    def blocked(self) -> bool:
        return self.status == SkroutzFetchStatus.BLOCKED_BY_CHALLENGE


_CHALLENGE_STATUS_CODES = {403, 429, 503}
_CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "enable javascript and cookies",
    "challenges.cloudflare.com",
    "cf-browser-verification",
    "cf_chl",
    "cf-ray",
    "cf-mitigated",
    "cloudflare",
)


def is_skroutz_challenge_html(html: str, *, status_code: int = 0, headers: dict[str, str] | None = None) -> bool:
    lowered = (html or "").lower()
    header_values = " ".join(str(value).lower() for value in (headers or {}).values())
    marker_present = any(marker in lowered or marker in header_values for marker in _CHALLENGE_MARKERS)
    if status_code in _CHALLENGE_STATUS_CODES and marker_present:
        return True
    title_challenge = "<title>just a moment" in lowered or "please wait while your request is being verified" in lowered
    return title_challenge and marker_present


class SkroutzSnapshotFetcher:
    def __init__(
        self,
        *,
        user_agent: str = USER_AGENT,
        timeout: httpx.Timeout = CRAWL_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
        browser_fetcher: ElectronetFetcher | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.transport = transport
        self.browser_fetcher = browser_fetcher or ElectronetFetcher(user_agent=user_agent, timeout=timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        }

    def fetch(self, url: str) -> SkroutzFetchResult:
        if self.transport is not None:
            return self._fetch_httpx_direct(url)

        playwright_challenge: SkroutzFetchResult | None = None
        try:
            playwright_result = self._from_fetch_result(self.browser_fetcher.fetch_playwright(url))
            if not playwright_result.blocked:
                return playwright_result
            playwright_challenge = playwright_result
        except FetchError:
            playwright_challenge = None

        try:
            httpx_result = self._from_fetch_result(self.browser_fetcher.fetch_httpx(url))
            if not httpx_result.blocked:
                return httpx_result
            return playwright_challenge or httpx_result
        except FetchError as exc:
            if playwright_challenge is not None:
                return playwright_challenge
            raise FetchError(f"Skroutz fetch failed for {url}: {exc}") from exc

    def _fetch_httpx_direct(self, url: str) -> SkroutzFetchResult:
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers=self._headers(),
                transport=self.transport,
            ) as client:
                response = client.get(url)
        except Exception as exc:
            raise FetchError(f"Skroutz HTTP fetch failed for {url}: {exc}") from exc

        headers = {str(key): str(value) for key, value in response.headers.items()}
        status = (
            SkroutzFetchStatus.BLOCKED_BY_CHALLENGE
            if is_skroutz_challenge_html(response.text, status_code=response.status_code, headers=headers)
            else SkroutzFetchStatus.OK
        )
        if status == SkroutzFetchStatus.OK:
            try:
                response.raise_for_status()
            except Exception as exc:
                raise FetchError(f"Skroutz HTTP fetch failed for {url}: {exc}") from exc

        return SkroutzFetchResult(
            url=url,
            final_url=str(response.url),
            html=response.text,
            status_code=response.status_code,
            method="httpx",
            fallback_used=False,
            status=status,
            headers=headers,
        )

    def _from_fetch_result(self, fetch: FetchResult) -> SkroutzFetchResult:
        headers = {str(key): str(value) for key, value in fetch.response_headers.items()}
        status = (
            SkroutzFetchStatus.BLOCKED_BY_CHALLENGE
            if is_skroutz_challenge_html(fetch.html, status_code=fetch.status_code, headers=headers)
            else SkroutzFetchStatus.OK
        )
        return SkroutzFetchResult(
            url=fetch.url,
            final_url=fetch.final_url,
            html=fetch.html,
            status_code=fetch.status_code,
            method=fetch.method,
            fallback_used=fetch.fallback_used,
            status=status,
            headers=headers,
        )
