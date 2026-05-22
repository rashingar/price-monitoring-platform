from __future__ import annotations

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
    dedupe_urls_preserve_order,
    make_absolute_url,
    normalize_for_match,
    normalize_whitespace,
    safe_text,
)
from .skroutz_taxonomy import classify_skroutz_taxonomy, normalize_category_href_slug
from .utils import utcnow_iso

KOTSOVOLOS_PRODUCT_ID_RE = re.compile(r"/(\d{5,})-", re.IGNORECASE)
KOTSOVOLOS_MPN_RE = re.compile(r"\b([A-Z]{2,}\d+[A-Z0-9]*(?:[-/][A-Z0-9]+)+)\b")


class KotsovolosProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        canonical_url = self._extract_canonical_url(soup, url)
        title, title_source = self._extract_title(soup)
        brand = self._extract_brand(title)
        mpn = self._extract_mpn(title)
        product_code = self._extract_product_code(canonical_url)
        hero_summary = self._extract_summary(soup)
        category_text, category_href, source_breadcrumbs = self._extract_category(
            canonical_url
        )
        taxonomy_hint = classify_skroutz_taxonomy(
            category_tag_text=category_text,
            category_tag_href=category_href,
            title=title,
            url=canonical_url,
            brand=brand,
        )
        spec_items = self._extract_specs(soup, brand)
        spec_sections = (
            [SpecSection(section="Χαρακτηριστικά", items=spec_items)]
            if spec_items
            else []
        )
        gallery_images = self._extract_gallery_images(
            soup, canonical_url, title, product_code
        )

        source = SourceProductData(
            source_name="kotsovolos",
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=(
                taxonomy_hint.breadcrumbs
                if taxonomy_hint and taxonomy_hint.breadcrumbs
                else source_breadcrumbs
            ),
            skroutz_family=(
                taxonomy_hint.matched_rule_id.split(":", 1)[0]
                if taxonomy_hint and taxonomy_hint.matched_rule_id
                else ""
            ),
            category_tag_text=category_text,
            category_tag_href=category_href,
            category_tag_slug=normalize_category_href_slug(category_href),
            taxonomy_source_category=(
                taxonomy_hint.source_category if taxonomy_hint else ""
            ),
            taxonomy_match_type=taxonomy_hint.match_type if taxonomy_hint else "",
            taxonomy_rule_id=taxonomy_hint.matched_rule_id if taxonomy_hint else "",
            taxonomy_ambiguity=(
                bool(taxonomy_hint.ambiguous) if taxonomy_hint else False
            ),
            taxonomy_escalation_reason=(
                taxonomy_hint.escalation_reason if taxonomy_hint else ""
            ),
            taxonomy_tv_inches=taxonomy_hint.tv_inches if taxonomy_hint else None,
            product_code=product_code,
            brand=brand,
            mpn=mpn,
            name=title,
            hero_summary=hero_summary,
            gallery_images=gallery_images,
            key_specs=spec_items[:8],
            spec_sections=spec_sections,
            presentation_source_text=hero_summary,
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
        )
        provenance = {
            "name": title_source,
            "brand": "title:first_token" if brand else "missing",
            "mpn": "title:model_pattern" if mpn else "missing",
            "product_code": "url:product_id" if product_code else "missing",
            "breadcrumbs": "kotsovolos:url_category",
            "gallery_images": "meta.og:image" if gallery_images else "missing",
            "spec_sections": (
                ".product-charactristics-row" if spec_sections else "missing"
            ),
            "hero_summary": "meta.og:description" if hero_summary else "missing",
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
            ]
        }
        return ParsedProduct(
            source=source,
            provenance=provenance,
            field_diagnostics=diagnostics,
            missing_fields=self._collect_missing_fields(source),
            critical_missing=self._collect_critical_missing(source),
        )

    def _extract_canonical_url(self, soup: BeautifulSoup, fallback_url: str) -> str:
        node = soup.select_one("link[rel='canonical']")
        canonical = normalize_whitespace(node.get("href", "") if node else "")
        return make_absolute_url(canonical or fallback_url, fallback_url)

    def _extract_title(self, soup: BeautifulSoup) -> tuple[str, str]:
        node = soup.select_one("h1")
        if node is not None:
            title = safe_text(node)
            if title:
                return title, "h1"
        meta = soup.select_one("meta[property='og:title']")
        title = normalize_whitespace(meta.get("content", "") if meta else "")
        if title:
            return title.split("|", 1)[0].strip(), "meta.og:title"
        return "", "missing"

    def _extract_brand(self, title: str) -> str:
        return normalize_whitespace(title.split(" ", 1)[0]) if title else ""

    def _extract_mpn(self, title: str) -> str:
        match = KOTSOVOLOS_MPN_RE.search(title.upper())
        return match.group(1) if match else ""

    def _extract_product_code(self, url: str) -> str:
        match = KOTSOVOLOS_PRODUCT_ID_RE.search(url)
        return match.group(1) if match else ""

    def _extract_summary(self, soup: BeautifulSoup) -> str:
        for selector in ("meta[property='og:description']", "meta[name='description']"):
            meta = soup.select_one(selector)
            summary = normalize_whitespace(meta.get("content", "") if meta else "")
            if summary and "Computing" not in summary:
                return summary
        return ""

    def _extract_category(self, base_url: str) -> tuple[str, str, list[str]]:
        return (
            "Κλιματιστικά",
            make_absolute_url("/air-condition-heaters/air-condition", base_url),
            ["Αρχική", "Κλιματισμός - Θέρμανση", "Κλιματιστικά"],
        )

    def _extract_specs(self, soup: BeautifulSoup, brand: str) -> list[SpecItem]:
        items: list[SpecItem] = []
        seen: set[str] = set()
        if brand:
            items.append(SpecItem(label="Κατασκευαστής", value=brand))
            seen.add(normalize_for_match("Κατασκευαστής"))

        texts = [
            safe_text(node)
            for node in soup.select(".product-charactristics-row")
            if safe_text(node)
        ]
        for index in range(0, len(texts) - 1, 2):
            label = normalize_whitespace(texts[index])
            value = normalize_whitespace(texts[index + 1])
            key = normalize_for_match(label)
            if not label or not value or key in seen:
                continue
            seen.add(key)
            items.append(SpecItem(label=label, value=value))
        return items

    def _extract_gallery_images(
        self, soup: BeautifulSoup, base_url: str, title: str, product_code: str
    ) -> list[GalleryImage]:
        urls: list[str] = []
        meta = soup.select_one("meta[property='og:image']")
        if meta is not None:
            urls.append(str(meta.get("content") or ""))
        for image in soup.select("img[src]"):
            src = str(image.get("src") or "")
            if "assets.kotsovolos.gr/product/" not in src:
                continue
            if product_code and f"/product/{product_code}" not in src:
                continue
            if re.search(r"-(?:s|xs)\.(?:jpe?g|png|webp)(?:[?#].*)?$", src, re.I):
                continue
            urls.append(src)
        image_urls = dedupe_urls_preserve_order(
            [make_absolute_url(url, base_url) for url in urls]
        )
        return [
            GalleryImage(url=image_url, alt=title, position=index)
            for index, image_url in enumerate(image_urls, start=1)
        ]

    def _collect_missing_fields(self, source: SourceProductData) -> list[str]:
        missing: list[str] = []
        for field_name in ("name", "brand", "mpn", "breadcrumbs", "gallery_images"):
            if not getattr(source, field_name):
                missing.append(field_name)
        if not source.spec_sections:
            missing.append("spec_sections")
        return missing

    def _collect_critical_missing(self, source: SourceProductData) -> list[str]:
        critical = [
            field
            for field in ("name", "brand", "mpn", "gallery_images", "spec_sections")
            if field in self._collect_missing_fields(source)
        ]
        if source.taxonomy_ambiguity:
            critical.append("supported_family")
        return sorted(set(critical))

    def _make_diagnostic(self, value: Any, selected_strategy: str) -> FieldDiagnostic:
        present = bool(value)
        preview = ""
        if isinstance(value, str):
            preview = value[:160]
        elif isinstance(value, list) and value:
            preview = f"{len(value)} items"
        return FieldDiagnostic(
            confidence=0.9 if present else 0.0,
            selected_strategy=selected_strategy,
            value_present=present,
            value_preview=normalize_whitespace(preview),
            selector_trace=[
                SelectorTraceEntry(strategy=selected_strategy, success=present)
            ],
        )
