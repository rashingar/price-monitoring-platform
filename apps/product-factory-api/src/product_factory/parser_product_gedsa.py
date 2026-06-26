from __future__ import annotations

import json
import re
from html import escape
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
from .skroutz_taxonomy import build_breadcrumbs, serialize_source_category
from .utils import utcnow_iso

AC_PARENT_CATEGORY = "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ"
AC_LEAF_CATEGORY = "Κλιματιστικά"
AC_SUB_CATEGORY = "Τοίχου"
STANDARD_AC_BTU_BUCKETS = (9000, 12000, 14000, 15000, 18000, 21000, 22000, 24000)


class GedsaProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        jsonld = self._extract_jsonld_items(soup)
        canonical_url = self._extract_canonical_url(soup, jsonld, url)
        title = self._extract_title(soup, jsonld)
        brand = self._extract_brand(soup, title)
        mpn = self._extract_mpn(soup, title)
        spec_items = self._extract_spec_items(soup)
        nominal_btu = self._first_btu_capacity(spec_items, title)
        display_name = self._build_display_name(brand, mpn, nominal_btu, title)
        description = self._extract_description(soup, jsonld)
        gallery_images = self._extract_gallery_images(soup, canonical_url, display_name)
        energy_label_url, product_sheet_url, documents = self._extract_documents(
            soup, canonical_url
        )
        presentation_html, presentation_text = self._extract_presentation_source(
            soup, canonical_url
        )
        breadcrumbs = build_breadcrumbs(AC_PARENT_CATEGORY, AC_LEAF_CATEGORY, AC_SUB_CATEGORY)

        source = SourceProductData(
            source_name="gedsa",
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=breadcrumbs,
            category_tag_text=AC_SUB_CATEGORY,
            taxonomy_source_category=serialize_source_category(
                AC_PARENT_CATEGORY, AC_LEAF_CATEGORY, [AC_SUB_CATEGORY]
            ),
            taxonomy_match_type="exact_category",
            taxonomy_rule_id="gedsa:wall_ac",
            product_code=mpn.split("/", 1)[0] if mpn else "",
            brand=brand,
            mpn=mpn,
            name=display_name,
            hero_summary=description,
            gallery_images=gallery_images,
            energy_label_asset_url=energy_label_url,
            product_sheet_asset_url=product_sheet_url,
            key_specs=spec_items[:10],
            spec_sections=(
                [SpecSection(section="Τεχνικά Χαρακτηριστικά", items=spec_items)]
                if spec_items
                else []
            ),
            manufacturer_documents=documents,
            manufacturer_source_text=self._source_text(spec_items),
            presentation_source_html=presentation_html,
            presentation_source_text=presentation_text or description,
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
        )
        provenance = {
            "name": "dom:elementor headings/specs" if display_name else "missing",
            "brand": "dom:brand nav/title" if brand else "missing",
            "mpn": "dom:model headings/title" if mpn else "missing",
            "product_code": "dom:model headings" if source.product_code else "missing",
            "breadcrumbs": "rule:gedsa_wall_ac",
            "gallery_images": "dom:.elementor-widget-gallery a[href]"
            if gallery_images
            else "missing",
            "spec_sections": "dom:elementor two-column h4 specs"
            if spec_items
            else "missing",
            "hero_summary": "jsonld.description/meta.description/dom:intro"
            if description
            else "missing",
            "energy_label_asset_url": "dom:support pdf Energy-label"
            if energy_label_url
            else "missing",
            "presentation_blocks": "dom:.elementor-image-box-wrapper",
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
                    "energy_label_asset_url",
                    "energy_label_asset_url",
                    provenance["energy_label_asset_url"],
                ),
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
        if not energy_label_url:
            warnings.append("energy_label_asset_missing")
        return ParsedProduct(
            source=source,
            provenance=provenance,
            field_diagnostics=diagnostics,
            missing_fields=missing_fields,
            critical_missing=[
                field for field in missing_fields if field in {"name", "brand", "gallery_images"}
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

    def _extract_canonical_url(
        self, soup: BeautifulSoup, jsonld: list[dict[str, Any]], fallback_url: str
    ) -> str:
        node = soup.find("link", rel=lambda value: value and "canonical" in value.lower())
        canonical = normalize_whitespace(node.get("href", "") if node else "")
        if not canonical:
            for item in jsonld:
                if item.get("@type") == "WebPage":
                    canonical = normalize_whitespace(str(item.get("url") or ""))
                    break
        return make_absolute_url(canonical or fallback_url, fallback_url)

    def _extract_title(self, soup: BeautifulSoup, jsonld: list[dict[str, Any]]) -> str:
        for selector in (
            "h2.elementor-heading-title",
            "h1",
            "meta[property='og:title']",
        ):
            node = soup.select_one(selector)
            text = normalize_whitespace(
                node.get("content") if node and selector.startswith("meta[") else safe_text(node)
            )
            if text and "DHT26" in text:
                return self._clean_title(text)
        for item in jsonld:
            text = normalize_whitespace(str(item.get("name") or ""))
            if text and "DHT26" in text:
                return self._clean_title(text)
        return ""

    def _clean_title(self, title: str) -> str:
        cleaned = re.sub(r"\s*-\s*Γ\.Ε\.\s*ΔΗΜΗΤΡΙΟΥ\s*Α\.Ε\.Ε\.?\s*$", "", title)
        cleaned = cleaned.replace("&#8211;", "-").replace("–", "-")
        return normalize_whitespace(cleaned)

    def _extract_brand(self, soup: BeautifulSoup, title: str) -> str:
        haystack = normalize_for_match(f"{title} {soup.get_text(' ', strip=True)}")
        if "dai ichi" in haystack or "dai-ichi" in haystack:
            return "Dai-Ichi"
        return "Dai-Ichi" if "DHT26" in title else ""

    def _extract_mpn(self, soup: BeautifulSoup, title: str) -> str:
        text = normalize_whitespace(f"{title} {soup.get_text(' ', strip=True)}")
        internal = self._first_match(r"\bDHT26-12IVi\b", text)
        external = self._first_match(r"\bDHT26-12IVo\b", text)
        if internal and external:
            return f"{internal}/{external}"
        return internal or external

    def _first_match(self, pattern: str, text: str) -> str:
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(0) if match else ""

    def _build_display_name(
        self, brand: str, mpn: str, nominal_btu: str, fallback_title: str
    ) -> str:
        if brand and mpn:
            suffix = f" {nominal_btu}" if nominal_btu else ""
            return normalize_whitespace(f"{brand} {mpn} Κλιματιστικό Inverter{suffix}")
        return fallback_title

    def _extract_description(
        self, soup: BeautifulSoup, jsonld: list[dict[str, Any]]
    ) -> str:
        for item in jsonld:
            text = normalize_whitespace(str(item.get("description") or ""))
            if text:
                return text
        for selector, attr in [
            ("meta[name='description']", "content"),
            ("meta[property='og:description']", "content"),
        ]:
            node = soup.select_one(selector)
            text = normalize_whitespace(node.get(attr) if node else "")
            if text:
                return text
        for paragraph in soup.select(".elementor-widget-text-editor p"):
            text = safe_text(paragraph)
            if "Eco Design" in text or "κλιματιστικών Dai-Ichi" in text:
                return text
        return ""

    def _extract_spec_items(self, soup: BeautifulSoup) -> list[SpecItem]:
        items: list[SpecItem] = []
        items.extend(self._extract_model_items(soup))
        for inner in soup.select(".e-con-inner"):
            children = [
                node
                for node in inner.find_all("div", recursive=False)
                if isinstance(node, Tag) and "e-con-full" in (node.get("class") or [])
            ]
            if len(children) == 2:
                items.extend(self._extract_two_column_items(children))
            elif len(children) >= 3:
                items.extend(self._extract_grouped_items(children))
        items.extend(self._derive_ac_items(items))
        return self._dedupe_items(items)

    def _extract_model_items(self, soup: BeautifulSoup) -> list[SpecItem]:
        text = normalize_whitespace(soup.get_text(" ", strip=True))
        items: list[SpecItem] = []
        internal = self._first_match(r"\bDHT26-12IVi\b", text)
        external = self._first_match(r"\bDHT26-12IVo\b", text)
        if internal:
            items.append(SpecItem("Μοντέλο Εσωτερικής Μονάδας", internal))
        if external:
            items.append(SpecItem("Μοντέλο Εξωτερικής Μονάδας", external))
        return items

    def _extract_two_column_items(self, children: list[Tag]) -> list[SpecItem]:
        labels = [safe_text(node) for node in children[0].select("h4") if safe_text(node)]
        values = [safe_text(node) for node in children[1].select("h4") if safe_text(node)]
        if not labels or len(labels) != len(values):
            return []
        return [
            item
            for label, value in zip(labels, values, strict=False)
            for item in self._items_for_label_value(label, value)
        ]

    def _extract_grouped_items(self, children: list[Tag]) -> list[SpecItem]:
        labels = [safe_text(node) for node in children[0].select("h4") if safe_text(node)]
        sublabels = [safe_text(node) for node in children[1].select("h4") if safe_text(node)]
        values = [safe_text(node) for node in children[2].select("h4") if safe_text(node)]
        if len(labels) != 1 or not values:
            return []
        label = labels[0]
        if normalize_for_match(label) == normalize_for_match("ΦΙΛΤΡΑ"):
            return [SpecItem("Φίλτρα", normalize_whitespace(" / ".join(values)))]
        if len(sublabels) != len(values):
            return []
        out: list[SpecItem] = []
        for sublabel, value in zip(sublabels, values, strict=False):
            combined_label = normalize_whitespace(f"{label} {sublabel}")
            out.extend(self._items_for_label_value(combined_label, value))
            out.extend(self._derive_grouped_dimensions(label, sublabel, value))
        return out

    def _items_for_label_value(self, label: str, value: str) -> list[SpecItem]:
        normalized_value = self._normalize_value(value)
        if not label or not normalized_value:
            return []
        normalized_label = self._normalize_spec_label(label, normalized_value)
        return [SpecItem(normalized_label, normalized_value)]

    def _normalize_spec_label(self, label: str, value: str) -> str:
        key = normalize_for_match(label)
        value_key = normalize_for_match(value)
        has_btu = "btu" in value_key
        has_watt = bool(re.search(r"\b(?:w|kw)\b", value_key))
        if key == normalize_for_match("Απόδοση Ψύξης") and has_btu:
            return "Ψυκτική Απόδοση ( Btu/h )"
        if key == normalize_for_match("Απόδοση Ψύξης") and has_watt:
            return "Ψυκτική Απόδοση ( W )"
        if key == normalize_for_match("Απόδοση Θέρμανσης") and has_btu:
            return "Θερμική Απόδοση ( Btu/h )"
        if key == normalize_for_match("Απόδοση Θέρμανσης") and has_watt:
            return "Θερμική Απόδοση ( W )"
        if key == normalize_for_match("Εύρος Απόδοση Ψύξης") and has_btu:
            return "Εύρος Ψυκτικής Απόδοσης ( Btu/h )"
        if key == normalize_for_match("Εύρος Απόδοση Ψύξης") and has_watt:
            return "Εύρος Ψυκτικής Απόδοσης ( W )"
        if key == normalize_for_match("Εύρος Απόδοση Θέρμανσης") and has_btu:
            return "Εύρος Θερμικής Απόδοσης ( Btu/h )"
        if key == normalize_for_match("Εύρος Απόδοση Θέρμανσης") and has_watt:
            return "Εύρος Θερμικής Απόδοσης ( W )"
        aliases = {
            "pdesignc": "Φορτίου Σχεδιασμού Ψύξης ( kW/h )",
            "seer": "Βαθμός Εποχιακής Απόδοσης Ψύξης - SEER",
            "pdesignh μεσης ζωνης": "Φορτίου Σχεδιασμού Θέρμανσης Μεσαίας Ζώνης ( kW/h )",
            "scop μεσης ζωνης": "Βαθμός Εποχιακής Απόδοσης Θέρμανσης Μέσης Εποχής - SCOP",
            "ενεργειακη κλαση θερμανσης μεσης ζωνης": "Ενεργειακή Κλάση Θέρμανσης Μέσης Εποχής",
            "pdesignh θερμης ζωνης": "Φορτίου Σχεδιασμού Θέρμανσης Θερμής Ζώνης ( kW/h )",
            "scop θερμης ζωνης": "Βαθμός Εποχιακής Απόδοσης Θέρμανσης Θερμότερης Εποχής - SCOP",
            "ενεργειακη κλαση θερμανσης θερμης ζωνης": "Ενεργειακή Κλάση Θέρμανσης Θερμότερης Εποχής",
            "ενεργειακη κλαση ψυξης": "Ενεργειακή Κλάση Ψύξης",
            "ψυκτικο υγρο": "Ψυκτικό Υγρό",
            "wi fi": "Wifi",
            "wifi": "Wifi",
        }
        normalized = aliases.get(key, normalize_whitespace(label))
        return normalized

    def _normalize_value(self, value: str) -> str:
        normalized = normalize_whitespace(value).replace("Kw", "kW").replace("Kwh", "kWh")
        normalized = normalized.replace("℃", "°C")
        if normalize_for_match(normalized) == "ναι":
            return "Υποστηρίζεται"
        return normalized

    def _derive_ac_items(self, items: list[SpecItem]) -> list[SpecItem]:
        derived: list[SpecItem] = []
        cooling_btu = self._first_item_value(items, "Ψυκτική Απόδοση ( Btu/h )")
        nominal = self._normalize_nominal_btu(cooling_btu)
        if nominal:
            derived.append(SpecItem("Ονομαστική Απόδοση (Btu/h)", nominal))
        inverter = self._first_item_value(items, "ΛΕΙΤΟΥΡΓΙΑ INVERTER")
        if inverter:
            derived.append(SpecItem("Τεχνολογία Κλιματιστικού", "Inverter"))
        return derived

    def _derive_grouped_dimensions(
        self, label: str, sublabel: str, value: str
    ) -> list[SpecItem]:
        key = normalize_for_match(label)
        subkey = normalize_for_match(sublabel)
        dimensions = self._parse_dimensions(value)
        if "διαστασεις προιοντος" in key and dimensions:
            width, height, depth = dimensions
            if "εσωτερικη" in subkey:
                return [
                    SpecItem("Πλάτος Εσωτερικής Μονάδας ( mm )", width),
                    SpecItem("Ύψος Εσωτερικής Μονάδας ( mm )", height),
                    SpecItem("Βάθος Εσωτερικής Μονάδας ( mm )", depth),
                ]
            if "εξωτερικη" in subkey:
                return [
                    SpecItem("Πλάτος Εξωτερικής Μονάδας ( mm )", width),
                    SpecItem("Ύψος Εξωτερικής Μονάδας ( mm )", height),
                    SpecItem("Βάθος Εξωτερικής Μονάδας ( mm )", depth),
                ]
        if "καθαρο βαρος" in key:
            weight = self._first_number(value)
            if weight and "εσωτερικη" in subkey:
                return [SpecItem("Βάρος Εσωτερικής Μονάδας ( Kg )", weight)]
            if weight and "εξωτερικη" in subkey:
                return [SpecItem("Βάρος Εξωτερικής Μονάδας ( Kg )", weight)]
        return []

    def _parse_dimensions(self, value: str) -> tuple[str, str, str] | None:
        parts = re.findall(r"\d+(?:[.,]\d+)?", value)
        if len(parts) < 3:
            return None
        return parts[0], parts[1], parts[2]

    def _first_number(self, value: str) -> str:
        match = re.search(r"\d+(?:[.,]\d+)?", value)
        return match.group(0) if match else ""

    def _first_item_value(self, items: list[SpecItem], label: str) -> str:
        label_key = normalize_for_match(label)
        for item in items:
            if normalize_for_match(item.label) == label_key:
                return normalize_whitespace(item.value or "")
        return ""

    def _first_btu_capacity(self, items: list[SpecItem], title: str) -> str:
        value = self._first_item_value(items, "Ψυκτική Απόδοση ( Btu/h )")
        return self._normalize_nominal_btu(value) or self._normalize_nominal_btu(title)

    def _normalize_nominal_btu(self, value: str) -> str:
        match = re.search(r"\d[\d.,]*", value or "")
        if not match:
            return ""
        raw = re.sub(r"[^\d]", "", match.group(0))
        if not raw:
            return ""
        btu = int(raw)
        nearest = min(STANDARD_AC_BTU_BUCKETS, key=lambda bucket: abs(bucket - btu))
        return f"{nearest} BTU"

    def _extract_gallery_images(
        self, soup: BeautifulSoup, base_url: str, title: str
    ) -> list[GalleryImage]:
        candidates: list[str] = []
        for link in soup.select(".elementor-widget-gallery a[href]"):
            href = normalize_whitespace(link.get("href"))
            if href and re.search(r"\.(?:jpe?g|png|webp)(?:$|\?)", href, re.I):
                candidates.append(make_absolute_url(href, base_url))
        urls = dedupe_urls_preserve_order(
            [url for url in candidates if "DHT" in url.upper() or "DAIICHI" in url.upper()]
        )
        if not urls:
            urls = dedupe_urls_preserve_order(candidates)
        return [
            GalleryImage(url=image_url, alt=title, position=position)
            for position, image_url in enumerate(urls, start=1)
        ]

    def _extract_documents(
        self, soup: BeautifulSoup, base_url: str
    ) -> tuple[str, str, list[dict[str, Any]]]:
        energy_label_url = ""
        product_sheet_url = ""
        documents: list[dict[str, Any]] = []
        for link in soup.select("a[href$='.pdf'], a[href*='.pdf?']"):
            if not isinstance(link, Tag):
                continue
            href = make_absolute_url(normalize_whitespace(link.get("href")), base_url)
            if not href:
                continue
            container = link.find_parent("div", class_="e-parent") or link.find_parent("div")
            name = safe_text(container.select_one("h3")) if isinstance(container, Tag) else ""
            if not name:
                name = href.rstrip("/").split("/")[-1]
            document = {"name": name, "document_type": "pdf", "url": href}
            documents.append(document)
            key = normalize_for_match(f"{name} {href}")
            if "ενεργειακη ετικετα" in key or "energy label" in key or "energy-label" in key:
                energy_label_url = href
            elif "δελτιο προιοντος" in key or "product fiche" in key:
                product_sheet_url = href
        return energy_label_url, product_sheet_url, documents

    def _extract_presentation_source(
        self, soup: BeautifulSoup, base_url: str
    ) -> tuple[str, str]:
        html_parts: list[str] = []
        text_parts: list[str] = []
        seen: set[str] = set()
        for block in soup.select(".elementor-image-box-wrapper"):
            title = safe_text(block.select_one(".elementor-image-box-title"))
            text = safe_text(block.select_one(".elementor-image-box-description"))
            key = normalize_for_match(title)
            if not title or not text or key in seen:
                continue
            image_url = ""
            image = block.select_one("img")
            if image:
                image_url = make_absolute_url(
                    normalize_whitespace(image.get("src") or image.get("data-src") or ""),
                    base_url,
                )
            image_html = (
                f'<img src="{escape(image_url, quote=True)}" alt="{escape(title, quote=True)}" />'
                if image_url
                else ""
            )
            html_parts.append(
                "<section>"
                f"<h4>{escape(title)}</h4>"
                f"<p>{escape(text)}</p>"
                f"{image_html}"
                "</section>"
            )
            text_parts.append(f"{title}: {text}")
            seen.add(key)
        return "\n".join(html_parts), normalize_whitespace(" ".join(text_parts))

    def _source_text(self, spec_items: list[SpecItem]) -> str:
        return normalize_whitespace(
            " ".join(
                f"{item.label}: {item.value}"
                for item in spec_items
                if item.label and item.value
            )
        )

    def _dedupe_items(self, items: list[SpecItem]) -> list[SpecItem]:
        out: list[SpecItem] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            label = normalize_whitespace(item.label)
            value = normalize_whitespace(item.value or "")
            key = (normalize_for_match(label), normalize_for_match(value))
            if not label or not value or key in seen:
                continue
            seen.add(key)
            out.append(SpecItem(label, value))
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
        return FieldDiagnostic(
            confidence=0.94 if present else 0.0,
            selected_strategy=strategy,
            value_present=present,
            value_preview=self._preview_value(value),
            selector_trace=[
                SelectorTraceEntry(
                    strategy=strategy,
                    success=present,
                    chosen_preview=self._preview_value(value),
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
            return normalize_whitespace(value)[:240]
        if isinstance(value, list):
            return f"{len(value)} item(s)"
        return normalize_whitespace(str(value))[:240]
