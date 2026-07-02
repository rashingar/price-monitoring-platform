from __future__ import annotations

import re
from urllib.parse import urlparse

ELECTRONET_DOMAINS = {"electronet.gr", "www.electronet.gr"}
DREAMELECTRIC_DOMAINS = {"dreamelectric.gr", "www.dreamelectric.gr"}
SKROUTZ_DOMAINS = {"skroutz.gr", "www.skroutz.gr", "skroutz.cy", "www.skroutz.cy"}
BESTPRICE_DOMAINS = {"bestprice.gr", "www.bestprice.gr"}
KOTSOVOLOS_DOMAINS = {"kotsovolos.gr", "www.kotsovolos.gr"}
ESTIA_DOMAINS = {"estiahomeart.com", "www.estiahomeart.com"}
APOTHEMA_DOMAINS = {"apothema.gr", "www.apothema.gr"}
MARKETQUEST_DOMAINS = {"marketquest.gr", "www.marketquest.gr"}
EURAGORA_DOMAINS = {"euragora.gr", "www.euragora.gr"}
PAMPOUKIDIS_DOMAINS = {"pampoukidis.gr", "www.pampoukidis.gr"}
GUARANTY_DOMAINS = {"guaranty.gr", "www.guaranty.gr"}
FGEUROPE_DOMAINS = {"fgeurope.gr", "www.fgeurope.gr"}
ECOMARKT_DOMAINS = {"ecomarkt.gr", "www.ecomarkt.gr"}
GEDSA_DOMAINS = {"gedsa.gr", "www.gedsa.gr"}
KOUNTISAE_DOMAINS = {"kountisae.gr", "www.kountisae.gr"}
SKROUTZ_PRODUCT_PATH_PREFIX = "/s/"
BESTPRICE_PRODUCT_PATH_PREFIX = "/item/"
KOTSOVOLOS_PRODUCT_PATH_RE = re.compile(r"/\d{5,}-", re.IGNORECASE)
ESTIA_PRODUCT_PATH_RE = re.compile(
    r"^/[A-Za-z0-9][A-Za-z0-9_-]*(?:/[A-Za-z0-9_-]+)?/?$"
)
MARKETQUEST_PRODUCT_PATH_RE = re.compile(r"^/product/\d+/.+\.html$", re.IGNORECASE)
EURAGORA_PRODUCT_PATH_PREFIX = "/product/"
GUARANTY_PRODUCT_PATH_RE = re.compile(r"^/product/\d+/.+\.html$", re.IGNORECASE)
FGEUROPE_PRODUCT_PATH_PREFIX = "/product/"
SUPPORTED_URL_MESSAGE = (
    "Input URL must be an Electronet, Dream Electric, Skroutz, BestPrice, "
    "Kotsovolos, Estia, Apothema, MarketQuest, Euragora, Pampoukidis, "
    "Guaranty, FG Europe, Ecomarkt, GEDSA, or Kountis AE product URL"
)


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
    if host in ESTIA_DOMAINS:
        return "estia"
    if host in APOTHEMA_DOMAINS:
        return "apothema"
    if host in MARKETQUEST_DOMAINS:
        return "marketquest"
    if host in EURAGORA_DOMAINS:
        return "euragora"
    if host in PAMPOUKIDIS_DOMAINS:
        return "pampoukidis"
    if host in GUARANTY_DOMAINS:
        return "guaranty"
    if host in FGEUROPE_DOMAINS:
        return "fgeurope"
    if host in ECOMARKT_DOMAINS:
        return "ecomarkt"
    if host in GEDSA_DOMAINS:
        return "gedsa"
    if host in KOUNTISAE_DOMAINS:
        return "kountisae"
    raise ValueError(SUPPORTED_URL_MESSAGE)


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
    return parsed.netloc.strip().lower() in KOTSOVOLOS_DOMAINS and bool(
        KOTSOVOLOS_PRODUCT_PATH_RE.search(parsed.path)
    )


def is_estia_product_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.strip()
    return (
        parsed.netloc.strip().lower() in ESTIA_DOMAINS
        and bool(ESTIA_PRODUCT_PATH_RE.match(path))
        and path.strip("/") not in {"", "el", "en", "cart", "login", "register"}
    )


def is_marketquest_product_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.strip().lower() in MARKETQUEST_DOMAINS and bool(
        MARKETQUEST_PRODUCT_PATH_RE.match(parsed.path.strip())
    )


def is_euragora_product_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.strip().lower() in EURAGORA_DOMAINS and parsed.path.startswith(
        EURAGORA_PRODUCT_PATH_PREFIX
    )


def is_pampoukidis_product_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    return parsed.netloc.strip().lower() in PAMPOUKIDIS_DOMAINS and bool(path)


def is_guaranty_product_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.strip().lower() in GUARANTY_DOMAINS and bool(
        GUARANTY_PRODUCT_PATH_RE.match(parsed.path.strip())
    )


def is_fgeurope_product_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.netloc.strip().lower() in FGEUROPE_DOMAINS
        and parsed.path.startswith(FGEUROPE_PRODUCT_PATH_PREFIX)
        and bool(parsed.path.strip("/").split("/", 1)[-1])
    )


def is_ecomarkt_product_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.strip().lower() in ECOMARKT_DOMAINS and bool(
        parsed.path.strip("/")
    )


def is_gedsa_product_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.strip().lower() in GEDSA_DOMAINS and bool(
        parsed.path.strip("/")
    )


def is_kountisae_product_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.netloc.strip().lower() in KOUNTISAE_DOMAINS
        and parsed.path.startswith("/product/")
        and bool(parsed.path.strip("/").split("/", 1)[-1])
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
    if is_estia_product_url(url):
        return source, True, "estia_product_path"
    if source == "estia":
        return source, False, "estia_non_product_path"
    if source == "apothema":
        parsed = urlparse(url)
        if re.search(r"-\d+p/?$", parsed.path, re.IGNORECASE):
            return source, True, "apothema_product_path"
        return source, False, "apothema_non_product_path"
    if is_marketquest_product_url(url):
        return source, True, "marketquest_product_path"
    if source == "marketquest":
        return source, False, "marketquest_non_product_path"
    if is_euragora_product_url(url):
        return source, True, "euragora_product_path"
    if source == "euragora":
        return source, False, "euragora_non_product_path"
    if is_pampoukidis_product_url(url):
        return source, True, "pampoukidis_product_path"
    if source == "pampoukidis":
        return source, False, "pampoukidis_non_product_path"
    if is_guaranty_product_url(url):
        return source, True, "guaranty_product_path"
    if source == "guaranty":
        return source, False, "guaranty_non_product_path"
    if is_fgeurope_product_url(url):
        return source, True, "fgeurope_product_path"
    if source == "fgeurope":
        return source, False, "fgeurope_non_product_path"
    if is_ecomarkt_product_url(url):
        return source, True, "ecomarkt_product_path"
    if source == "ecomarkt":
        return source, False, "ecomarkt_non_product_path"
    if is_gedsa_product_url(url):
        return source, True, "gedsa_product_path"
    if source == "gedsa":
        return source, False, "gedsa_non_product_path"
    if is_kountisae_product_url(url):
        return source, True, "kountisae_product_path"
    if source == "kountisae":
        return source, False, "kountisae_non_product_path"
    return source, False, "unsupported_source"
