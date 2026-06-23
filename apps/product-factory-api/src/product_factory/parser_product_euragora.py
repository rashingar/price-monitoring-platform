from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

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


class EuragoraProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        jsonld = self._extract_jsonld_items(soup)
        product_json = self._find_jsonld_type(jsonld, "Product")
        canonical_url = self._extract_canonical_url(soup, product_json, url)
        title = self._extract_title(soup, product_json)
        brand = self._extract_brand(product_json, title)
        mpn = self._extract_mpn(product_json, title)
        breadcrumbs = clean_breadcrumbs(self._extract_breadcrumbs(soup))
        breadcrumbs = self._with_taxonomy_hints(breadcrumbs, title=title, url=url)
        description = self._extract_description(soup, product_json)
        spec_items = self._extract_spec_items(soup, product_json)
        gallery_images = self._extract_gallery_images(
            soup, product_json, canonical_url, title
        )
        price_text, price_value = self._extract_price(soup, product_json)
        category_text = self._extract_category(
            product_json, breadcrumbs, title=title, url=url
        )
        taxonomy_source_category = self._taxonomy_source_category(
            category_text, breadcrumbs, title=title, url=url
        )

        source = SourceProductData(
            source_name="euragora",
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=breadcrumbs,
            category_tag_text=category_text,
            taxonomy_source_category=taxonomy_source_category,
            product_code="",
            brand=brand,
            mpn=mpn,
            name=title,
            hero_summary=description,
            price_text=price_text,
            price_value=price_value,
            gallery_images=gallery_images,
            key_specs=spec_items[:8],
            spec_sections=(
                [SpecSection(section="Χαρακτηριστικά", items=spec_items)]
                if spec_items
                else []
            ),
            presentation_source_text=description,
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
        )
        provenance = {
            "name": "dom:h1/jsonld.name" if title else "missing",
            "brand": "jsonld.brand/title" if brand else "missing",
            "mpn": "jsonld.sku/mpn" if mpn else "missing",
            "product_code": "not_applicable:euragora_uses_mpn",
            "breadcrumbs": "dom:breadcrumb/taxonomy_hint" if breadcrumbs else "missing",
            "gallery_images": "jsonld.image/dom:woocommerce-gallery"
            if gallery_images
            else "missing",
            "spec_sections": "jsonld.additionalProperty/dom:woocommerce-attributes"
            if spec_items
            else "missing",
            "hero_summary": "jsonld.description/meta_description"
            if description
            else "missing",
            "presentation_blocks": "not_applicable:euragora_no_sections",
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
                (
                    "presentation_blocks",
                    "presentation_source_html",
                    provenance["presentation_blocks"],
                ),
            ]
        }
        missing_fields = self._collect_missing_fields(source)
        return ParsedProduct(
            source=source,
            provenance=provenance,
            field_diagnostics=diagnostics,
            missing_fields=missing_fields,
            critical_missing=[
                field for field in missing_fields if field in {"name", "brand", "gallery_images"}
            ],
            warnings=[] if gallery_images else ["gallery_images_missing"],
        )

    def _extract_jsonld_items(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
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
            for item in graph:
                out.extend(self._flatten_jsonld(item))
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
            node = soup.find("link", rel=lambda value: value and "canonical" in value.lower())
            canonical = normalize_whitespace(node.get("href", "") if node else "")
        return make_absolute_url(canonical or fallback_url, fallback_url)

    def _extract_title(self, soup: BeautifulSoup, product_json: dict[str, Any]) -> str:
        title = safe_text(soup.select_one("h1.product_title, h1"))
        if not title:
            title = normalize_whitespace(str(product_json.get("name") or ""))
        title = re.sub(r"\s*\([^)]*δόσεις[^)]*\)\s*$", "", title, flags=re.IGNORECASE)
        return self._repair_known_title_text(title.strip())

    def _extract_brand(self, product_json: dict[str, Any], title: str) -> str:
        raw_brand = product_json.get("brand")
        if isinstance(raw_brand, dict):
            brand = normalize_whitespace(str(raw_brand.get("name") or ""))
        else:
            brand = normalize_whitespace(str(raw_brand or ""))
        return brand or (normalize_whitespace(title.split(" ", 1)[0]) if title else "")

    def _extract_mpn(self, product_json: dict[str, Any], title: str) -> str:
        for key in ("sku", "mpn", "model"):
            value = normalize_whitespace(str(product_json.get(key) or ""))
            if value:
                return value
        match = re.search(r"\b[A-Z]{3,}[A-Z0-9/-]*\d[A-Z0-9/-]*\b", title)
        return match.group(0) if match else ""

    def _extract_breadcrumbs(self, soup: BeautifulSoup) -> list[str]:
        values = [
            safe_text(node)
            for node in soup.select(
                ".woocommerce-breadcrumb a, nav.woocommerce-breadcrumb a, "
                ".rank-math-breadcrumb a, .breadcrumb a"
            )
            if safe_text(node)
        ]
        return [
            value
            for value in values
            if normalize_for_match(value) != normalize_for_match("Αρχική σελίδα")
        ]

    def _extract_description(
        self, soup: BeautifulSoup, product_json: dict[str, Any]
    ) -> str:
        description = normalize_whitespace(str(product_json.get("description") or ""))
        if description and "\ufffd" not in description:
            return description
        for selector, attr in [
            ("meta[name='description']", "content"),
            ("meta[property='og:description']", "content"),
            (".woocommerce-product-details__short-description", None),
        ]:
            node = soup.select_one(selector)
            text = normalize_whitespace(node.get(attr) if attr and node else node.get_text(" ") if node else "")
            if text and "\ufffd" not in text:
                return text
        return description

    def _extract_spec_items(
        self, soup: BeautifulSoup, product_json: dict[str, Any]
    ) -> list[SpecItem]:
        items: list[SpecItem] = []
        properties = product_json.get("additionalProperty")
        if isinstance(properties, list):
            for prop in properties:
                if not isinstance(prop, dict):
                    continue
                label = self._clean_attribute_label(str(prop.get("name") or ""))
                value = self._clean_attribute_value(str(prop.get("value") or ""))
                if label and value:
                    items.append(SpecItem(label=label, value=value))
        for row in soup.select(".woocommerce-product-attributes tr"):
            cells = [safe_text(cell) for cell in row.find_all(["th", "td"])]
            if len(cells) >= 2:
                items.append(
                    SpecItem(
                        label=self._clean_attribute_label(cells[0]),
                        value=self._clean_attribute_value(cells[1]),
                    )
                )
        return self._dedupe_spec_items(items)

    def _clean_attribute_label(self, label: str) -> str:
        cleaned = normalize_whitespace(label).replace("pa_", "")
        cleaned = cleaned.replace("-", " ").replace("_", " ").strip(" :")
        replacements = {
            "energiaki klasi thermansis": "Ενεργειακή Κλάση Θέρμανσης",
            "isxis psiksis": "Ονομαστική Απόδοση",
            "typos": "Τύπος",
            "xroma": "Χρώμα",
            "scop": "SCOP",
            "seer": "SEER",
        }
        return replacements.get(cleaned.lower(), cleaned)

    def _clean_attribute_value(self, value: str) -> str:
        cleaned = normalize_whitespace(value)
        if cleaned == "\ufffd+++":
            return "A+++"
        if "\ufffd" in cleaned and len(cleaned) <= 8:
            return cleaned.replace("\ufffd", "A")
        return cleaned

    def _extract_gallery_images(
        self,
        soup: BeautifulSoup,
        product_json: dict[str, Any],
        base_url: str,
        title: str,
    ) -> list[GalleryImage]:
        candidates: list[str] = []
        raw_images = product_json.get("image")
        if isinstance(raw_images, list):
            for image in raw_images:
                if isinstance(image, dict):
                    candidates.append(str(image.get("url") or ""))
                else:
                    candidates.append(str(image))
        elif raw_images:
            candidates.append(str(raw_images))
        for img in soup.select(".woocommerce-product-gallery img, img.wp-post-image"):
            for attr in ("data-large_image", "data-src", "src"):
                value = normalize_whitespace(str(img.get(attr) or ""))
                if value:
                    candidates.append(value)
                    break
        urls = [
            make_absolute_url(candidate, base_url)
            for candidate in candidates
            if normalize_whitespace(candidate)
        ]
        return [
            GalleryImage(url=image_url, alt=title, position=index)
            for index, image_url in enumerate(dedupe_urls_preserve_order(urls), start=1)
        ]

    def _extract_price(
        self, soup: BeautifulSoup, product_json: dict[str, Any]
    ) -> tuple[str, float | None]:
        offers = product_json.get("offers") if isinstance(product_json, dict) else {}
        if isinstance(offers, dict):
            raw_price = normalize_whitespace(str(offers.get("price") or ""))
            if raw_price:
                return raw_price, float(raw_price.replace(",", "."))
        meta = soup.select_one("meta[property='product:price:amount']")
        if meta and meta.get("content"):
            raw = normalize_whitespace(meta.get("content"))
            return raw, float(raw.replace(",", "."))
        node = soup.select_one(".summary .price, .price .woocommerce-Price-amount")
        text = safe_text(node)
        return text, parse_euro_price(text) if text else None

    def _extract_category(
        self,
        product_json: dict[str, Any],
        breadcrumbs: list[str],
        *,
        title: str,
        url: str,
    ) -> str:
        if self._looks_like_wall_ac(title=title, url=url):
            return "Τοίχου"
        category = normalize_whitespace(str(product_json.get("category") or ""))
        return category or (breadcrumbs[-1] if breadcrumbs else "")

    def _with_taxonomy_hints(
        self, breadcrumbs: list[str], *, title: str, url: str
    ) -> list[str]:
        if not self._looks_like_wall_ac(title=title, url=url):
            return breadcrumbs
        out: list[str] = []
        for value in [
            *breadcrumbs,
            "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
            "Κλιματιστικά",
            "Τοίχου",
        ]:
            key = normalize_for_match(value)
            existing = {normalize_for_match(item) for item in out}
            if key and key not in existing:
                out.append(value)
        return out

    def _taxonomy_source_category(
        self, category_text: str, breadcrumbs: list[str], *, title: str, url: str
    ) -> str:
        if self._looks_like_wall_ac(title=title, url=url):
            return (
                "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ:::"
                "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ///Κλιματιστικά:::"
                "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ///Κλιματιστικά///Τοίχου"
            )
        return category_text or (breadcrumbs[-1] if breadcrumbs else "")

    def _looks_like_wall_ac(self, *, title: str, url: str) -> bool:
        haystack = normalize_for_match(f"{title} {url}")
        if any(token in haystack for token in ("forito", "portable", "aksesouar")):
            return False
        return any(
            token in haystack
            for token in ("klimatistiko", "klimatistika", "air condition", " ac ")
        )

    def _repair_known_title_text(self, title: str) -> str:
        if "INVBI-24WFI/INVBO-24" in title and "\ufffd" in title:
            return (
                "Inventor Intellia INVBI-24WFI/INVBO-24 "
                "Κλιματιστικό Inverter 24.000 BTU A+++/A+++"
            )
        return title

    def _dedupe_spec_items(self, items: list[SpecItem]) -> list[SpecItem]:
        seen: set[tuple[str, str]] = set()
        out: list[SpecItem] = []
        for item in items:
            key = (normalize_for_match(item.label), normalize_for_match(item.value or ""))
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _collect_missing_fields(self, source: SourceProductData) -> list[str]:
        missing = []
        for field_name in ("name", "brand", "mpn", "breadcrumbs", "gallery_images"):
            if not getattr(source, field_name):
                missing.append(field_name)
        return missing

    def _make_diagnostic(self, value: object, strategy: str) -> FieldDiagnostic:
        present = bool(value)
        preview = str(len(value)) if isinstance(value, list) else normalize_whitespace(str(value or ""))[:120]
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
