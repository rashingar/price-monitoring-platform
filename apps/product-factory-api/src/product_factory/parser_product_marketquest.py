from __future__ import annotations

import re

from bs4 import BeautifulSoup

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


class MarketQuestProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        canonical_url = self._extract_canonical_url(soup, url)
        title = self._extract_title(soup)
        brand = self._extract_brand(soup, title)
        mpn = self._extract_mpn(soup, title)
        product_code = self._extract_product_code(soup, canonical_url)
        description_text = self._extract_description_text(soup)
        info_items = self._extract_info_items(soup)
        spec_items = self._extract_spec_items(
            brand=brand,
            title=title,
            mpn=mpn,
            info_items=info_items,
            description_text=description_text,
        )
        breadcrumbs = clean_breadcrumbs(self._extract_breadcrumbs(soup))
        gallery_images = self._extract_gallery_images(soup, canonical_url, title)
        price_text, price_value = self._extract_price(soup)
        category_text = breadcrumbs[-1] if breadcrumbs else ""

        source = SourceProductData(
            source_name="marketquest",
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=breadcrumbs,
            category_tag_text=category_text,
            taxonomy_source_category=category_text,
            product_code=product_code,
            brand=brand,
            mpn=mpn,
            name=title,
            hero_summary=description_text,
            price_text=price_text,
            price_value=price_value,
            gallery_images=gallery_images,
            key_specs=spec_items[:10],
            spec_sections=(
                [SpecSection(section="Πληροφορίες", items=spec_items)]
                if spec_items
                else []
            ),
            presentation_source_html=str(
                soup.select_one("#products_description") or ""
            ),
            presentation_source_text=description_text,
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
        )
        provenance = {
            "name": "dom:.product-right h2/meta:title" if title else "missing",
            "brand": "dom:.product-right h5/title" if brand else "missing",
            "mpn": "dom:#products_mpn/title" if mpn else "missing",
            "product_code": "dom:#products_model/url" if product_code else "missing",
            "breadcrumbs": "dom:.breadcrumb a" if breadcrumbs else "missing",
            "gallery_images": "dom:.product-slick a.lightbox" if gallery_images else "missing",
            "spec_sections": "dom:#products_perigrafi-tabcontent li" if spec_items else "missing",
            "hero_summary": "dom:#products_description/meta:description"
            if description_text
            else "missing",
            "presentation_blocks": "not_applicable:marketquest_description_tab",
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
        warnings = []
        if not info_items:
            warnings.append("marketquest_info_tab_missing")
        if not gallery_images:
            warnings.append("gallery_images_missing")
        return ParsedProduct(
            source=source,
            provenance=provenance,
            field_diagnostics=diagnostics,
            missing_fields=missing_fields,
            critical_missing=self._collect_critical_missing(missing_fields),
            warnings=warnings,
        )

    def _extract_canonical_url(self, soup: BeautifulSoup, fallback_url: str) -> str:
        node = soup.select_one("link[rel='canonical']")
        canonical = normalize_whitespace(node.get("href", "") if node else "")
        return make_absolute_url(canonical or fallback_url, fallback_url)

    def _extract_title(self, soup: BeautifulSoup) -> str:
        title = safe_text(soup.select_one(".product-right h2"))
        if title:
            return title
        meta = soup.select_one("meta[property='og:title']")
        title = normalize_whitespace(meta.get("content", "") if meta else "")
        if title:
            return title.split("|", 1)[0].strip()
        return normalize_whitespace((soup.title.get_text() if soup.title else "").split("|", 1)[0])

    def _extract_brand(self, soup: BeautifulSoup, title: str) -> str:
        for node in soup.select(".product-right h5"):
            text = safe_text(node)
            if not text:
                continue
            first_line = text.split("Κωδικός", 1)[0].strip()
            if first_line and len(first_line.split()) <= 3:
                return first_line
        return normalize_whitespace(title.split(" ", 1)[0]) if title else ""

    def _extract_mpn(self, soup: BeautifulSoup, title: str) -> str:
        value = safe_text(soup.select_one("#products_mpn"))
        if value:
            token_match = re.search(r"\bA\d{5,}\b", value, re.I)
            return token_match.group(0) if token_match else value
        token_match = re.search(r"\bA\d{5,}[A-Z0-9 _-]*\b", title, re.I)
        if token_match:
            return normalize_whitespace(token_match.group(0))
        return extract_mpn_from_name(title)

    def _extract_product_code(self, soup: BeautifulSoup, canonical_url: str) -> str:
        value = safe_text(soup.select_one("#products_model"))
        if value:
            return value
        match = re.search(r"/product/(\d+)/", canonical_url)
        return match.group(1) if match else ""

    def _extract_description_text(self, soup: BeautifulSoup) -> str:
        text = safe_text(soup.select_one("#products_description"))
        if text:
            return text
        meta = soup.select_one("meta[name='description']")
        return normalize_whitespace(meta.get("content", "") if meta else "")

    def _extract_info_items(self, soup: BeautifulSoup) -> list[str]:
        out: list[str] = []
        for node in soup.select("#products_perigrafi-tabcontent li"):
            text = safe_text(node)
            if text:
                out.append(text)
        return list(dict.fromkeys(out))

    def _extract_spec_items(
        self,
        *,
        brand: str,
        title: str,
        mpn: str,
        info_items: list[str],
        description_text: str,
    ) -> list[SpecItem]:
        evidence = normalize_whitespace(" ".join([title, description_text, *info_items]))
        evidence_norm = normalize_for_match(evidence)
        items: list[SpecItem] = []
        if brand:
            items.append(SpecItem("Κατασκευαστής", brand))
        if mpn:
            items.append(SpecItem("MPN", mpn))
        diameter = self._extract_diameter(evidence)
        if diameter:
            items.extend(
                [
                    SpecItem("Μέγεθος", diameter),
                    SpecItem("Διάμετρος Σκεύους σε Εκατοστά.", diameter),
                ]
            )
        if "grill" in evidence_norm or "ραβδω" in evidence_norm:
            items.append(SpecItem("Τύπος Σκεύους", "Τηγάνι Grill"))
        elif "τηγαν" in evidence_norm:
            items.append(SpecItem("Τύπος Σκεύους", "Τηγάνι"))
        if "ανοξειδωτο" in evidence_norm or "inox" in evidence_norm:
            items.append(SpecItem("Υλικό Σκεύους", "Ανοξείδωτο Ατσάλι"))
        if "χωρις αντικολλητικ" in evidence_norm:
            items.append(SpecItem("Εσωτερική Επίστρωση", "Χωρίς Αντικολλητική Επίστρωση"))
        elif "αντικολλητικ" in evidence_norm:
            items.append(SpecItem("Εσωτερική Επίστρωση", "Αντικολλητική"))
        if "γυαλισμεν" in evidence_norm:
            items.append(SpecItem("Εξωτερική Επίστρωση", "Γυαλισμένη"))
        if "σατινε" in evidence_norm:
            items.append(SpecItem("Εσωτερική Επιφάνεια", "Σατινέ"))
        if "επαγωγ" in evidence_norm or "full induction" in evidence_norm:
            items.append(
                SpecItem(
                    "Πηγή Θερμότητας",
                    "Κεραμική - Ηλεκτρική - Αερίου - Επαγωγική",
                )
            )
            items.append(SpecItem("Κατάλληλη Εστία", "Επαγωγική"))
        oven = self._extract_oven_temperature(evidence)
        if oven:
            items.append(SpecItem("Κατάλληλο για Φούρνο", oven))
        elif "φουρν" in evidence_norm:
            items.append(SpecItem("Κατάλληλο για Φούρνο", "Ναι"))
        if "πλυντηριο πιατων" in evidence_norm:
            items.append(SpecItem("Πλυντήριο Πιάτων", "Ναι"))
        for index, item in enumerate(info_items, start=1):
            items.append(SpecItem(f"Πληροφορία {index}", item))
        return self._dedupe_spec_items(items)

    def _extract_diameter(self, text: str) -> str:
        match = re.search(r"(?<!\d)(\d{2})(?:[,.]\d+)?\s*cm\b", text, re.I)
        return f"{match.group(1)}cm" if match else ""

    def _extract_oven_temperature(self, text: str) -> str:
        match = re.search(r"φούρνο\s*(?:έως|ως|μέχρι)?\s*(\d+)\s*°?\s*C", text, re.I)
        return f"Έως {match.group(1)}°C" if match else ""

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
        self, soup: BeautifulSoup, base_url: str, title: str
    ) -> list[GalleryImage]:
        candidates: list[str] = []
        for node in soup.select(".product-slick a.lightbox, .product_images a.lightbox"):
            value = normalize_whitespace(str(node.get("href") or ""))
            if value:
                candidates.append(value)
        for node in soup.select(".product-slick img, .product_images img"):
            for attr in ("data-src", "src"):
                value = normalize_whitespace(str(node.get(attr) or ""))
                if value and "thumbnails/" not in value:
                    candidates.append(value)
        urls = dedupe_urls_preserve_order(
            [
                make_absolute_url(self._marketquest_asset_path(candidate), base_url)
                for candidate in candidates
                if candidate
            ]
        )
        return [
            GalleryImage(url=image_url, alt=title, position=index)
            for index, image_url in enumerate(urls, start=1)
        ]

    def _marketquest_asset_path(self, value: str) -> str:
        candidate = normalize_whitespace(value)
        if re.match(r"^[a-z][a-z0-9+.-]*://", candidate, re.I):
            return candidate
        if candidate.startswith("/"):
            return candidate
        if candidate.startswith(("images/", "assets/", "thumbnails/")):
            return f"/{candidate}"
        return candidate

    def _extract_price(self, soup: BeautifulSoup) -> tuple[str, float | None]:
        for selector in (".product-right .price", ".product-price", "[itemprop='price']"):
            node = soup.select_one(selector)
            text = safe_text(node) or normalize_whitespace(
                str(node.get("content", "") if node else "")
            )
            if parse_euro_price(text) is not None:
                return text, parse_euro_price(text)
        return "", None

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
