from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence
from urllib.parse import urlparse

import httpx

from .normalize import make_absolute_url, normalize_for_match, normalize_whitespace

EPREL_HOST = "https://eprel.ec.europa.eu"
EPREL_API_ROOT = f"{EPREL_HOST}/api"
EPREL_PUBLIC_API_KEY = "3PR31D3F4ULTU1K3Y2020"
EPREL_TIMEOUT = httpx.Timeout(20.0, connect=10.0, read=20.0)
EPREL_SEARCH_PARAMS: dict[str, Any] = {
    "_page": 1,
    "_limit": 10,
    "sort0": "onMarketStartDateTS",
    "order0": "DESC",
    "sort1": "energyClass",
    "order1": "DESC",
}

FAMILY_TO_PRODUCT_GROUP = {
    "air_conditioner": "airconditioners",
    "built_in_oven": "ovens",
    "dishwasher": "dishwashers",
    "hood": "rangehoods",
    "refrigeration": "refrigeratingappliances2019",
    "television": "electronicdisplays",
}

_PRODUCT_GROUP_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ovens", ("oven", "ovens", "fourno", "fourno", "fournos", "φουρν")),
    ("rangehoods", ("hood", "range hood", "hoods", "aporrofit", "απορροφητ")),
    ("dishwashers", ("dishwasher", "dishwashers", "piat", "πιατ")),
    ("electronicdisplays", ("tv", "television", "display", "τηλεορ")),
    ("refrigeratingappliances2019", ("fridge", "freezer", "refrigerator", "ψυγει", "καταψυκτ")),
    ("airconditioners", ("air condition", "aircondition", "klimatist", "κλιματιστ")),
)

JsonFetcher = Callable[[str, dict[str, Any] | None], dict[str, Any]]


@dataclass(slots=True)
class EprelLabelResolution:
    product_group: str = ""
    registration_number: str = ""
    label_url: str = ""
    search_strategy: str = ""


def infer_eprel_product_group(
    *,
    family_key: str = "",
    breadcrumbs: Sequence[str] | None = None,
    taxonomy_source_category: str = "",
    title: str = "",
    canonical_url: str = "",
) -> str:
    family = normalize_whitespace(family_key)
    if family in FAMILY_TO_PRODUCT_GROUP:
        return FAMILY_TO_PRODUCT_GROUP[family]

    haystack = normalize_for_match(
        " ".join(
            [
                canonical_url,
                title,
                taxonomy_source_category,
                *(breadcrumbs or ()),
            ]
        )
    )
    if not haystack:
        return ""

    for product_group, tokens in _PRODUCT_GROUP_HINTS:
        if any(normalize_for_match(token) in haystack for token in tokens):
            return product_group
    return ""


def resolve_eprel_energy_label(
    *,
    family_key: str = "",
    breadcrumbs: Sequence[str] | None = None,
    taxonomy_source_category: str = "",
    title: str = "",
    canonical_url: str = "",
    model_identifier: str = "",
    gtin: str = "",
    eprel_registration_number: str = "",
    fetch_json: JsonFetcher | None = None,
) -> EprelLabelResolution:
    product_group = infer_eprel_product_group(
        family_key=family_key,
        breadcrumbs=breadcrumbs,
        taxonomy_source_category=taxonomy_source_category,
        title=title,
        canonical_url=canonical_url,
    )
    if not product_group:
        return EprelLabelResolution()

    fetch = fetch_json or _fetch_eprel_json

    registration_number = normalize_whitespace(eprel_registration_number)
    if registration_number:
        label_url = _resolve_label_url(
            product_group=product_group,
            registration_number=registration_number,
            fetch_json=fetch,
        )
        if label_url:
            return EprelLabelResolution(
                product_group=product_group,
                registration_number=registration_number,
                label_url=label_url,
                search_strategy="registration_number",
            )

    normalized_model = normalize_whitespace(model_identifier).upper()
    if normalized_model:
        registration_number = _search_registration_number(
            product_group=product_group,
            field_name="modelIdentifier",
            field_value=normalized_model,
            fetch_json=fetch,
        )
        if registration_number:
            label_url = _resolve_label_url(
                product_group=product_group,
                registration_number=registration_number,
                fetch_json=fetch,
            )
            if label_url:
                return EprelLabelResolution(
                    product_group=product_group,
                    registration_number=registration_number,
                    label_url=label_url,
                    search_strategy="model_identifier",
                )

    normalized_gtin = _normalize_gtin(gtin)
    if normalized_gtin:
        registration_number = _search_registration_number(
            product_group=product_group,
            field_name="gtinIdentifier",
            field_value=normalized_gtin,
            fetch_json=fetch,
        )
        if registration_number:
            label_url = _resolve_label_url(
                product_group=product_group,
                registration_number=registration_number,
                fetch_json=fetch,
            )
            if label_url:
                return EprelLabelResolution(
                    product_group=product_group,
                    registration_number=registration_number,
                    label_url=label_url,
                    search_strategy="gtin_identifier",
                )

    return EprelLabelResolution(product_group=product_group)


