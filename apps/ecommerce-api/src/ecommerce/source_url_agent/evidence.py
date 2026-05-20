"""Public product-page evidence extraction for source URL discovery."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

from ecommerce.source_url_agent.matching import extract_name_evidence
from ecommerce.utils.decimals import format_decimal_two_places
from ecommerce.source_url_agent.page_rules import review_page_rejection_reason
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.sources import SourceDefinition
from ecommerce.utils.text import (
    normalize_product_text,
    parse_greek_money_text,
    product_tokens,
)

CANONICAL_RE = re.compile(
    r"<link[^>]+rel=[\"'][^\"']*canonical[^\"']*[\"'][^>]+href=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META_DESCRIPTION_RE = re.compile(
    r"<meta\b(?=[^>]*\bname=[\"']description[\"'])(?=[^>]*\bcontent=[\"']([^\"']*)[\"'])[^>]*>",
    re.IGNORECASE | re.DOTALL,
)
META_DESCRIPTION_REVERSED = re.compile(
    r"<meta\b(?=[^>]*\bcontent=[\"']([^\"']*)[\"'])(?=[^>]*\bname=[\"']description[\"'])[^>]*>",
    re.IGNORECASE | re.DOTALL,
)
JSONLD_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
PRICE_RE = re.compile(
    r"([0-9]{1,3}(?:[.\s][0-9]{3})*(?:,[0-9]{2})?|[0-9]+(?:[,.][0-9]{2})?)\s*€"
)
BLOCKED_RE = re.compile(
    r"(captcha|recaptcha|cf-chl|challenge-platform|cf-browser-verification|attention required|just a moment|sorry, you have been blocked|access denied)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PageEvidence:
    requested_url: str
    final_url: str
    canonical_url: str
    title: str
    body_text_sample: str
    candidate_price: Decimal | None
    exact_mpn_found: bool
    exact_mpn_fragment: str
    exact_mpn_source: str
    exact_model_found: bool
    exact_model_fragment: str
    exact_model_source: str
    brand_found: bool
    brand_fragment: str
    category_compatible: bool
    category_fragment: str
    title_similarity: float
    title_matched_tokens: tuple[str, ...]
    price_compatible: bool | None
    jsonld_products: tuple[dict[str, Any], ...]
    blocked_or_captcha: bool = False
    error_code: str = ""
    error_message: str = ""
    evidence_source: str = "fetched_page"
    provider_provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def title_only(self) -> bool:
        return bool(
            self.title_similarity >= 0.5
            and not self.exact_mpn_found
            and not self.exact_model_found
        )

    def to_json(self) -> dict[str, Any]:
        payload = {
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "body_text_sample": self.body_text_sample,
            "candidate_price": (
                format_decimal_two_places(self.candidate_price)
                if self.candidate_price is not None
                else ""
            ),
            "mpn": {
                "expected": "",
                "found": self.exact_mpn_found,
                "fragment": self.exact_mpn_fragment,
                "source": self.exact_mpn_source,
            },
            "model": {
                "expected": "",
                "found": self.exact_model_found,
                "fragment": self.exact_model_fragment,
                "source": self.exact_model_source,
            },
            "brand": {
                "found": self.brand_found,
                "fragment": self.brand_fragment,
            },
            "category": {
                "compatible": self.category_compatible,
                "fragment": self.category_fragment,
            },
            "price": {
                "compatible": self.price_compatible,
            },
            "title_similarity": self.title_similarity,
            "title_matched_tokens": list(self.title_matched_tokens),
            "title_only": self.title_only,
            "blocked_or_captcha": self.blocked_or_captcha,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "jsonld_products": [
                _compact_jsonld_product(item) for item in self.jsonld_products[:3]
            ],
        }
        if self.provider_provenance:
            payload["provider_provenance"] = self.provider_provenance
        if self.evidence_source == "provider_search_result":
            payload["evidence_source"] = self.evidence_source
        return payload


def extract_page_evidence(
    *,
    product: AgentProduct,
    source: SourceDefinition,
    requested_url: str,
    final_url: str,
    html_text: str,
    title: str = "",
    body_text: str = "",
    evidence_source: str = "fetched_page",
    provider_provenance: dict[str, Any] | None = None,
) -> PageEvidence:
    title_text = _clean_text(title) or _extract_title(html_text)
    meta_description = _extract_meta_description(html_text)
    visible_text = _clean_text(body_text) or html_to_visible_text(html_text)
    combined_text = "\n".join((title_text, visible_text))
    jsonld_products = tuple(_product_jsonld_items(_parse_jsonld(html_text)))
    jsonld_text = _jsonld_search_text(jsonld_products)
    canonical_url = _canonical_url(html_text, final_url or requested_url)
    url_text = _url_evidence_text(requested_url, final_url, canonical_url)
    non_url_search_text = "\n".join(
        (title_text, meta_description, visible_text, jsonld_text)
    )
    search_text = "\n".join((non_url_search_text, url_text))
    if source.is_product_url(canonical_url):
        canonical = source.canonical_candidate_url(canonical_url)
    else:
        canonical = source.canonical_candidate_url(final_url or requested_url)
    rejection_reason = review_page_rejection_reason(
        candidate_url=requested_url,
        canonical_url=canonical_url or canonical,
        title=title_text,
    ) or review_page_rejection_reason(canonical_url=canonical, title=title_text)
    if rejection_reason:
        return _not_public_product_page_evidence(
            requested_url=requested_url,
            final_url=final_url or requested_url,
            canonical_url=canonical,
            title=title_text,
            body_text=visible_text,
            reason=rejection_reason,
            provider_provenance=provider_provenance or {},
        )

    mpn_fragment, mpn_source = _find_identifier_evidence(
        product.mpn,
        jsonld_text=jsonld_text,
        title=title_text,
        meta_description=meta_description,
        body_text=visible_text,
        url_text=url_text,
    )
    model_fragment, model_source = _find_identifier_evidence(
        product.model,
        jsonld_text=jsonld_text,
        title=title_text,
        meta_description=meta_description,
        body_text=visible_text,
        url_text=url_text,
    )
    brand_haystack = (
        search_text
        if _identifier_source_supports_url_brand(product, mpn_source, model_source)
        else non_url_search_text
    )
    brand_fragment = _find_brand_fragment(
        product.manufacturer, brand_haystack, jsonld_products
    )
    category_fragment = _find_category_fragment(
        product.category, search_text, jsonld_products
    )
    candidate_price = _extract_price(jsonld_products, visible_text)
    title_evidence = (
        extract_name_evidence(product.name, title_text)
        if product.name and title_text
        else None
    )

    return PageEvidence(
        requested_url=requested_url,
        final_url=final_url or requested_url,
        canonical_url=canonical,
        title=title_text,
        body_text_sample=visible_text[:800],
        candidate_price=candidate_price,
        exact_mpn_found=bool(mpn_fragment),
        exact_mpn_fragment=mpn_fragment,
        exact_mpn_source=mpn_source,
        exact_model_found=bool(model_fragment),
        exact_model_fragment=model_fragment,
        exact_model_source=model_source,
        brand_found=bool(brand_fragment),
        brand_fragment=brand_fragment,
        category_compatible=bool(category_fragment),
        category_fragment=category_fragment,
        title_similarity=(
            round(float(title_evidence.score), 4) if title_evidence is not None else 0.0
        ),
        title_matched_tokens=(
            title_evidence.matched_tokens if title_evidence is not None else ()
        ),
        price_compatible=_price_compatible(product.price, candidate_price),
        jsonld_products=jsonld_products,
        blocked_or_captcha=bool(BLOCKED_RE.search(combined_text)),
        evidence_source=evidence_source,
        provider_provenance=provider_provenance or {},
    )


def provider_search_result_evidence(
    *,
    product: AgentProduct,
    source: SourceDefinition,
    requested_url: str,
    final_url: str = "",
    title: str = "",
    description: str = "",
    extra_snippets: tuple[str, ...] = (),
    provider_provenance: dict[str, Any] | None = None,
) -> PageEvidence:
    snippet_text = _clean_text(" ".join([description, *extra_snippets]))
    provenance = dict(provider_provenance or {})
    provenance["evidence_source"] = "provider_search_result"
    return extract_page_evidence(
        product=product,
        source=source,
        requested_url=requested_url,
        final_url=final_url or requested_url,
        html_text="",
        title=title,
        body_text=snippet_text,
        evidence_source="provider_search_result",
        provider_provenance=provenance,
    )


def error_evidence(
    *,
    product: AgentProduct,
    requested_url: str,
    final_url: str = "",
    title: str = "",
    body_text: str = "",
    source: SourceDefinition | None = None,
    error_code: str,
    error_message: str,
    provider_provenance: dict[str, Any] | None = None,
) -> PageEvidence:
    if source is not None:
        canonical_url = source.canonical_candidate_url(final_url or requested_url)
    else:
        canonical_url = final_url or requested_url
    url_text = _url_evidence_text(requested_url, final_url, canonical_url)
    title_text = _clean_text(title)
    body = _clean_text(body_text)
    mpn_fragment, mpn_source = _find_identifier_evidence(
        product.mpn,
        jsonld_text="",
        title=title_text,
        meta_description="",
        body_text=body,
        url_text=url_text,
    )
    model_fragment, model_source = _find_identifier_evidence(
        product.model,
        jsonld_text="",
        title=title_text,
        meta_description="",
        body_text=body,
        url_text=url_text,
    )
    brand_fragment = _find_brand_fragment(
        product.manufacturer, "\n".join((title_text, body, url_text)), ()
    )
    return PageEvidence(
        requested_url=requested_url,
        final_url=final_url or requested_url,
        canonical_url=canonical_url,
        title=title_text,
        body_text_sample=body[:800],
        candidate_price=None,
        exact_mpn_found=bool(mpn_fragment),
        exact_mpn_fragment=mpn_fragment,
        exact_mpn_source=mpn_source,
        exact_model_found=bool(model_fragment),
        exact_model_fragment=model_fragment,
        exact_model_source=model_source,
        brand_found=bool(brand_fragment),
        brand_fragment=brand_fragment,
        category_compatible=False,
        category_fragment="",
        title_similarity=0.0,
        title_matched_tokens=(),
        price_compatible=None,
        jsonld_products=(),
        blocked_or_captcha=error_code == "blocked_or_captcha",
        error_code=error_code,
        error_message=error_message,
        evidence_source="navigation_error",
        provider_provenance=provider_provenance or {},
    )


def _not_public_product_page_evidence(
    *,
    requested_url: str,
    final_url: str,
    canonical_url: str,
    title: str,
    body_text: str,
    reason: str,
    provider_provenance: dict[str, Any] | None = None,
) -> PageEvidence:
    return PageEvidence(
        requested_url=requested_url,
        final_url=final_url or requested_url,
        canonical_url=canonical_url,
        title=title,
        body_text_sample=body_text[:800],
        candidate_price=None,
        exact_mpn_found=False,
        exact_mpn_fragment="",
        exact_mpn_source="",
        exact_model_found=False,
        exact_model_fragment="",
        exact_model_source="",
        brand_found=False,
        brand_fragment="",
        category_compatible=False,
        category_fragment="",
        title_similarity=0.0,
        title_matched_tokens=(),
        price_compatible=None,
        jsonld_products=(),
        blocked_or_captcha=False,
        error_code="not_public_product_page",
        error_message=f"Rejected review page: {reason}.",
        evidence_source="fetched_page",
        provider_provenance=provider_provenance or {},
    )


def html_to_visible_text(html_text: str) -> str:
    parser = _VisibleTextParser()
    try:
        parser.feed(_remove_script_blocks(html_text))
        parser.close()
    except Exception:
        return _clean_text(re.sub(r"<[^>]+>", " ", html_text))
    return _clean_text(" ".join(parser.parts))


def _extract_title(html_text: str) -> str:
    match = TITLE_RE.search(html_text or "")
    return _clean_text(html.unescape(match.group(1))) if match else ""


def _extract_meta_description(html_text: str) -> str:
    for pattern in (META_DESCRIPTION_RE, META_DESCRIPTION_REVERSED):
        match = pattern.search(html_text or "")
        if match is not None:
            return _clean_text(html.unescape(match.group(1)))
    return ""


def _canonical_url(html_text: str, base_url: str) -> str:
    match = CANONICAL_RE.search(html_text or "")
    if match is None:
        return base_url
    return urljoin(base_url, html.unescape(match.group(1)).strip())


def _url_evidence_text(*urls: str) -> str:
    parts: list[str] = []
    for url in urls:
        parsed = urlsplit(str(url or "").strip())
        if not parsed.netloc:
            continue
        parts.append(unquote(parsed.netloc.replace(".", " ")))
        parts.append(
            unquote(
                (parsed.path or "")
                .replace("/", " ")
                .replace("-", " ")
                .replace("_", " ")
            )
        )
        parts.append(unquote(parsed.path or ""))
    return _clean_text(" ".join(parts))


def _parse_jsonld(html_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in JSONLD_RE.finditer(html_text or ""):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        _append_jsonld(items, parsed)
    return items


def _append_jsonld(items: list[dict[str, Any]], value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _append_jsonld(items, item)
        return
    if not isinstance(value, dict):
        return
    graph = value.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            _append_jsonld(items, item)
    items.append(value)


def _product_jsonld_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    products = [
        item for item in items if "product" in _jsonld_type_text(item.get("@type"))
    ]
    return products or items


def _jsonld_search_text(items: tuple[dict[str, Any], ...]) -> str:
    parts: list[str] = []
    for item in items:
        for key in (
            "name",
            "brand",
            "manufacturer",
            "mpn",
            "model",
            "sku",
            "productID",
            "category",
        ):
            parts.append(_jsonld_text(item.get(key)))
        offers = item.get("offers")
        if isinstance(offers, dict):
            parts.extend(
                _jsonld_text(offers.get(key))
                for key in ("price", "priceCurrency", "availability")
            )
    return _clean_text(" ".join(part for part in parts if part))


def _find_identifier_evidence(
    identifier: str,
    *,
    jsonld_text: str,
    title: str,
    meta_description: str,
    body_text: str,
    url_text: str,
) -> tuple[str, str]:
    for source, haystack in (
        ("jsonld", jsonld_text),
        ("title", title),
        ("meta", meta_description),
        ("body", body_text),
        ("url", url_text),
    ):
        fragment = _find_identifier_fragment(identifier, haystack)
        if fragment:
            return fragment, source
    return "", ""


def _find_identifier_fragment(identifier: str, haystack: str) -> str:
    needle = str(identifier or "").strip()
    if not needle:
        return ""
    parts = [re.escape(part) for part in needle.split()]
    if not parts:
        return ""
    normalized_needle_pattern = r"\s+".join(parts)
    pattern = re.compile(
        rf"(?<![A-Za-z0-9]){normalized_needle_pattern}(?![A-Za-z0-9])", re.IGNORECASE
    )
    match = pattern.search(haystack or "")
    if match is not None:
        return match.group(0)
    normalized_needle = _identifier_key(needle)
    normalized_haystack = _identifier_key(haystack)
    if (
        len(normalized_needle) >= 4
        and any(character.isdigit() for character in normalized_needle)
        and normalized_needle in normalized_haystack
    ):
        return needle
    return ""


def _identifier_key(value: str) -> str:
    return "".join(
        character.casefold() for character in str(value or "") if character.isalnum()
    )


def _identifier_source_supports_url_brand(
    product: AgentProduct, mpn_source: str, model_source: str
) -> bool:
    if mpn_source == "url":
        return True
    return not str(product.mpn or "").strip() and model_source == "url"


def _find_brand_fragment(
    manufacturer: str, haystack: str, jsonld_products: tuple[dict[str, Any], ...]
) -> str:
    brand = _clean_text(manufacturer)
    if not brand:
        return ""
    brand_norm = normalize_product_text(brand)
    for item in jsonld_products:
        for key in ("brand", "manufacturer"):
            candidate = _clean_text(_jsonld_text(item.get(key)))
            if candidate and normalize_product_text(candidate) == brand_norm:
                return candidate
    pattern = re.compile(rf"(?<!\w){re.escape(brand)}(?!\w)", re.IGNORECASE)
    match = pattern.search(haystack or "")
    return match.group(0) if match is not None else ""


def _find_category_fragment(
    category: str, haystack: str, jsonld_products: tuple[dict[str, Any], ...]
) -> str:
    category_values = [_jsonld_text(item.get("category")) for item in jsonld_products]
    category_text = " ".join([category, *category_values])
    expected_tokens = [
        token for token in product_tokens(category_text) if len(token) >= 4
    ]
    if not expected_tokens:
        return ""
    haystack_tokens = set(product_tokens(haystack))
    matched = [token for token in expected_tokens if token in haystack_tokens]
    if len(matched) >= 2:
        return " ".join(matched[:6])
    return matched[0] if matched and len(expected_tokens) <= 2 else ""


def _extract_price(
    jsonld_products: tuple[dict[str, Any], ...], body_text: str
) -> Decimal | None:
    for item in jsonld_products:
        offers = item.get("offers")
        offer_items = offers if isinstance(offers, list) else [offers]
        for offer in offer_items:
            if not isinstance(offer, dict):
                continue
            value = (
                offer.get("price") or offer.get("lowPrice") or offer.get("highPrice")
            )
            price = _decimal_from_text(value)
            if price is not None and price > 0:
                return price
    match = PRICE_RE.search(body_text or "")
    if match is None:
        return None
    return _decimal_from_text(match.group(0))


def _price_compatible(
    own_price: Decimal | None, candidate_price: Decimal | None
) -> bool | None:
    if (
        own_price is None
        or candidate_price is None
        or own_price <= 0
        or candidate_price <= 0
    ):
        return None
    delta = abs(candidate_price - own_price) / own_price
    return delta <= Decimal("0.40")


def _decimal_from_text(value: object) -> Decimal | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return parse_greek_money_text(text)
    except ValueError:
        try:
            return Decimal(text.replace("€", "").replace(",", ".").strip())
        except Exception:
            return None


def _compact_jsonld_product(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _jsonld_text(item.get(key))
        for key in (
            "@type",
            "name",
            "brand",
            "manufacturer",
            "mpn",
            "model",
            "sku",
            "productID",
            "category",
        )
        if _jsonld_text(item.get(key))
    }


def _jsonld_type_text(value: object) -> str:
    if isinstance(value, list):
        return " ".join(str(item).casefold() for item in value)
    return str(value or "").casefold()


def _jsonld_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("name", "@id", "value"):
            if value.get(key):
                return _clean_text(value.get(key))
        return _clean_text(" ".join(_jsonld_text(item) for item in value.values()))
    if isinstance(value, list):
        return _clean_text(" ".join(_jsonld_text(item) for item in value))
    return _clean_text(value)


def _remove_script_blocks(html_text: str) -> str:
    return re.sub(
        r"<(?:script|style)[^>]*>.*?</(?:script|style)>",
        " ",
        html_text or "",
        flags=re.IGNORECASE | re.DOTALL,
    )


def _clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)
