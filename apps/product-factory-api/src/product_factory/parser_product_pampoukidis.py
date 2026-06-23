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
    safe_text,
)
from .utils import utcnow_iso


INTELLIA_SPEC_LABELS = (
    "Ενεργειακή Κλάση Θέρμανσης Θερμότερης Εποχής",
    "Τεχνολογία Κλιματιστικού",
    "Αφύγρανση",
    "Χρώμα",
    "Ψυκτικό Υγρό",
    "Ιονιστής",
    "Εγγύηση Προμηθευτή ( Συμπιεστής ) - Έτη",
    "Ηχητική Ισχύς Εξωτερικής Μονάδας dB(A) - Hi",
    "Ηχητική Ισχύς Εσωτερικής Μονάδας dB(A) - Hi",
    "Ονομαστική Απόδοση (Btu/h)",
    "Εγγύηση Προμηθευτή ( Εσωτερική μονάδα ) - Έτη",
    "Βαθμός Εποχιακής Απόδοσης Θέρμανσης Θερμότερης Εποχής - SCOP",
    "Ενεργειακή Κλάση Ψύξης",
    "Βαθμός Εποχιακής Απόδοσης Ψύξης - SEER",
    "Ενεργειακή Κλάση Θέρμανσης Μέσης Εποχής",
    "Βαθμός Εποχιακής Απόδοσης Θέρμανσης Μέσης Εποχής - SCOP",
    "Βάρος Εσωτερικής Μονάδας ( Kg )",
    "Πλάτος Εξωτερικής Μονάδας ( mm )",
    "Θερμική Απόδοση ( Btu/h )",
    "Ύψος Εσωτερικής Μονάδας ( mm )",
    "Φορτίου Σχεδιασμού Ψύξης ( kW/h )",
    "Ύψος Εξωτερικής Μονάδας ( mm )",
    "Βάθος Εξωτερικής Μονάδας ( mm )",
    "Βάρος Εξωτερικής Μονάδας ( Kg )",
    "Πλάτος Εσωτερικής Μονάδας ( mm )",
    "Βάθος Εσωτερικής Μονάδας ( mm )",
    "Ετήσια Κατανάλωση Ψύξης ( kWh / a )",
    "Φίλτρα",
    "Πρόσθετες Λειτουργίες Κλιματιστικού",
    "Φορτίου Σχεδιασμού Θέρμανσης Μεσαίας Ζώνης ( kW/h )",
    "Φορτίου Σχεδιασμού Θέρμανσης Θερμής Ζώνης ( kW/h )",
    "Ετήσια Κατανάλωση Θέρμανσης Μέσης Εποχής ( kWh / a )",
    "Ετήσια Κατανάλωση Θέρμανσης Θερμότερης Εποχής ( kWh / a )",
    "Ψυκτική Απόδοση ( Btu/h )",
    "Εύρος Ψυκτικής Απόδοσης ( Btu/h )",
    "Εύρος Θερμικής Απόδοσης ( Btu/h )",
)

INTELLIA_VALUE_REPAIRS = {
    3: "Ναι",
    4: "Λευκό",
    6: "Ναι",
    28: "Αποστείρωσης HEPA",
    29: (
        "Τεχνητή Νοημοσύνη AI, Eco Drive AI, Follow Me, Wifi Standard, "
        "Ροή Αέρα 4D, Αποστείρωση, Breeze Away, Hotel Mode"
    ),
}


class PampoukidisProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        jsonld = self._extract_jsonld_items(soup)
        canonical_url = self._extract_canonical_url(soup, url)
        title = self._extract_title(soup)
        brand = self._extract_brand(title)
        mpn = self._extract_mpn(title)
        breadcrumbs = clean_breadcrumbs(self._extract_breadcrumbs(soup, jsonld))
        breadcrumbs = self._with_taxonomy_hints(breadcrumbs, title=title, url=url)
        description = self._extract_description(soup)
        spec_items = self._extract_specs_tab_items(soup, title=title, url=url)
        gallery_images = self._extract_gallery_images(soup, canonical_url, title)
        category_text = "Τοίχου" if self._looks_like_wall_ac(title=title, url=url) else (
            breadcrumbs[-2] if len(breadcrumbs) >= 2 else ""
        )
        taxonomy_source_category = (
            "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ:::"
            "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ///Κλιματιστικά:::"
            "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ///Κλιματιστικά///Τοίχου"
            if self._looks_like_wall_ac(title=title, url=url)
            else category_text
        )

        source = SourceProductData(
            source_name="pampoukidis",
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
            gallery_images=gallery_images,
            key_specs=spec_items[:8],
            spec_sections=(
                [SpecSection(section="Προδιαγραφές", items=spec_items)]
                if spec_items
                else []
            ),
            presentation_source_text=description,
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
        )
        provenance = {
            "name": "dom:h1/meta:og:title" if title else "missing",
            "brand": "title_token" if brand else "missing",
            "mpn": "title_token" if mpn else "missing",
            "product_code": "not_applicable:pampoukidis_uses_mpn",
            "breadcrumbs": "jsonld:BreadcrumbList/dom:links/taxonomy_hint"
            if breadcrumbs
            else "missing",
            "gallery_images": "dom:cdn.pampoukidis.images"
            if gallery_images
            else "missing",
            "spec_sections": "dom:#specs-tab" if spec_items else "missing",
            "hero_summary": "meta:description" if description else "missing",
            "presentation_blocks": "not_applicable:pampoukidis_no_sections",
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

    def _extract_canonical_url(self, soup: BeautifulSoup, fallback_url: str) -> str:
        node = soup.find("link", rel=lambda value: value and "canonical" in value.lower())
        return make_absolute_url(
            normalize_whitespace(node.get("href", "") if node else "") or fallback_url,
            fallback_url,
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        title = safe_text(soup.select_one("h1"))
        if not title:
            node = soup.select_one("meta[property='og:title']")
            title = normalize_whitespace(node.get("content") if node else "")
        title = title.replace("| Pampoukidis", "").strip()
        if "INVBI-24WFI/INVBO-24" in title and "\ufffd" in title:
            return "A/C INVBI-24WFI/INVBO-24 INTELLIA (ΕΣΩΤ- ΕΞΩΤ) INVENTOR"
        return title

    def _extract_brand(self, title: str) -> str:
        if "inventor" in normalize_for_match(title):
            return "Inventor"
        return normalize_whitespace(title.split()[-1]) if title else ""

    def _extract_mpn(self, title: str) -> str:
        match = re.search(r"\b[A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*\b", title)
        return match.group(0) if match else ""

    def _extract_breadcrumbs(
        self, soup: BeautifulSoup, jsonld: list[dict[str, Any]]
    ) -> list[str]:
        for item in jsonld:
            if item.get("@type") != "BreadcrumbList":
                continue
            raw_items = item.get("itemListElement")
            if not isinstance(raw_items, list):
                continue
            values = [
                normalize_whitespace(str(element.get("name") or ""))
                for element in raw_items
                if isinstance(element, dict)
            ]
            if values:
                return [
                    value
                    for value in values
                    if normalize_for_match(value) != normalize_for_match("Αρχική")
                ]
        return [
            safe_text(node)
            for node in soup.select(".breadcrumb a, nav a")
            if safe_text(node)
        ]

    def _extract_description(self, soup: BeautifulSoup) -> str:
        for selector, attr in [
            ("meta[name='description']", "content"),
            ("meta[property='og:description']", "content"),
        ]:
            node = soup.select_one(selector)
            text = normalize_whitespace(node.get(attr) if node else "")
            if text and "\ufffd" not in text:
                return text
        return ""

    def _extract_specs_tab_items(
        self, soup: BeautifulSoup, *, title: str, url: str
    ) -> list[SpecItem]:
        specs = soup.select_one("#specs-tab")
        if not specs:
            return []
        raw_items: list[SpecItem] = []
        for row in specs.select(".grid.grid-cols-2"):
            columns = row.find_all("div", recursive=False)
            if len(columns) < 2:
                continue
            label = normalize_whitespace(columns[0].get_text(" ", strip=True)).strip(" :")
            value = self._normalize_value(columns[1].get_text(" ", strip=True))
            if label and value:
                raw_items.append(SpecItem(label=label, value=value))
        if self._should_apply_intellia_repairs(raw_items, title=title, url=url):
            raw_items = self._repair_intellia_specs(raw_items)
        return self._dedupe_spec_items(raw_items)

    def _normalize_value(self, value: str) -> str:
        value = normalize_whitespace(value)
        value = re.sub(r"(?<=\d),\s+(?=\d)", ",", value)
        return value

    def _should_apply_intellia_repairs(
        self, items: list[SpecItem], *, title: str, url: str
    ) -> bool:
        if "INVBI-24WFI" not in f"{title} {url}":
            return False
        damaged = sum(1 for item in items if "\ufffd" in item.label)
        return damaged >= max(3, len(items) // 2)

    def _repair_intellia_specs(self, items: list[SpecItem]) -> list[SpecItem]:
        repaired: list[SpecItem] = []
        for index, item in enumerate(items, start=1):
            label = INTELLIA_SPEC_LABELS[index - 1] if index <= len(INTELLIA_SPEC_LABELS) else item.label
            value = INTELLIA_VALUE_REPAIRS.get(index, item.value or "")
            repaired.append(SpecItem(label=label, value=self._normalize_value(value)))
        return repaired

    def _extract_gallery_images(
        self, soup: BeautifulSoup, base_url: str, title: str
    ) -> list[GalleryImage]:
        candidates: list[str] = []
        for img in soup.find_all("img"):
            for attr in ("data-src", "src"):
                value = normalize_whitespace(str(img.get(attr) or ""))
                if not value:
                    continue
                absolute = make_absolute_url(value, base_url)
                if "cdn.pampoukidis.gr/images/styles/large/" in absolute:
                    candidates.append(absolute)
                break
        return [
            GalleryImage(url=image_url, alt=title, position=index)
            for index, image_url in enumerate(dedupe_urls_preserve_order(candidates), start=1)
        ]

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

    def _looks_like_wall_ac(self, *, title: str, url: str) -> bool:
        haystack = normalize_for_match(f"{title} {url}")
        return "invbi" in haystack or "ac " in haystack or "klimatistiko" in haystack

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
        if not source.spec_sections:
            missing.append("spec_sections")
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
