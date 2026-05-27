from __future__ import annotations

import re
from urllib.parse import urlparse

ELECTRONET_DOMAINS = {"electronet.gr", "www.electronet.gr"}
DREAMELECTRIC_DOMAINS = {"dreamelectric.gr", "www.dreamelectric.gr"}
SKROUTZ_DOMAINS = {"skroutz.gr", "www.skroutz.gr", "skroutz.cy", "www.skroutz.cy"}
BESTPRICE_DOMAINS = {"bestprice.gr", "www.bestprice.gr"}
KOTSOVOLOS_DOMAINS = {"kotsovolos.gr", "www.kotsovolos.gr"}
SKROUTZ_PRODUCT_PATH_PREFIX = "/s/"
BESTPRICE_PRODUCT_PATH_PREFIX = "/item/"
KOTSOVOLOS_PRODUCT_PATH_RE = re.compile(r"/\d{5,}-", re.IGNORECASE)


def normalize_host(url: str) -> str:
    return urlparse(url).netloc.strip().lower()


def detect_source(url: str) -> str:
    host = normalize_host(url)
    if host in ELECTRONET_DOMAINS:
        return "electronet"
    if host in DREAMELECTRIC_DOMAINS:
        return "dreamelectric"
    if host in SKROUTZ_DOMAINS:
        return "skroutz"
    if host in BESTPRICE_DOMAINS:
        return "bestprice"
    if host in KOTSOVOLOS_DOMAINS:
        return "kotsovolos"
    raise ValueError(
        "Input URL must be an Electronet, Dream Electric, Skroutz, BestPrice, or Kotsovolos product URL"
    )


def is_skroutz_product_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.strip().lower() in SKROUTZ_DOMAINS and parsed.path.startswith(
        SKROUTZ_PRODUCT_PATH_PREFIX
    )


def is_bestprice_product_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.netloc.strip().lower() in BESTPRICE_DOMAINS
        and parsed.path.startswith(BESTPRICE_PRODUCT_PATH_PREFIX)
    )


def is_kotsovolos_product_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.netloc.strip().lower() in KOTSOVOLOS_DOMAINS
        and bool(KOTSOVOLOS_PRODUCT_PATH_RE.search(parsed.path))
    )


def validate_url_scope(url: str) -> tuple[str, bool, str]:
    source = detect_source(url)
    if source == "electronet":
        return source, True, "electronet_domain"
    if source == "dreamelectric":
        return source, True, "dreamelectric_domain"
    if is_skroutz_product_url(url):
        return source, True, "skroutz_product_path"
    if source == "skroutz":
        return source, False, "skroutz_non_product_path"
    if is_bestprice_product_url(url):
        return source, True, "bestprice_product_path"
    if source == "bestprice":
        return source, False, "bestprice_non_product_path"
    if is_kotsovolos_product_url(url):
        return source, True, "kotsovolos_product_path"
    if source == "kotsovolos":
        return source, False, "kotsovolos_non_product_path"
    return source, False, "unsupported_source"