def resolve_eprel_energy_label_asset_url(**kwargs: Any) -> str:
    return resolve_eprel_energy_label(**kwargs).label_url


def _search_registration_number(
    *,
    product_group: str,
    field_name: str,
    field_value: str,
    fetch_json: JsonFetcher,
) -> str:
    try:
        payload = fetch_json(
            f"{EPREL_API_ROOT}/products/{product_group}",
            {
                **EPREL_SEARCH_PARAMS,
                field_name: field_value,
            },
        )
    except Exception:
        return ""
    hits = payload.get("hits") if isinstance(payload, dict) else None
    if not isinstance(hits, list):
        return ""

    expected_value = _normalize_field_value(field_name, field_value)
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        if not _hit_matches(hit, field_name, expected_value):
            continue
        registration_number = normalize_whitespace(str(hit.get("eprelRegistrationNumber") or ""))
        if registration_number:
            return registration_number
    return ""


def _resolve_label_url(
    *,
    product_group: str,
    registration_number: str,
    fetch_json: JsonFetcher,
) -> str:
    try:
        payload = fetch_json(
            f"{EPREL_API_ROOT}/products/{product_group}/{registration_number}/labels",
            {
                "noRedirect": "true",
                "format": "PNG",
            },
        )
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    address = normalize_whitespace(str(payload.get("address") or ""))
    if not address:
        return ""
    return make_absolute_url(address, EPREL_HOST)


def _hit_matches(hit: dict[str, Any], field_name: str, expected_value: str) -> bool:
    if field_name == "modelIdentifier":
        return _normalize_field_value(field_name, hit.get("modelIdentifier")) == expected_value
    if field_name == "gtinIdentifier":
        hit_values = {
            _normalize_field_value(field_name, hit.get("gtinIdentifier")),
            _normalize_field_value(field_name, hit.get("gtin")),
            _normalize_field_value(field_name, hit.get("ean")),
        }
        hit_values.discard("")
        return expected_value in hit_values
    return False


def _normalize_field_value(field_name: str, value: Any) -> str:
    if field_name == "modelIdentifier":
        return normalize_whitespace(value).upper()
    if field_name == "gtinIdentifier":
        return _normalize_gtin(value)
    return normalize_whitespace(value)


def _normalize_gtin(value: Any) -> str:
    return "".join(ch for ch in normalize_whitespace(value) if ch.isdigit())


def _fetch_eprel_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": EPREL_HOST,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
        "x-api-key": EPREL_PUBLIC_API_KEY,
    }
    referer = _build_eprel_referer(url)
    if referer:
        headers["Referer"] = referer

    with httpx.Client(timeout=EPREL_TIMEOUT, follow_redirects=True, headers=headers) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _build_eprel_referer(api_url: str) -> str:
    parsed = urlparse(api_url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "products":
        if len(parts) >= 5 and parts[4] == "labels":
            return f"{EPREL_HOST}/screen/product/{parts[2]}/{parts[3]}"
        return f"{EPREL_HOST}/screen/product/{parts[2]}"
    return f"{EPREL_HOST}/screen/home"
