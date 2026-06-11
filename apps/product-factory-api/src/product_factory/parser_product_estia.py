from __future__ import annotations

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
    safe_text,
)
from .utils import utcnow_iso

ESTIA_THERMOS_BREADCRUMBS = [
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
    "Καφές-Ροφήματα-Χυμοί",
    "Αξεσουάρ-Αναλώσιμα-Θερμός",
]
ESTIA_THERMOS_CATEGORY_URL = (
    "https://www.etranoulis.gr/oikiakos-eksoplismos/"
    "kafes-rofhmata-xhmoi/kaf-aksesouar-analwsima-thermos"
)
THERMOS_BASE_RE = re.compile(
    r"^(?P<base>ΘΕΡΜΟΣ\s+STRAW\s+TUMBLER\s+XL\s+"
    r"(?:(?:StA\s+)?(?:SAVE\s+THE\s+AEGEAN\s+)?(?P<volume>\d+(?:[.,]\d+)?\s*ml)))"
    r"\s+(?P<variant>.+)$",
    re.IGNORECASE,
)


class EstiaProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        product_root = self._find_product_root(soup)
        tabs_root = soup.select_one(".productTabs") or product_root
        canonical_url = self._extract_canonical_url(soup, url)
        title = self._extract_title(product_root, soup)
        brand = self._extract_brand(product_root, title)
        product_code = self._extract_product_code(product_root, canonical_url)
        normalized_name = normalize_estia_product_name(title, brand=brand or "Estia")
        description_html, description_text = self._extract_description(tabs_root)
        characteristics = self._extract_table_items(
            tabs_root.select_one("#quickTab-specifications")
        )
        volumetric = self._extract_table_items(tabs_root.select_one("#quickTab-elem"))
        spec_sections = []
        if characteristics:
            spec_sections.append(SpecSection("Χαρακτηριστικά", characteristics))
        if volumetric:
            spec_sections.append(SpecSection("Ογκομετρικά Στοιχεία", volumetric))
        key_specs = self._dedupe_spec_items([*characteristics, *volumetric])[:10]
        gallery_images = self._extract_gallery_images(product_root, canonical_url, title)
        breadcrumbs = self._extract_breadcrumbs(soup)
        source_breadcrumbs = clean_breadcrumbs(breadcrumbs or ESTIA_THERMOS_BREADCRUMBS)
        mapped_breadcrumbs = self._map_thermos_breadcrumbs(source_breadcrumbs, title)

        source = SourceProductData(
            source_name="estia",
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=mapped_breadcrumbs,
            category_tag_text="Αξεσουάρ-Αναλώσιμα-Θερμός",
            category_tag_href=ESTIA_THERMOS_CATEGORY_URL,
            category_tag_slug="aksesouar-analosima-thermos",
            taxonomy_source_category="Αξεσουάρ-Αναλώσιμα-Θερμός",
            product_code=product_code,
            brand=brand or "Estia",
            mpn=product_code,
            name=normalized_name or title,
            hero_summary=description_text,
            gallery_images=gallery_images,
            key_specs=key_specs,
            spec_sections=spec_sections,
            presentation_source_html="",
            presentation_source_text=description_text,
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
        )
        provenance = {
            "name": "estia:name_normalization" if normalized_name else "h1",
            "brand": "dom:.overview brand" if brand else "fallback:Estia",
            "mpn": "dom:.overview product-code" if product_code else "url:path",
            "product_code": "dom:.overview product-code" if product_code else "url:path",
            "breadcrumbs": (
                "estia:thermos_category_mapping"
                if mapped_breadcrumbs != source_breadcrumbs
                else "dom:.breadcrumb"
            ),
            "gallery_images": (
                "dom:.gallery .picture-link[data-full-image-url]"
                if gallery_images
                else "missing"
            ),
            "spec_sections": "dom:.productTabs tables" if spec_sections else "missing",
            "hero_summary": "dom:#quickTab-description" if description_text else "missing",
            "presentation_blocks": (
                "not_applicable:estia_no_presentation_sections"
            ),
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
            critical_missing=self._collect_critical_missing(missing_fields),
            warnings=[] if gallery_images else ["gallery_images_missing"],
        )

    def _find_product_root(self, soup: BeautifulSoup) -> Tag | BeautifulSoup:
        for selector in (".product-essential", ".product-details-page", "main"):
            node = soup.select_one(selector)
            if node:
                return node
        return soup.body or soup

    def _extract_canonical_url(self, soup: BeautifulSoup, fallback_url: str) -> str:
        node = soup.select_one("link[rel='canonical']")
        canonical = normalize_whitespace(node.get("href", "") if node else "")
        return make_absolute_url(canonical or fallback_url, fallback_url)

    def _extract_title(self, product_root: Tag | BeautifulSoup, soup: BeautifulSoup) -> str:
        for selector in (".product-name h1", "h1", "meta[property='og:title']"):
            node = product_root.select_one(selector) or soup.select_one(selector)
            if not node:
                continue
            value = (
                normalize_whitespace(node.get("content", ""))
                if node.name == "meta"
                else safe_text(node)
            )
            if value:
                return value.replace("εstia Home Art.", "").strip()
        return ""

    def _extract_brand(self, product_root: Tag | BeautifulSoup, title: str) -> str:
        for selector in (".overview .manufacturers a", ".overview a[href*='estia']"):
            node = product_root.select_one(selector)
            value = safe_text(node)
            if value:
                return value
        text = safe_text(product_root)
        match = re.search(r"\bBrand\s*:\s*([^\n\r]+?)(?:\s{2,}|Κωδ|$)", text, re.I)
        if match:
            return normalize_whitespace(match.group(1))
        return "Estia" if "estia" in normalize_for_match(title) else ""

    def _extract_product_code(
        self, product_root: Tag | BeautifulSoup, canonical_url: str
    ) -> str:
        text = safe_text(product_root)
        match = re.search(r"(\d{2}-\d{4,})", text)
        if match:
            return match.group(1)
        path_code = canonical_url.rstrip("/").rsplit("/", 1)[-1]
        return path_code if re.match(r"^[A-Za-z0-9_-]+$", path_code) else ""

    def _extract_description(self, tabs_root: Tag | BeautifulSoup) -> tuple[str, str]:
        node = tabs_root.select_one("#quickTab-description .full-description")
        if not node:
            node = tabs_root.select_one(".full-description")
        if not node:
            return "", ""
        return str(node), safe_text(node)

    def _extract_table_items(self, root: Tag | BeautifulSoup | None) -> list[SpecItem]:
        if root is None:
            return []
        items: list[SpecItem] = []
        for row in root.select("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label = normalize_whitespace(safe_text(cells[0]).rstrip(":"))
            value = normalize_whitespace(safe_text(cells[1]))
            if not label or not value:
                continue
            if normalize_for_match(label) in {
                normalize_for_match("Όνομα χαρακτηριστικού"),
                normalize_for_match("Τιμή χαρακτηριστικού"),
            }:
                continue
            items.append(SpecItem(label, value))
        return self._dedupe_spec_items(items)

    def _extract_gallery_images(
        self, product_root: Tag | BeautifulSoup, base_url: str, title: str
    ) -> list[GalleryImage]:
        gallery = product_root.select_one(".gallery")
        if not gallery:
            return []
        candidates: list[str] = []
        for node in gallery.select(
            "a[data-full-image-url], a[href] img, img[src], img[data-src]"
        ):
            if node.name == "a":
                candidates.append(str(node.get("data-full-image-url") or node.get("href") or ""))
                continue
            parent = node.parent if isinstance(node.parent, Tag) else None
            candidates.append(
                str(
                    (parent.get("data-full-image-url") if parent else "")
                    or (parent.get("href") if parent else "")
                    or node.get("data-full-image-url")
                    or node.get("data-src")
                    or node.get("src")
                    or ""
                )
            )
        urls = [
            url
            for url in dedupe_urls_preserve_order(
                [make_absolute_url(candidate, base_url) for candidate in candidates]
            )
            if self._is_product_image_url(url)
        ]
        return [
            GalleryImage(url=image_url, alt=title, position=index)
            for index, image_url in enumerate(urls, start=1)
        ]

    def _is_product_image_url(self, url: str) -> bool:
        normalized = normalize_for_match(url)
        if not url or "/images/thumbs/" not in url:
            return False
        blocked = ("logo", "default image", "category", "facebook", "twitter")
        return not any(token in normalized for token in blocked)

    def _extract_breadcrumbs(self, soup: BeautifulSoup) -> list[str]:
        nodes = soup.select(".breadcrumb a, .breadcrumb li, .breadcrumb span")
        return clean_breadcrumbs([safe_text(node) for node in nodes if safe_text(node)])

    def _map_thermos_breadcrumbs(self, breadcrumbs: list[str], title: str) -> list[str]:
        haystack = normalize_for_match(" ".join([title, *breadcrumbs]))
        if "θερμος" in haystack or "straw tumbler" in haystack:
            return list(ESTIA_THERMOS_BREADCRUMBS)
        return breadcrumbs

    def _dedupe_spec_items(self, items: list[SpecItem]) -> list[SpecItem]:
        out: list[SpecItem] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            key = (normalize_for_match(item.label), normalize_for_match(item.value or ""))
            if not key[0] or key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _collect_missing_fields(self, source: SourceProductData) -> list[str]:
        missing: list[str] = []
        for field_name in ("name", "brand", "mpn", "breadcrumbs", "gallery_images"):
            if not getattr(source, field_name):
                missing.append(field_name)
        if not source.spec_sections:
            missing.append("spec_sections")
        if not source.hero_summary:
            missing.append("hero_summary")
        return missing

    def _collect_critical_missing(self, missing_fields: list[str]) -> list[str]:
        return [field for field in missing_fields if field in {"name", "gallery_images"}]

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


def normalize_estia_product_name(source_name: str, *, brand: str = "Estia") -> str:
    name = normalize_whitespace(source_name)
    brand = normalize_whitespace(brand) or "Estia"
    if not name:
        return ""
    name = re.sub(rf"\s+{re.escape(brand)}\s*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^\s*estia\s+", "", name, flags=re.IGNORECASE)
    match = THERMOS_BASE_RE.match(name)
    if match:
        base = _normalize_thermos_base(match.group("base"), match.group("volume"))
        variant = _title_case_preserving_tokens(match.group("variant"))
        return f"{brand} {variant} - {base}" if variant else f"{brand} - {base}"
    return f"{brand} {_title_case_preserving_tokens(name)}"


def _normalize_thermos_base(base: str, volume: str) -> str:
    del base
    compact_volume = normalize_whitespace(volume).replace(" ", "")
    return f"Θερμός Straw Tumbler XL StA {compact_volume}"


def _title_case_preserving_tokens(value: str) -> str:
    tokens = normalize_whitespace(value).split()
    return " ".join(_title_token(token) for token in tokens)


def _title_token(token: str) -> str:
    if re.fullmatch(r"\d+(?:[.,]\d+)?\s*(?:ml|lt|l)", token, re.IGNORECASE):
        return token
    if token.upper() in {"XL", "BPA"}:
        return token.upper()
    if token.lower() == "sta":
        return "StA"
    if normalize_for_match(token) == "θερμος":
        return "Θερμός"
    if not token:
        return token
    return token[:1].upper() + token[1:].lower()
