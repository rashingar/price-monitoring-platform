from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from .deterministic_fields import extract_mpn_from_name
from .models import (
    FieldDiagnostic,
    GalleryImage,
    ParsedProduct,
    SelectorTraceEntry,
    SourceProductData,
    SpecItem,
    SpecSection,
)
from .normalize import (
    clean_breadcrumbs,
    dedupe_urls_preserve_order,
    make_absolute_url,
    normalize_for_match,
    normalize_whitespace,
    parse_euro_price,
    safe_text,
)
from .utils import utcnow_iso

_CHARACTERISTICS_HEADING = normalize_for_match("\u03a7\u03b1\u03c1\u03b1\u03ba\u03c4\u03b7\u03c1\u03b9\u03c3\u03c4\u03b9\u03ba\u03ac")
_SPEC_SECTION_HEADINGS = {
    normalize_for_match("\u0391\u03c0\u03cc\u03b4\u03bf\u03c3\u03b7"),
    normalize_for_match("\u0394\u03c5\u03bd\u03b1\u03c4\u03cc\u03c4\u03b7\u03c4\u03b5\u03c2 & \u039b\u03b5\u03b9\u03c4\u03bf\u03c5\u03c1\u03b3\u03af\u03b5\u03c2"),
    normalize_for_match("\u0395\u03bd\u03b5\u03c1\u03b3\u03b5\u03b9\u03b1\u03ba\u03ae \u039a\u03bb\u03ac\u03c3\u03b7"),
    normalize_for_match("\u0399\u03c3\u03c7\u03cd\u03c2 \u0398\u03bf\u03c1\u03cd\u03b2\u03bf\u03c5"),
    normalize_for_match("\u03a6\u03c5\u03c3\u03b9\u03ba\u03ad\u03c2 \u0394\u03b9\u03b1\u03c3\u03c4\u03ac\u03c3\u03b5\u03b9\u03c2"),
}
_BOOLEAN_FEATURE_LABELS = {
    normalize_for_match("WiFi"): "WiFi",
    normalize_for_match("\u03a6\u03af\u03bb\u03c4\u03c1\u03b1 \u0391\u03ad\u03c1\u03b1"): "\u03a6\u03af\u03bb\u03c4\u03c1\u03b1 \u0391\u03ad\u03c1\u03b1",
    normalize_for_match("\u0399\u03bf\u03bd\u03b9\u03c3\u03c4\u03ae\u03c2"): "\u0399\u03bf\u03bd\u03b9\u03c3\u03c4\u03ae\u03c2",
}
_REFRIGERANT_LABEL = normalize_for_match(
    "\u039f\u03b9\u03ba\u03bf\u03bb\u03bf\u03b3\u03b9\u03ba\u03cc \u03a8\u03c5\u03ba\u03c4\u03b9\u03ba\u03cc \u03a5\u03b3\u03c1\u03cc"
)


class ApothemaProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        product_json = self._find_jsonld_type(self._extract_jsonld_items(soup), "Product")
        canonical_url = self._extract_canonical_url(soup, product_json, url)
        title = self._extract_title(soup, product_json)
        brand = self._extract_brand(soup, product_json, title)
        mpn = self._extract_mpn(soup, product_json, title)
        description_text = self._extract_description_text(soup, product_json)
        spec_items = self._extract_spec_items(soup)
        breadcrumbs = clean_breadcrumbs(self._extract_breadcrumbs(soup))
        gallery_images = self._extract_gallery_images(soup, product_json, canonical_url, title)
        price_text, price_value = self._extract_price(soup, product_json)
        category_text = breadcrumbs[-1] if breadcrumbs else ""

        source = SourceProductData(
            source_name="apothema",
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=breadcrumbs,
            category_tag_text=category_text,
            taxonomy_source_category=category_text,
            product_code=self._extract_product_code(soup, canonical_url),
            brand=brand,
            mpn=mpn,
            name=title,
            hero_summary=description_text,
            price_text=price_text,
            price_value=price_value,
            gallery_images=gallery_images,
            key_specs=spec_items[:10],
            spec_sections=(
                [SpecSection(section="Characteristics", items=spec_items)]
                if spec_items
                else []
            ),
            presentation_source_html="",
            presentation_source_text=description_text,
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
        )
        provenance = {
            "name": "dom:h1/jsonld.name" if title else "missing",
            "brand": "dom:h1/jsonld.brand" if brand else "missing",
            "mpn": "dom:product__desc/name" if mpn else "missing",
            "product_code": "dom:contact_code/url" if source.product_code else "missing",
            "breadcrumbs": "dom:breadcrumb" if breadcrumbs else "missing",
            "gallery_images": "dom:productImages/jsonld.image" if gallery_images else "missing",
            "spec_sections": "dom:.product__desc li" if spec_items else "missing",
            "hero_summary": "jsonld.description/dom:.product__desc" if description_text else "missing",
            "presentation_blocks": "not_applicable:apothema_no_sections",
        }
        diagnostics = {
            key: self._make_diagnostic(getattr(source, field), strategy)
            for key, field, strategy in [
                ("name", "name", provenance["name"]),
                ("brand", "brand", provenance["brand"]),
                ("mpn", "mpn", provenance["mpn"]),
                ("product_code", "product_code", provenance["product_code"]),
                ("breadcrumbs", "breadcrumbs", provenance["breadcrumbs"]),
                ("gallery_images", "gallery_images", provenance["gallery_images"]),
                ("spec_sections", "spec_sections", provenance["spec_sections"]),
                ("hero_summary", "hero_summary", provenance["hero_summary"]),
                ("presentation_blocks", "presentation_source_html", provenance["presentation_blocks"]),
            ]
        }
        missing_fields = self._collect_missing_fields(source)
        return ParsedProduct(
            source=source,
            provenance=provenance,
            field_diagnostics=diagnostics,
            missing_fields=missing_fields,
            critical_missing=self._collect_critical_missing(missing_fields),
            warnings=[] if gallery_images else ["gallery_images_missing"],
        )

    def _extract_jsonld_items(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for script in soup.select('script[type="application/ld+json"]'):
            raw = script.string or script.get_text()
            if not normalize_whitespace(raw):
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            items.extend(self._flatten_jsonld(payload))
        return items

    def _flatten_jsonld(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            out: list[dict[str, Any]] = []
            for item in payload:
                out.extend(self._flatten_jsonld(item))
            return out
        if not isinstance(payload, dict):
            return []
        out = [payload]
        graph = payload.get("@graph")
        if isinstance(graph, list):
            out.extend(item for item in graph if isinstance(item, dict))
        return out

    def _find_jsonld_type(
        self, items: list[dict[str, Any]], type_name: str
    ) -> dict[str, Any]:
        for item in items:
            raw_type = item.get("@type")
            if raw_type == type_name or (
                isinstance(raw_type, list) and type_name in raw_type
            ):
                return item
        return {}

    def _extract_canonical_url(
        self, soup: BeautifulSoup, product_json: dict[str, Any], fallback_url: str
    ) -> str:
        canonical = normalize_whitespace(str(product_json.get("url") or ""))
        if not canonical:
            node = soup.select_one("link[rel='canonical']")
            canonical = normalize_whitespace(node.get("href", "") if node else "")
        return make_absolute_url(canonical or fallback_url, fallback_url)

    def _extract_title(self, soup: BeautifulSoup, product_json: dict[str, Any]) -> str:
        node = soup.select_one("h1.product__title, h1")
        title = safe_text(node)
        if not title:
            title = normalize_whitespace(str(product_json.get("name") or ""))
        return title

    def _extract_brand(
        self, soup: BeautifulSoup, product_json: dict[str, Any], title: str
    ) -> str:
        for item in self._extract_spec_items(soup):
            if normalize_for_match(item.label) in {
                normalize_for_match("Κατασκευαστής"),
                "manufacturer",
            }:
                return item.value or ""
        raw_brand = product_json.get("brand")
        if isinstance(raw_brand, dict):
            brand = normalize_whitespace(str(raw_brand.get("name") or ""))
        else:
            brand = normalize_whitespace(str(raw_brand or ""))
        if brand:
            return brand
        return normalize_whitespace(title.split(" ", 1)[0]) if title else ""

    def _extract_mpn(
        self, soup: BeautifulSoup, product_json: dict[str, Any], title: str
    ) -> str:
        for item in self._extract_spec_items(soup):
            if "kod" in normalize_for_match(item.label):
                value = item.value or ""
                if re.search(r"[A-Za-z]", value):
                    return value
        for key in ("mpn", "sku", "model"):
            value = normalize_whitespace(str(product_json.get(key) or ""))
            if value and re.fullmatch(r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9._-]{4,}", value):
                return value
        token_match = re.search(r"\b(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{4,}\b", title)
        if token_match:
            return token_match.group(0)
        return extract_mpn_from_name(title)

    def _extract_description_text(
        self, soup: BeautifulSoup, product_json: dict[str, Any]
    ) -> str:
        description = normalize_whitespace(str(product_json.get("description") or ""))
        if description:
            return description
        node = soup.select_one(".detailDescription-row-div .product__desc")
        return safe_text(node)

    def _extract_spec_items(self, soup: BeautifulSoup) -> list[SpecItem]:
        items: list[SpecItem] = []
        in_characteristics = False
        for node in soup.select(".detailDescription-row-div .product__desc li"):
            text = safe_text(node)
            text_key = normalize_for_match(text.rstrip(":"))
            if not in_characteristics:
                if _CHARACTERISTICS_HEADING in text_key:
                    in_characteristics = True
                    continue
                if ":" not in text:
                    continue
                label_preview, value_preview = text.split(":", 1)
                if not self._is_spec_label_candidate(label_preview, value_preview):
                    continue
                in_characteristics = True
            if text_key in _SPEC_SECTION_HEADINGS:
                continue
            if ":" in text:
                label, value = text.split(":", 1)
                label = normalize_whitespace(label)
                value = normalize_whitespace(value)
                if not self._is_spec_label_candidate(label, value):
                    continue
            elif text_key in _BOOLEAN_FEATURE_LABELS:
                label = _BOOLEAN_FEATURE_LABELS[text_key]
                value = "\u039d\u03b1\u03b9"
            elif _REFRIGERANT_LABEL in text_key:
                label = "\u03a8\u03c5\u03ba\u03c4\u03b9\u03ba\u03cc \u03a5\u03b3\u03c1\u03cc"
                match = re.search(r"\b(R\d+[A-Z]*)\b", text, flags=re.IGNORECASE)
                value = match.group(1).upper() if match else text
            else:
                continue
            if label and value:
                items.append(SpecItem(label=label, value=value))
        return self._dedupe_spec_items(items)

    def _is_spec_label_candidate(self, label: str, value: str) -> bool:
        label = normalize_whitespace(label.rstrip(":"))
        value = normalize_whitespace(value)
        label_key = normalize_for_match(label)
        if not label or not value:
            return False
        if label_key in _SPEC_SECTION_HEADINGS:
            return False
        if len(label) > 80 or len(value) > 180:
            return False
        if re.search(r"[.!?;,]", label):
            return False
        if len(re.findall(r"\w+", label, flags=re.UNICODE)) > 8:
            return False
        return True

    def _extract_breadcrumbs(self, soup: BeautifulSoup) -> list[str]:
        values = [
            safe_text(node)
            for node in soup.select(".breadcrumb a, .breadcrumbs a")
            if safe_text(node)
        ]
        return [
            value
            for value in values
            if normalize_for_match(value) != normalize_for_match("Αρχική")
        ]

    def _extract_gallery_images(
        self,
        soup: BeautifulSoup,
        product_json: dict[str, Any],
        base_url: str,
        title: str,
    ) -> list[GalleryImage]:
        candidates: list[str] = []
        for node in soup.select(".product__photo--large img, .product-photo-thumbs img"):
            for attr in ("data-full-image-url", "data-src", "src"):
                value = normalize_whitespace(str(node.get(attr) or ""))
                if value:
                    candidates.append(value)
        raw_image = product_json.get("image")
        if isinstance(raw_image, list):
            candidates.extend(str(item) for item in raw_image)
        elif raw_image:
            candidates.append(str(raw_image))
        urls = []
        for candidate in candidates:
            absolute = make_absolute_url(candidate, base_url)
            if "/productImages/" not in absolute:
                continue
            urls.append(self._normalize_gallery_image_url(absolute))
        return [
            GalleryImage(url=image_url, alt=title, position=index)
            for index, image_url in enumerate(dedupe_urls_preserve_order(urls), start=1)
        ]

    def _normalize_gallery_image_url(self, url: str) -> str:
        if "/productImages/s/resized/" in url:
            return re.sub(r"_(?:110x100|150x120)(?=\.[A-Za-z0-9]+(?:[?#]|$))", "_500x360", url)
        return url

    def _extract_price(
        self, soup: BeautifulSoup, product_json: dict[str, Any]
    ) -> tuple[str, float | None]:
        offers = product_json.get("offers") if isinstance(product_json, dict) else {}
        if isinstance(offers, dict):
            raw_price = normalize_whitespace(str(offers.get("price") or ""))
            if raw_price:
                return raw_price, parse_euro_price(raw_price)
        node = soup.select_one(".product__price, [itemprop='price']")
        price = safe_text(node) or normalize_whitespace(str(node.get("content", "") if node else ""))
        return price, parse_euro_price(price) if price else None

    def _extract_product_code(self, soup: BeautifulSoup, canonical_url: str) -> str:
        contact = safe_text(soup.select_one(".product__contact-code"))
        match = re.search(r"(\d{5,})", contact)
        if match:
            return match.group(1)
        path_match = re.search(r"-(\d+)p/?$", canonical_url)
        return path_match.group(1) if path_match else ""

    def _dedupe_spec_items(self, items: list[SpecItem]) -> list[SpecItem]:
        seen: set[tuple[str, str]] = set()
        out: list[SpecItem] = []
        for item in items:
            key = (normalize_for_match(item.label), normalize_for_match(item.value or ""))
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _collect_missing_fields(self, source: SourceProductData) -> list[str]:
        missing = []
        for field_name in ("name", "brand", "mpn", "breadcrumbs", "gallery_images"):
            value = getattr(source, field_name)
            if not value:
                missing.append(field_name)
        return missing

    def _collect_critical_missing(self, missing_fields: list[str]) -> list[str]:
        critical = {"name", "brand", "gallery_images"}
        return [field for field in missing_fields if field in critical]

    def _make_diagnostic(self, value: object, strategy: str) -> FieldDiagnostic:
        present = bool(value)
        preview = ""
        if isinstance(value, list):
            preview = str(len(value))
        elif value is not None:
            preview = normalize_whitespace(str(value))[:120]
        return FieldDiagnostic(
            confidence=0.9 if present else 0.0,
            selected_strategy=strategy,
            value_present=present,
            value_preview=preview,
            selector_trace=[
                SelectorTraceEntry(
                    strategy=strategy,
                    success=present,
                    chosen_preview=preview,
                )
            ],
        )
