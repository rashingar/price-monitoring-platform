from __future__ import annotations

from urllib.parse import urlparse

ELECTRONET_DOMAINS = {"electronet.gr", "www.electronet.gr"}
SKROUTZ_DOMAINS = {"skroutz.gr", "www.skroutz.gr", "skroutz.cy", "www.skroutz.cy"}
SKROUTZ_PRODUCT_PATH_PREFIX = "/s/"


def normalize_host(url: str) -> str:
    return urlparse(url).netloc.strip().lower()


def detect_source(url: str) -> str:
    host = normalize_host(url)
    if host in ELECTRONET_DOMAINS:
        return "electronet"
    if host in SKROUTZ_DOMAINS:
        return "skroutz"
    raise ValueError("Input URL must be an Electronet or Skroutz product URL")


def is_skroutz_product_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.strip().lower() in SKROUTZ_DOMAINS and parsed.path.startswith(SKROUTZ_PRODUCT_PATH_PREFIX)


def validate_url_scope(url: str) -> tuple[str, bool, str]:
    source = detect_source(url)
    if source == "electronet":
        return source, True, "electronet_domain"
    if is_skroutz_product_url(url):
        return source, True, "skroutz_product_path"
    if source == "skroutz":
        return source, False, "skroutz_non_product_path"
    return source, False, "unsupported_source"
