"""Safe Playwright browser session for supervised URL discovery."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class PageSnapshot:
    requested_url: str
    final_url: str
    title: str
    html: str
    body_text: str
    links: tuple[str, ...] = field(default_factory=tuple)
    status: str = "success"
    error_code: str = ""
    error_message: str = ""


class SourceUrlBrowserSession:
    """Reusable Chromium session with per-domain throttling."""

    def __init__(
        self,
        *,
        headed: bool = False,
        no_browser_cache: bool = False,
        default_rate_limit_seconds: float = 2.0,
        navigation_timeout_ms: int = 30000,
        page_ready_timeout_ms: int = 1200,
    ) -> None:
        self.headed = headed
        self.no_browser_cache = no_browser_cache
        self.default_rate_limit_seconds = max(0.0, float(default_rate_limit_seconds))
        self.navigation_timeout_ms = int(navigation_timeout_ms)
        self.page_ready_timeout_ms = int(page_ready_timeout_ms)
        self._playwright = None
        self._browser = None
        self._context = None
        self._last_request_by_domain: dict[str, float] = {}

    def __enter__(self) -> "SourceUrlBrowserSession":
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=not self.headed)
        context_options = {
            "locale": "el-GR",
            "timezone_id": "Europe/Athens",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
        }
        self._context = self._browser.new_context(**context_options)
        self._context.set_default_navigation_timeout(self.navigation_timeout_ms)
        self._context.set_default_timeout(self.navigation_timeout_ms)
        if self.no_browser_cache:
            self._context.clear_cookies()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._context = None
        self._browser = None
        self._playwright = None

    def fetch_snapshot(self, url: str, *, rate_limit_seconds: float | None = None) -> PageSnapshot:
        if self._context is None:
            raise RuntimeError("browser session is not open")
        self._throttle(url, rate_limit_seconds)
        page = self._context.new_page()
        page.set_default_navigation_timeout(self.navigation_timeout_ms)
        page.set_default_timeout(self.navigation_timeout_ms)
        try:
            response = page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(self.page_ready_timeout_ms)
            title = page.title()
            html = page.content()
            body_text = page.locator("body").inner_text(timeout=5000)
            links = tuple(
                str(item)
                for item in page.eval_on_selector_all("a[href]", "elements => elements.map(element => element.href)")
            )
            status_code = response.status if response is not None else None
            if _blocked_or_captcha(title, body_text, html):
                return PageSnapshot(
                    requested_url=url,
                    final_url=page.url,
                    title=title,
                    html=html,
                    body_text=body_text,
                    links=links,
                    status="error",
                    error_code="blocked_or_captcha",
                    error_message="Blocked page or CAPTCHA marker detected.",
                )
            if status_code is not None and status_code >= 400:
                return PageSnapshot(
                    requested_url=url,
                    final_url=page.url,
                    title=title,
                    html=html,
                    body_text=body_text,
                    links=links,
                    status="error",
                    error_code=f"http_{status_code}",
                    error_message=f"HTTP {status_code}",
                )
            return PageSnapshot(
                requested_url=url,
                final_url=page.url,
                title=title,
                html=html,
                body_text=body_text,
                links=links,
            )
        except Exception as exc:
            code = _error_code(exc)
            return PageSnapshot(
                requested_url=url,
                final_url="",
                title="",
                html="",
                body_text="",
                links=(),
                status="error",
                error_code=code,
                error_message=str(exc).strip()[:500] or exc.__class__.__name__,
            )
        finally:
            page.close()

    def _throttle(self, url: str, rate_limit_seconds: float | None) -> None:
        delay = self.default_rate_limit_seconds if rate_limit_seconds is None else max(0.0, float(rate_limit_seconds))
        if delay <= 0:
            return
        domain = str(urlsplit(url).hostname or "").casefold()
        now = time.monotonic()
        previous = self._last_request_by_domain.get(domain)
        if previous is not None:
            sleep_for = delay - (now - previous)
            if sleep_for > 0:
                time.sleep(sleep_for)
        self._last_request_by_domain[domain] = time.monotonic()


def _blocked_or_captcha(title: str, body_text: str, html: str) -> bool:
    combined = "\n".join((title, body_text)).casefold()
    markers = (
        "captcha",
        "recaptcha",
        "cf-chl",
        "challenge-platform",
        "cf-browser-verification",
        "attention required",
        "just a moment",
        "sorry, you have been blocked",
        "access denied",
    )
    return any(marker in combined for marker in markers)


def _error_code(exc: Exception) -> str:
    name = exc.__class__.__name__.casefold()
    text = str(exc).casefold()
    if "timeout" in name or "timeout" in text:
        return "timeout"
    blocked_markers = (
        "captcha",
        "recaptcha",
        "cf-chl",
        "challenge-platform",
        "cf-browser-verification",
        "attention required",
        "just a moment",
        "sorry, you have been blocked",
        "access denied",
    )
    if any(marker in text for marker in blocked_markers):
        return "blocked_or_captcha"
    return "inaccessible"
