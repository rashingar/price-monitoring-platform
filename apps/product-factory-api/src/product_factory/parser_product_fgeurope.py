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
    parse_euro_price,
    safe_text,
)
from .skroutz_taxonomy import serialize_source_category
from .utils import utcnow_iso

WALL_AC_TAXONOMY = (
    "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
    "Κλιματιστικά",
    "Τοίχου",
)

FGEUROPE_AC_LABEL_ALIASES = {
    "ονομαστικη αποδοση btu h": "Ονομαστική Απόδοση (Btu/h)",
    "ψυκτικη αποδοση btu h": "Ψυκτική Απόδοση ( Btu/h )",
    "θερμικη αποδοση btu h": "Θερμική Απόδοση ( Btu/h )",
    "seer ψυξης": "Βαθμός Εποχιακής Απόδοσης Ψύξης - SEER",
    "scop θερμανσης μεσης εποχης": "Βαθμός Εποχιακής Απόδοσης Θέρμανσης Μέσης Εποχής - SCOP",
    "scop θερμανσης θερμοτερης εποχης": "Βαθμός Εποχιακής Απόδοσης Θέρμανσης Θερμότερης Εποχής - SCOP",
    "ετησια καταναλωση ψυξης kwh a": "Ετήσια Κατανάλωση Ψύξης ( kWh / a )",
    "ετησια καταναλωση θερμανσης μεσης εποχης kwh a": "Ετήσια Κατανάλωση Θέρμανσης Μέσης Εποχής ( kWh / a )",
    "ετησια καταναλωση θερμανσης θερμοτερης εποχης kwh a": "Ετήσια Κατανάλωση Θέρμανσης Θερμότερης Εποχής ( kWh / a )",
    "ηχητικη ισχυς εσωτερικης μοναδας db a": "Ηχητική Ισχύς Εσωτερικής Μονάδας dB(A) - Hi",
    "ηχητικη ισχυς εξωτερικης μοναδας db a": "Ηχητική Ισχύς Εξωτερικής Μονάδας dB(A) - Hi",
    "ηχητικη ισχυς εξωτερικης μοναδας σε db a": "Ηχητική Ισχύς Εξωτερικής Μονάδας dB(A) - Hi",
    "ψυκτικο υγρο": "Ψυκτικό Υγρό",
    "βαρος εσωτερικης μοναδας kg": "Βάρος Εσωτερικής Μονάδας ( Kg )",
    "βαρος εξωτερικης μοναδας kg": "Βάρος Εξωτερικής Μονάδας ( Kg )",
    "υψος εσωτερικης μοναδας mm": "Ύψος Εσωτερικής Μονάδας ( mm )",
    "πλατος εσωτερικης μοναδας mm": "Πλάτος Εσωτερικής Μονάδας ( mm )",
    "βαθος εσωτερικης μοναδας mm": "Βάθος Εσωτερικής Μονάδας ( mm )",
    "υψος εξωτερικης μοναδας mm": "Ύψος Εξωτερικής Μονάδας ( mm )",
    "πλατος εξωτερικης μοναδας mm": "Πλάτος Εξωτερικής Μονάδας ( mm )",
    "βαθος εξωτερικης μοναδας mm": "Βάθος Εξωτερικής Μονάδας ( mm )",
    "κωδικος εσωτερικης μοναδας": "Κωδικός Εσωτερικής Μονάδας",
    "κωδικος εξωτερικης μοναδας": "Κωδικός Εξωτερικής Μονάδας",
}

PRESENTATION_EXCLUDED_HEADINGS = {
    "αναλυτικη περιγραφη",
    "τεχνικα χαρακτηριστικα",
    "λειτουργιες",
    "συνοδευτικα αρχεια",
    "σχετικα προιοντα",
}

STANDARD_AC_BTU_BUCKETS = (9000, 12000, 14000, 15000, 18000, 21000, 22000, 24000)


class FGEuropeProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "html.parser")
        jsonld = self._extract_jsonld_items(soup)
        canonical_url = self._extract_canonical_url(soup, jsonld, url)
        title = self._extract_title(soup, jsonld)
        brand = self._extract_brand(soup, title)
        mpn = self._extract_mpn(soup, title)
        product_code = self._extract_product_code(soup, mpn)
        description = self._extract_description(soup, jsonld)
        breadcrumbs = clean_breadcrumbs(self._extract_breadcrumbs(soup, jsonld))
        spec_items = self._extract_spec_items(soup)
        gallery_images = self._extract_gallery_images(soup, canonical_url, title)
        energy_label_url, product_sheet_url, documents = self._extract_documents(
            soup, canonical_url
        )
        presentation_html, presentation_text = self._extract_presentation_source(
            soup, canonical_url
        )
        price_text, price_value = self._extract_price(soup)
        category_text = self._extract_category(title=title, breadcrumbs=breadcrumbs)
        taxonomy_source_category = self._taxonomy_source_category(
            title=title, url=canonical_url, category_text=category_text
        )

        source = SourceProductData(
            source_name="fgeurope",
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=breadcrumbs,
            category_tag_text=category_text,
            taxonomy_source_category=taxonomy_source_category,
            taxonomy_match_type=(
                "exact_category"
                if self._looks_like_wall_ac(title, canonical_url)
                else ""
            ),
            taxonomy_rule_id=(
                "fgeurope:wall_ac"
                if self._looks_like_wall_ac(title, canonical_url)
                else ""
            ),
            product_code=product_code,
            brand=brand,
            mpn=mpn,
            name=title,
            hero_summary=description,
            price_text=price_text,
            price_value=price_value,
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
            manufacturer_source_text=self._manufacturer_source_text(spec_items),
            presentation_source_text=presentation_text or description,
            presentation_source_html=presentation_html,
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
        )
        provenance = {
            "name": "dom:.single-product-link h3/meta:og:title" if title else "missing",
            "brand": "dom:subsite-logo/title" if brand else "missing",
            "mpn": "dom:summary_model_codes/spec_table/title" if mpn else "missing",
            "product_code": (
                "dom:summary_model_codes/spec_table" if product_code else "missing"
            ),
            "breadcrumbs": (
                "dom:breadcrumb/jsonld:BreadcrumbList" if breadcrumbs else "missing"
            ),
            "gallery_images": (
                "dom:.product-gallery a[data-fancybox='images']"
                if gallery_images
                else "missing"
            ),
            "spec_sections": (
                "dom:.product-attributes table" if spec_items else "missing"
            ),
            "hero_summary": (
                "meta:description/jsonld.description" if description else "missing"
            ),
            "energy_label_asset_url": (
                "dom:#ΣυνοδευτικάΑρχεία files-slider" if energy_label_url else "missing"
            ),
            "presentation_blocks": "dom:product_feature_cards",
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
        if not energy_label_url and self._looks_like_wall_ac(title, canonical_url):
            warnings.append("energy_label_asset_missing")
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

    def _extract_canonical_url(
        self, soup: BeautifulSoup, jsonld: list[dict[str, Any]], fallback_url: str
    ) -> str:
        node = soup.find(
            "link", rel=lambda value: value and "canonical" in value.lower()
        )
        canonical = normalize_whitespace(node.get("href", "") if node else "")
        if not canonical:
            for item in jsonld:
                if item.get("@type") == "WebPage":
                    canonical = normalize_whitespace(str(item.get("url") or ""))
                    break
        return make_absolute_url(canonical or fallback_url, fallback_url)

    def _extract_title(self, soup: BeautifulSoup, jsonld: list[dict[str, Any]]) -> str:
        for selector in (
            ".single-product-link h3",
            ".product-list-item h3",
            "h1.product_title",
        ):
            title = safe_text(soup.select_one(selector))
            if title:
                return self._clean_title(title)
        meta = soup.select_one("meta[property='og:title']")
        title = normalize_whitespace(meta.get("content") if meta else "")
        if not title:
            for item in jsonld:
                if item.get("@type") == "WebPage":
                    title = normalize_whitespace(str(item.get("name") or ""))
                    break
        return self._clean_title(title)

    def _clean_title(self, title: str) -> str:
        return normalize_whitespace(re.sub(r"\s*\|\s*FG Europe\s*$", "", title))

    def _extract_brand(self, soup: BeautifulSoup, title: str) -> str:
        logo = soup.select_one(".subsite-logo img[alt], .subsite-logo[title]")
        brand = normalize_whitespace(
            logo.get("alt")
            if logo and logo.has_attr("alt")
            else logo.get("title") if logo else ""
        )
        if brand:
            return brand
        first = normalize_whitespace(title.split(" ", 1)[0]) if title else ""
        return first if first.lower() != "midea" else "Midea"

    def _extract_mpn(self, soup: BeautifulSoup, title: str) -> str:
        codes = self._extract_summary_codes(soup)
        internal = codes.get("Κωδικός Εσωτερικής Μονάδας", "")
        external = codes.get("Κωδικός Εξωτερικής Μονάδας", "")
        if internal and external:
            return f"{internal}/{external}"
        if internal:
            return internal
        for item in self._extract_spec_items(soup):
            if normalize_for_match(item.label) == normalize_for_match(
                "Κωδικός Εσωτερικής Μονάδας"
            ):
                return normalize_whitespace(item.value or "")
        match = re.search(r"\b[A-Z]{2,}-\d+[A-Z0-9-]*\b", title)
        return match.group(0) if match else ""

    def _extract_product_code(self, soup: BeautifulSoup, mpn: str) -> str:
        codes = self._extract_summary_codes(soup)
        return codes.get("Κωδικός Εσωτερικής Μονάδας", "") or mpn

    def _extract_summary_codes(self, soup: BeautifulSoup) -> dict[str, str]:
        codes: dict[str, str] = {}
        for node in soup.select(".line-height-2"):
            label_node = node.find("strong")
            if not label_node:
                continue
            label = normalize_whitespace(safe_text(label_node).rstrip(":"))
            value_node = node.find("span")
            value = safe_text(value_node)
            if label and value and "Κωδικός" in label:
                codes[label] = value
        return codes

    def _extract_description(
        self, soup: BeautifulSoup, jsonld: list[dict[str, Any]]
    ) -> str:
        for item in jsonld:
            if item.get("@type") == "WebPage":
                description = normalize_whitespace(str(item.get("description") or ""))
                if description:
                    return description
        for selector, attr in [
            ("meta[name='description']", "content"),
            ("meta[property='og:description']", "content"),
            (".woocommerce-product-details__short-description", None),
        ]:
            node = soup.select_one(selector)
            text = normalize_whitespace(
                node.get(attr) if attr and node else node.get_text(" ") if node else ""
            )
            if text:
                return text
        return ""

    def _extract_breadcrumbs(
        self, soup: BeautifulSoup, jsonld: list[dict[str, Any]]
    ) -> list[str]:
        values = [
            safe_text(node)
            for node in soup.select(".breadcrumb-item a, .breadcrumb-item span")
            if safe_text(node)
        ]
        if values:
            return [
                value for value in values if normalize_for_match(value) not in {"home"}
            ]
        for item in jsonld:
            if item.get("@type") != "BreadcrumbList":
                continue
            elements = item.get("itemListElement")
            if not isinstance(elements, list):
                continue
            out = []
            for element in elements:
                if isinstance(element, dict):
                    name = normalize_whitespace(str(element.get("name") or ""))
                    if name and normalize_for_match(name) != "home":
                        out.append(name)
            if out:
                return out
        return []

    def _extract_spec_items(self, soup: BeautifulSoup) -> list[SpecItem]:
        items: list[SpecItem] = []
        for row in soup.select(".product-attributes table tr"):
            label = safe_text(row.find("th"))
            value = safe_text(row.find("td"))
            if not label or not value:
                continue
            normalized_label = self._normalize_spec_label(label)
            items.append(
                SpecItem(
                    label=normalized_label,
                    value=self._normalize_spec_value_for_label(normalized_label, value),
                )
            )
            items.extend(self._derive_spec_items(label, value))
        if self._supports_wifi(soup):
            items.append(SpecItem(label="Wifi", value="Υποστηρίζεται"))
        features = self._extract_feature_names(soup)
        if features:
            items.append(
                SpecItem(
                    label="Πρόσθετες Λειτουργίες Κλιματιστικού",
                    value=", ".join(features),
                )
            )
        return self._dedupe_items(items)

    def _normalize_spec_label(self, label: str) -> str:
        key = normalize_for_match(label)
        if key.startswith("εποχιακος βαθμος ενεργειακης αποδοσης seer"):
            return "Βαθμός Εποχιακής Απόδοσης Ψύξης - SEER"
        if key.startswith("εποχιακος συντελεστης αποδοσης scop θερμανση μεση"):
            return "Βαθμός Εποχιακής Απόδοσης Θέρμανσης Μέσης Εποχής - SCOP"
        if key.startswith("εποχιακος συντελεστης αποδοσης scop θερμανση θερμη"):
            return "Βαθμός Εποχιακής Απόδοσης Θέρμανσης Θερμότερης Εποχής - SCOP"
        if key == "ενεργειακη κλαση θερμανσης θερμη ζωνη":
            return "Ενεργειακή Κλάση Θέρμανσης Θερμότερης Εποχής"
        if key == "ενεργειακη κλαση θερμανσης μεσης ζωνης":
            return "Ενεργειακή Κλάση Θέρμανσης Μέσης Εποχής"
        return FGEUROPE_AC_LABEL_ALIASES.get(key, normalize_whitespace(label))

    def _normalize_spec_value(self, value: str) -> str:
        normalized = normalize_whitespace(value)
        normalized = re.sub(r"\s*,\s*$", "", normalized)
        return normalized

    def _normalize_spec_value_for_label(self, label: str, value: str) -> str:
        normalized = self._normalize_spec_value(value)
        if normalize_for_match(label) == normalize_for_match(
            "Ονομαστική Απόδοση (Btu/h)"
        ):
            return self._normalize_nominal_btu(normalized) or normalized
        return normalized

    def _derive_spec_items(self, label: str, value: str) -> list[SpecItem]:
        key = normalize_for_match(label)
        normalized_value = self._normalize_spec_value(value)
        derived: list[SpecItem] = []

        dimensions = self._parse_dimensions(normalized_value)
        if dimensions and "διαστασεις εσωτερικης μοναδας" in key:
            width, depth, height = dimensions
            derived.extend(
                [
                    SpecItem(label="Πλάτος Εσωτερικής Μονάδας ( mm )", value=width),
                    SpecItem(label="Βάθος Εσωτερικής Μονάδας ( mm )", value=depth),
                    SpecItem(label="Ύψος Εσωτερικής Μονάδας ( mm )", value=height),
                ]
            )
        elif dimensions and "διαστασεις εξωτερικης μοναδας" in key:
            width, depth, height = dimensions
            derived.extend(
                [
                    SpecItem(label="Πλάτος Εξωτερικής Μονάδας ( mm )", value=width),
                    SpecItem(label="Βάθος Εξωτερικής Μονάδας ( mm )", value=depth),
                    SpecItem(label="Ύψος Εξωτερικής Μονάδας ( mm )", value=height),
                ]
            )

        net_weight = self._parse_net_weight(normalized_value)
        if net_weight and "βαρος εσωτερικης μοναδας" in key:
            derived.append(
                SpecItem(label="Βάρος Εσωτερικής Μονάδας ( Kg )", value=net_weight)
            )
        elif net_weight and "βαρος εξωτερικης μοναδας" in key:
            derived.append(
                SpecItem(label="Βάρος Εξωτερικής Μονάδας ( Kg )", value=net_weight)
            )
        return derived

    def _parse_dimensions(self, value: str) -> tuple[str, str, str] | None:
        normalized = value.replace("×", "x").replace("Χ", "x").replace("χ", "x")
        parts = re.findall(r"\d+(?:[.,]\d+)?", normalized)
        if len(parts) < 3:
            return None
        return parts[0], parts[1], parts[2]

    def _parse_net_weight(self, value: str) -> str:
        match = re.search(r"\d+(?:[.,]\d+)?", value)
        return match.group(0) if match else ""

    def _normalize_nominal_btu(self, value: str) -> str:
        match = re.search(r"\d[\d.,]*", value)
        if not match:
            return ""
        raw = re.sub(r"[^\d]", "", match.group(0))
        if not raw:
            return ""
        btu = int(raw)
        nearest = min(STANDARD_AC_BTU_BUCKETS, key=lambda bucket: abs(bucket - btu))
        return f"{nearest} BTU"

    def _supports_wifi(self, soup: BeautifulSoup) -> bool:
        text = normalize_for_match(soup.get_text(" "))
        return any(token in text for token in ("smarthome app", "wi fi", "wifi"))

    def _extract_feature_names(self, soup: BeautifulSoup) -> list[str]:
        names: list[str] = []
        for node in soup.select(".functions h6, .product-functions h6, h6"):
            name = safe_text(node)
            key = normalize_for_match(name)
            if not name or key in {"product fiche"}:
                continue
            if any(
                skip in key
                for skip in (
                    "εγχειριδιο",
                    "ενεργειακη ετικετα",
                    "product file",
                    "product fiche",
                )
            ):
                continue
            if any(
                token in key
                for token in (
                    "prime guard",
                    "ecomaster",
                    "smarthome",
                    "i sleep",
                    "follow me",
                    "swing",
                    "super ionizer",
                )
            ):
                names.append(name)
        for title in self._extract_presentation_titles(soup):
            if normalize_for_match(title) not in {
                normalize_for_match(name) for name in names
            }:
                names.append(title)
        return dedupe_urls_preserve_order(names)

    def _extract_presentation_titles(self, soup: BeautifulSoup) -> list[str]:
        return [
            title
            for title, _text, _image in self._presentation_blocks_from_dom(soup, "")
        ]

    def _extract_presentation_source(
        self, soup: BeautifulSoup, base_url: str
    ) -> tuple[str, str]:
        blocks = self._presentation_blocks_from_dom(soup, base_url)
        if not blocks:
            fallback = soup.select_one(
                "#ΑναλυτικήΠεριγραφή, .woocommerce-product-details__short-description"
            )
            html = str(fallback or "")
            return html, safe_text(fallback) if fallback else ""

        html_parts: list[str] = []
        text_parts: list[str] = []
        for title, text, image_url in blocks:
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
        return "\n".join(html_parts), normalize_whitespace(" ".join(text_parts))

    def _presentation_blocks_from_dom(
        self, soup: BeautifulSoup, base_url: str
    ) -> list[tuple[str, str, str]]:
        blocks: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for heading in soup.find_all("h4"):
            title = safe_text(heading)
            key = normalize_for_match(title)
            if not title or key in PRESENTATION_EXCLUDED_HEADINGS:
                continue
            container = (
                heading.find_parent("div", class_="row")
                or heading.find_parent("section")
                or heading.find_parent("div")
            )
            if not isinstance(container, Tag):
                continue
            paragraph_texts = [
                safe_text(node) for node in container.find_all("p") if safe_text(node)
            ]
            text = normalize_whitespace(" ".join(paragraph_texts))
            if not text or key in seen:
                continue
            image_url = ""
            image = container.find("img")
            if isinstance(image, Tag):
                image_url = normalize_whitespace(
                    image.get("src")
                    or image.get("data-src")
                    or image.get("data-lazy-src")
                    or ""
                )
                if image_url:
                    image_url = make_absolute_url(image_url, base_url)
            seen.add(key)
            blocks.append((title, text, image_url))
        return blocks

    def _extract_gallery_images(
        self, soup: BeautifulSoup, base_url: str, title: str
    ) -> list[GalleryImage]:
        urls = dedupe_urls_preserve_order(
            [
                make_absolute_url(node.get("href"), base_url)
                for node in soup.select(
                    ".product-gallery a[data-fancybox='images'][href]"
                )
                if normalize_whitespace(node.get("href"))
            ]
        )
        if not urls:
            urls = dedupe_urls_preserve_order(
                [
                    make_absolute_url(node.get("content"), base_url)
                    for node in soup.select("meta[property='og:image'][content]")
                    if normalize_whitespace(node.get("content"))
                ]
            )
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
        for link in soup.select(".files-wrapper a[href], .file-slider a[href]"):
            if not isinstance(link, Tag):
                continue
            name = safe_text(link.select_one("h6")) or safe_text(link)
            href = make_absolute_url(normalize_whitespace(link.get("href")), base_url)
            if not href or not name:
                continue
            normalized_name = normalize_for_match(name)
            document_type = (
                "image"
                if re.search(r"\.(?:jpe?g|png|webp)(?:$|\?)", href, re.I)
                else "pdf"
            )
            documents.append(
                {"name": name, "document_type": document_type, "url": href}
            )
            if "ενεργειακη ετικετα" in normalized_name:
                energy_label_url = href
            elif "product fiche" in normalized_name or "δελτιο" in normalized_name:
                product_sheet_url = href
        return energy_label_url, product_sheet_url, documents

    def _extract_price(self, soup: BeautifulSoup) -> tuple[str, float | None]:
        for selector in (
            ".price",
            ".product-price",
            "meta[property='product:price:amount']",
        ):
            node = soup.select_one(selector)
            if not node:
                continue
            text = normalize_whitespace(
                node.get("content")
                if selector.startswith("meta[")
                else node.get_text(" ")
            )
            value = parse_euro_price(text)
            if value is not None:
                return text, value
        return "", None

    def _extract_category(self, *, title: str, breadcrumbs: list[str]) -> str:
        if self._looks_like_wall_ac(title, ""):
            return WALL_AC_TAXONOMY[2]
        return (
            breadcrumbs[-2]
            if len(breadcrumbs) >= 2
            else breadcrumbs[-1] if breadcrumbs else ""
        )

    def _taxonomy_source_category(
        self, *, title: str, url: str, category_text: str
    ) -> str:
        if self._looks_like_wall_ac(title, url):
            parent, leaf, sub = WALL_AC_TAXONOMY
            return serialize_source_category(parent, leaf, [sub])
        return category_text

    def _looks_like_wall_ac(self, title: str, url: str) -> bool:
        haystack = normalize_for_match(f"{title} {url}")
        return "κλιματιστικο" in haystack and (
            "τοιχου" in haystack or "toichou" in haystack or "wall" in haystack
        )

    def _manufacturer_source_text(self, spec_items: list[SpecItem]) -> str:
        return normalize_whitespace(
            " ".join(
                f"{item.label}: {item.value}"
                for item in spec_items
                if item.label and item.value
            )
        )

    def _dedupe_items(self, items: list[SpecItem]) -> list[SpecItem]:
        out: list[SpecItem] = []
        seen: set[str] = set()
        for item in items:
            key = normalize_for_match(item.label)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item)
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
            return normalize_whitespace(value)[:160]
        if isinstance(value, list):
            return f"{len(value)} items" if value else ""
        return normalize_whitespace(str(value))[:160]
