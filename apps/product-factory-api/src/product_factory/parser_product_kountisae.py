from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

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
from .skroutz_taxonomy import serialize_source_category
from .utils import utcnow_iso

WASHER_PARENT_CATEGORY = "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ"
WASHER_LEAF_CATEGORY = "Πλυντήρια-Στεγνωτήρια"
WASHER_SUB_CATEGORY = "Πλυντήρια Ρούχων"


class KountisAEProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        jsonld = self._extract_jsonld_items(soup)
        canonical_url = self._extract_canonical_url(soup, url)
        title = self._extract_title(soup, jsonld)
        description = self._extract_description(soup, jsonld)
        description_lines = self._description_lines(soup)
        spec_sections = self._extract_spec_sections(description_lines)
        self._add_derived_washer_specs(spec_sections, title, description_lines)
        spec_items = [item for section in spec_sections for item in section.items]
        brand = self._extract_brand(soup, jsonld, title)
        mpn = self._extract_mpn(spec_items, title)
        gallery_images = self._extract_gallery_images(soup, canonical_url, title)
        breadcrumbs = clean_breadcrumbs(self._extract_breadcrumbs(soup))
        price_text, price_value = self._extract_price(soup, jsonld)

        source = SourceProductData(
            source_name="kountisae",
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=breadcrumbs,
            category_tag_text=WASHER_SUB_CATEGORY,
            taxonomy_source_category=serialize_source_category(
                WASHER_PARENT_CATEGORY,
                WASHER_LEAF_CATEGORY,
                [WASHER_SUB_CATEGORY],
            ),
            taxonomy_match_type="exact_category",
            taxonomy_rule_id="kountisae:washing_machine",
            product_code="",
            brand=brand,
            mpn=mpn,
            name=title,
            hero_summary=description,
            price_text=price_text,
            price_value=price_value,
            gallery_images=gallery_images,
            key_specs=spec_items[:10],
            spec_sections=spec_sections,
            presentation_source_text=description,
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
        )
        provenance = {
            "name": "dom:h1.product_title/jsonld.name" if title else "missing",
            "brand": "jsonld.brand/title_token" if brand else "missing",
            "mpn": "description:Εμπορικός κωδικός/title_token" if mpn else "missing",
            "product_code": "not_applicable:kountisae_uses_commercial_code_as_mpn",
            "breadcrumbs": "dom:.woocommerce-breadcrumb a" if breadcrumbs else "missing",
            "gallery_images": "dom:figure.woocommerce-product-gallery__wrapper img"
            if gallery_images
            else "missing",
            "spec_sections": "dom:#tab-description"
            if spec_sections
            else "missing",
            "hero_summary": "dom:#tab-description/jsonld.description"
            if description
            else "missing",
            "presentation_blocks": "not_applicable:kountisae_sections_zero",
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
        warnings: list[str] = []
        if not gallery_images:
            warnings.append("gallery_images_missing")
        return ParsedProduct(
            source=source,
            provenance=provenance,
            field_diagnostics=diagnostics,
            missing_fields=missing_fields,
            critical_missing=[
                field
                for field in missing_fields
                if field in {"name", "brand", "gallery_images"}
            ],
            warnings=warnings,
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

    def _extract_canonical_url(self, soup: BeautifulSoup, fallback_url: str) -> str:
        node = soup.select_one("link[rel='canonical']")
        canonical = normalize_whitespace(node.get("href", "") if node else "")
        return make_absolute_url(canonical or fallback_url, fallback_url)

    def _extract_title(self, soup: BeautifulSoup, jsonld: list[dict[str, Any]]) -> str:
        title = safe_text(soup.select_one("h1.product_title, h1.entry-title, h1"))
        if title:
            return title
        product_json = self._find_jsonld_type(jsonld, "Product")
        return normalize_whitespace(str(product_json.get("name") or ""))

    def _extract_brand(
        self, soup: BeautifulSoup, jsonld: list[dict[str, Any]], title: str
    ) -> str:
        product_json = self._find_jsonld_type(jsonld, "Product")
        brand = product_json.get("brand") if product_json else None
        if isinstance(brand, dict):
            value = normalize_whitespace(str(brand.get("name") or ""))
            if value:
                return value
        if isinstance(brand, str) and normalize_whitespace(brand):
            return normalize_whitespace(brand)
        node = soup.select_one("meta[property='product:brand'], meta[itemprop='brand']")
        value = normalize_whitespace(node.get("content") if node else "")
        if value:
            return value
        first = normalize_whitespace(title.split(" ", 1)[0]) if title else ""
        return first.title() if first.isupper() else first

    def _extract_mpn(self, spec_items: list[SpecItem], title: str) -> str:
        for item in spec_items:
            if normalize_for_match(item.label) in {
                normalize_for_match("Εμπορικός κωδικός"),
                normalize_for_match("Κωδικός προϊόντος"),
                normalize_for_match("SKU"),
            }:
                return normalize_whitespace(item.value or "")
        match = re.search(
            r"\b(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{6,}\b",
            title,
        )
        return match.group(0) if match else ""

    def _extract_description(
        self, soup: BeautifulSoup, jsonld: list[dict[str, Any]]
    ) -> str:
        lines = self._description_lines(soup)
        if lines:
            summary = self._summary_from_description_lines(lines)
            if summary:
                return summary
        product_json = self._find_jsonld_type(jsonld, "Product")
        description = normalize_whitespace(str(product_json.get("description") or ""))
        if description:
            return description
        node = soup.select_one("meta[name='description'], meta[property='og:description']")
        return normalize_whitespace(node.get("content") if node else "")

    def _summary_from_description_lines(self, lines: list[str]) -> str:
        for line in lines:
            key = normalize_for_match(line)
            if len(line.split()) >= 12 and ":" not in line and "βασικα στοιχεια" not in key:
                return line
        return " ".join(lines[:3])

    def _description_lines(self, soup: BeautifulSoup) -> list[str]:
        container = soup.select_one(
            "#tab-description, .woocommerce-Tabs-panel--description"
        )
        if not container:
            return []
        return [
            normalize_whitespace(line)
            for line in container.get_text("\n").splitlines()
            if normalize_whitespace(line)
        ]

    def _extract_spec_sections(self, lines: list[str]) -> list[SpecSection]:
        sections: list[SpecSection] = []
        current_title = "Περιγραφή"
        current_items: list[SpecItem] = []
        started_specs = False
        for line in lines:
            parsed = self._parse_spec_line(line)
            if parsed is not None:
                started_specs = True
                current_items.append(SpecItem(*parsed))
                continue
            if self._looks_like_section_heading(line, started_specs):
                if current_items:
                    sections.append(SpecSection(section=current_title, items=current_items))
                current_title = line
                current_items = []
        if current_items:
            sections.append(SpecSection(section=current_title, items=current_items))
        return self._dedupe_sections(sections)

    def _add_derived_washer_specs(
        self, sections: list[SpecSection], title: str, lines: list[str]
    ) -> None:
        labels = {
            normalize_for_match(item.label)
            for section in sections
            for item in section.items
        }
        loading_label = normalize_for_match("Τρόπος Φόρτωσης")
        if loading_label in labels or normalize_for_match("Τύπος Φόρτωσης") in labels:
            return

        combined = normalize_for_match(" ".join([title, *lines]))
        loading_value = ""
        if "εμπροσθ" in combined or "front" in combined:
            loading_value = "Εμπρόσθιας Φόρτωσης"
        elif "ανω φορτω" in combined or "top load" in combined:
            loading_value = "Άνω Φόρτωσης"
        if not loading_value:
            return

        target = sections[0] if sections else None
        if target is None:
            sections.append(
                SpecSection(
                    section="Περιγραφή",
                    items=[SpecItem("Τρόπος Φόρτωσης", loading_value)],
                )
            )
            return
        target.items.append(SpecItem("Τρόπος Φόρτωσης", loading_value))

    def _parse_spec_line(self, line: str) -> tuple[str, str] | None:
        if ":" not in line:
            return None
        label, value = line.split(":", 1)
        label = normalize_whitespace(label).strip(" :")
        value = normalize_whitespace(value).strip(" :")
        if not label or not value:
            return None
        if len(label) > 90 or len(value) > 220:
            return None
        return label, value

    def _looks_like_section_heading(self, line: str, started_specs: bool) -> bool:
        if ":" in line:
            return False
        if not started_specs and normalize_for_match(line) != normalize_for_match(
            "Βασικά Στοιχεία"
        ):
            return False
        word_count = len(line.split())
        return 1 <= word_count <= 5

    def _extract_breadcrumbs(self, soup: BeautifulSoup) -> list[str]:
        values = [
            safe_text(node)
            for node in soup.select(".woocommerce-breadcrumb a, nav.breadcrumbs a")
            if safe_text(node)
        ]
        return [
            value
            for value in values
            if normalize_for_match(value)
            not in {
                normalize_for_match("Αρχική"),
                normalize_for_match("Home"),
            }
        ]

    def _extract_gallery_images(
        self, soup: BeautifulSoup, base_url: str, title: str
    ) -> list[GalleryImage]:
        candidates: list[str] = []
        for image in soup.select("figure.woocommerce-product-gallery__wrapper img"):
            for attr in ("data-large_image", "data-src", "src"):
                value = normalize_whitespace(str(image.get(attr) or ""))
                if value and re.search(r"\.(?:jpe?g|png|webp)(?:$|\?)", value, re.I):
                    candidates.append(make_absolute_url(value, base_url))
                    break
        urls = dedupe_urls_preserve_order(candidates)
        if len(urls) > 1:
            last = urls[-1]
            urls = [urls[0], last, *urls[1:-1]]
        return [
            GalleryImage(url=image_url, alt=title, position=position)
            for position, image_url in enumerate(urls, start=1)
        ]

    def _extract_price(
        self, soup: BeautifulSoup, jsonld: list[dict[str, Any]]
    ) -> tuple[str, float | None]:
        product_json = self._find_jsonld_type(jsonld, "Product")
        offers = product_json.get("offers") if product_json else {}
        if isinstance(offers, dict):
            raw_price = normalize_whitespace(str(offers.get("price") or ""))
            if raw_price:
                return raw_price, parse_euro_price(raw_price)
        node = soup.select_one(
            ".summary .price .woocommerce-Price-amount, [itemprop='price']"
        )
        price_text = normalize_whitespace(
            node.get("content") if node and node.has_attr("content") else safe_text(node)
        )
        return price_text, parse_euro_price(price_text) if price_text else None

    def _dedupe_sections(self, sections: list[SpecSection]) -> list[SpecSection]:
        out: list[SpecSection] = []
        seen: set[tuple[str, str]] = set()
        for section in sections:
            items: list[SpecItem] = []
            for item in section.items:
                label = normalize_whitespace(item.label)
                value = normalize_whitespace(item.value or "")
                key = (normalize_for_match(label), normalize_for_match(value))
                if not label or not value or key in seen:
                    continue
                seen.add(key)
                items.append(SpecItem(label, value))
            if items:
                out.append(SpecSection(section=section.section, items=items))
        return out

    def _collect_missing_fields(self, source: SourceProductData) -> list[str]:
        missing: list[str] = []
        if not source.name:
            missing.append("name")
        if not source.brand:
            missing.append("brand")
        if not source.mpn:
            missing.append("mpn")
        if not source.breadcrumbs:
            missing.append("breadcrumbs")
        if not source.gallery_images:
            missing.append("gallery_images")
        if not source.spec_sections:
            missing.append("spec_sections")
        return missing

    def _make_diagnostic(self, value: Any, strategy: str) -> FieldDiagnostic:
        present = self._value_present(value)
        preview = self._preview_value(value)
        return FieldDiagnostic(
            confidence=0.93 if present else 0.0,
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

    def _value_present(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(normalize_whitespace(value))
        if isinstance(value, list):
            return bool(value)
        return True

    def _preview_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return normalize_whitespace(value)[:200]
        if isinstance(value, list):
            return f"{len(value)} item(s)" if value else ""
        return normalize_whitespace(str(value))[:200]
