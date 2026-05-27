from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from .models import GalleryImage, SelectorTraceEntry, SpecItem, SpecSection
from .normalize import (
    dedupe_urls_preserve_order,
    make_absolute_url,
    normalize_for_match,
    normalize_whitespace,
    nullify_dash_values,
    parse_euro_price,
    safe_text,
)
from .parser_product_electronet import ElectronetProductParser


class DreamelectricProductParser(ElectronetProductParser):
    def parse(self, html: str, url: str, fallback_used: bool = False):
        parsed = super().parse(html, url, fallback_used=fallback_used)
        if "inverter" in normalize_for_match(f"{url} {parsed.source.name}"):
            item = SpecItem("Τεχνολογία Κλιματιστικού", "Inverter")
            parsed.source.key_specs.append(item)
            if parsed.source.spec_sections:
                parsed.source.spec_sections[0].items.append(item)
        return parsed

    def _find_product_root(self, soup: BeautifulSoup) -> Tag | BeautifulSoup:
        for selector in (
            "#product-product",
            ".product-info",
            "#product",
            ".product-details",
            "main",
        ):
            node = soup.select_one(selector)
            if node:
                return node
        return soup.body or soup

    def _extract_product_code(
        self,
        soup: BeautifulSoup,
        product_root: Tag | BeautifulSoup,
        product_lines: list[str],
        jsonld: list[dict[str, Any]],
    ) -> tuple[str, str, float, list[SelectorTraceEntry]]:
        del jsonld
        trace: list[SelectorTraceEntry] = []
        for selector in (".product-info .product-right", ".product-info", "#product"):
            nodes = soup.select(selector)
            chosen = next((node for node in nodes if safe_text(node)), None)
            trace.append(self._trace_selector("dom", selector, nodes, chosen))
            if not chosen:
                continue
            match = re.search(r"Κωδικός\s*:?\s*(\d{4,})", safe_text(chosen), re.I)
            if match:
                return match.group(1), f"regex:{selector}", 0.92, trace
        for line in product_lines:
            match = re.search(r"Κωδικός\s*:?\s*(\d{4,})", line, re.I)
            if match:
                return match.group(1), "regex:lines", 0.75, trace
        return "", "missing", 0.0, trace

    def _extract_price(
        self,
        product_root: Tag | BeautifulSoup,
        soup: BeautifulSoup,
        product_lines: list[str],
        jsonld: list[dict[str, Any]],
    ) -> tuple[str, float | None, str, float, list[SelectorTraceEntry]]:
        del jsonld
        trace: list[SelectorTraceEntry] = []
        for selector, confidence in (
            (".product-price", 0.96),
            (".price", 0.9),
            ("[itemprop='price']", 0.88),
        ):
            nodes = product_root.select(selector) or soup.select(selector)
            chosen = next(
                (node for node in nodes if parse_euro_price(safe_text(node)) is not None),
                None,
            )
            trace.append(self._trace_selector("dom", selector, nodes, chosen))
            if chosen:
                text = safe_text(chosen)
                return text, parse_euro_price(text), f"dom:{selector}", confidence, trace

        for line in product_lines:
            price = parse_euro_price(line)
            if price is not None:
                return line, price, "lines:price", 0.55, trace
        return "", None, "missing", 0.0, trace

    def _extract_brand(
        self,
        product_root: Tag | BeautifulSoup,
        product_lines: list[str],
        jsonld: list[dict[str, Any]],
        name: str,
    ) -> tuple[str, str, float, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        for selector, confidence in (
            (".product-right a[href*='manufacturer']", 0.95),
            (".product-right a[href*='brand']", 0.92),
            (".brand-image img", 0.9),
        ):
            nodes = product_root.select(selector)
            chosen = next(
                (
                    node
                    for node in nodes
                    if safe_text(node) or normalize_whitespace(node.get("alt"))
                ),
                None,
            )
            trace.append(self._trace_selector("dom", selector, nodes, chosen))
            if chosen:
                return (
                    safe_text(chosen) or normalize_whitespace(chosen.get("alt")),
                    f"dom:{selector}",
                    confidence,
                    trace,
                )
        return super()._extract_brand(product_root, product_lines, jsonld, name)

    def _extract_hero_summary(
        self,
        product_root: Tag | BeautifulSoup,
        soup: BeautifulSoup,
        product_lines: list[str],
        jsonld: list[dict[str, Any]],
        name: str,
    ) -> tuple[str, str, float, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        for selector, attr, confidence in (
            ("meta[name='description']", "content", 0.82),
            ("meta[property='og:description']", "content", 0.8),
        ):
            nodes = soup.select(selector)
            chosen = next(
                (node for node in nodes if self._node_attr_or_text(node, attr)), None
            )
            trace.append(self._trace_selector("dom", selector, nodes, chosen))
            if chosen:
                return (
                    self._node_attr_or_text(chosen, attr),
                    f"dom:{selector}",
                    confidence,
                    trace,
                )
        if name:
            return name, "fallback:name", 0.45, trace
        return super()._extract_hero_summary(
            product_root, soup, product_lines, jsonld, name
        )

    def _extract_key_specs(
        self, product_root: Tag | BeautifulSoup, product_lines: list[str], name: str
    ) -> tuple[list[SpecItem], str, float, list[SelectorTraceEntry]]:
        del product_lines, name
        items, trace = self._extract_specs_table(product_root)
        if items:
            return items[:10], "dom:.block-attributes table", 0.9, trace
        return [], "missing", 0.0, trace

    def _extract_spec_sections(
        self, product_root: Tag | BeautifulSoup, product_lines: list[str]
    ) -> tuple[list[SpecSection], str, float, list[SelectorTraceEntry]]:
        del product_lines
        items, trace = self._extract_specs_table(product_root)
        if items:
            return (
                [SpecSection(section="Τεχνικά Χαρακτηριστικά", items=items)],
                "dom:.block-attributes table",
                0.94,
                trace,
            )
        return [], "missing", 0.0, trace

    def _extract_specs_table(
        self, product_root: Tag | BeautifulSoup
    ) -> tuple[list[SpecItem], list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        nodes = product_root.select(".block-attributes table, table")
        chosen = next((node for node in nodes if node.find("tr")), None)
        trace.append(
            self._trace_selector(
                "dom", ".block-attributes table, table", nodes, chosen
            )
        )
        if not chosen:
            return [], trace

        items: list[SpecItem] = []
        for row in chosen.select("tr"):
            cells = [safe_text(cell) for cell in row.find_all(["th", "td"])]
            if len(cells) < 2:
                continue
            label = normalize_whitespace(cells[0].rstrip(":"))
            value = nullify_dash_values(self._normalize_yes_no(cells[1]))
            if label and value:
                items.append(SpecItem(label=label, value=value))
        return self._dedupe_spec_items(self._expand_dreamelectric_specs(items)), trace

    def _normalize_yes_no(self, value: str) -> str:
        normalized = normalize_whitespace(value)
        return "Ναι" if normalized in {"√", "✓", "✔"} else normalized

    def _expand_dreamelectric_specs(self, items: list[SpecItem]) -> list[SpecItem]:
        expanded = list(items)
        lookup = {normalize_for_match(item.label): item.value or "" for item in items}

        nominal_btu = lookup.get(normalize_for_match("Ονομαστική Απόδοση (Btu/h)"))
        if nominal_btu:
            btu_value = self._format_btu(nominal_btu)
            expanded.extend(
                [
                    SpecItem("Ψυκτική Απόδοση ( Btu/h )", btu_value),
                    SpecItem("Θερμική Απόδοση ( Btu/h )", btu_value),
                ]
            )

        seer = lookup.get(normalize_for_match("SEER / Βαθμός Απόδοσης Ψύξης"))
        if seer:
            expanded.append(
                SpecItem("Βαθμός Εποχιακής Απόδοσης Ψύξης - SEER", seer)
            )

        scop = lookup.get(normalize_for_match("SCOP / Βαθμός Απόδοσης Θέρμανσης"))
        if scop:
            expanded.append(
                SpecItem(
                    "Βαθμός Εποχιακής Απόδοσης Θέρμανσης Μέσης Εποχής - SCOP",
                    scop,
                )
            )

        cooling_energy = lookup.get(normalize_for_match("Ψύξης Ενεργειακή Κλάση"))
        if cooling_energy:
            expanded.append(SpecItem("Ενεργειακή Κλάση Ψύξης", cooling_energy))

        heating_energy = lookup.get(normalize_for_match("Θέρμανσης Ενεργειακή Κλάση"))
        if heating_energy:
            expanded.append(
                SpecItem("Ενεργειακή Κλάση Θέρμανσης Μέσης Εποχής", heating_energy)
            )

        consumption = lookup.get(normalize_for_match("Κατανάλωση"))
        cooling_kwh, heating_kwh = self._split_cooling_heating_pair(consumption)
        if cooling_kwh:
            expanded.append(SpecItem("Ετήσια Κατανάλωση Ψύξης ( kWh / a )", cooling_kwh))
        if heating_kwh:
            expanded.append(
                SpecItem(
                    "Ετήσια Κατανάλωση Θέρμανσης Μέσης Εποχής ( kWh / a )",
                    heating_kwh,
                )
            )

        dimensions = lookup.get(normalize_for_match("Υ x Π x Β (Διαστάσεις)"))
        expanded.extend(self._expand_dimensions(dimensions))

        weight = lookup.get(normalize_for_match("Βάρος (Προϊόντος)"))
        internal_weight, external_weight = self._split_internal_external_pair(weight)
        if internal_weight:
            expanded.append(SpecItem("Βάρος Εσωτερικής Μονάδας ( Kg )", internal_weight))
        if external_weight:
            expanded.append(SpecItem("Βάρος Εξωτερικής Μονάδας ( Kg )", external_weight))

        functions = lookup.get(normalize_for_match("Επιπλέον Λειτουργίες"))
        if functions:
            expanded.append(SpecItem("Πρόσθετες Λειτουργίες Κλιματιστικού", functions))
            if "ion" in normalize_for_match(functions):
                expanded.append(SpecItem("Ιονιστής", "Ναι"))

        if "inverter" in normalize_for_match(" ".join([item.value or "" for item in items])):
            expanded.append(SpecItem("Τεχνολογία Κλιματιστικού", "Inverter"))
        return expanded

    def _format_btu(self, value: str) -> str:
        match = re.search(r"\d[\d.\s]*", value)
        if not match:
            return value
        number = re.sub(r"\D", "", match.group(0))
        return f"{number} BTU" if number else value

    def _split_cooling_heating_pair(self, value: str) -> tuple[str, str]:
        if not value:
            return "", ""
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)", value)
        if not match:
            return "", ""
        return match.group(1), match.group(2)

    def _split_internal_external_pair(self, value: str) -> tuple[str, str]:
        if not value:
            return "", ""
        match = re.search(r"Εσ/Εξ:\s*([^/+]+)(?:\+|/)([^ ]+)", value, re.I)
        if not match:
            return "", ""
        internal = match.group(1).strip()
        external = match.group(2).strip()
        if not re.search(r"\d", external):
            external = ""
        return internal, external

    def _expand_dimensions(self, value: str) -> list[SpecItem]:
        if not value:
            return []
        match = re.search(
            r"Εσ/Εξ:\s*([\d.,]+)\s*[*xX]\s*([\d.,]+)\s*[*xX]\s*([\d.,]+)"
            r"\s*/\s*([\d.,]+)\s*[*xX]\s*([\d.,]+)\s*[*xX]\s*([\d.,]+)",
            value,
            re.I,
        )
        if not match:
            return []
        internal_h, internal_w, internal_d, external_h, external_w, external_d = (
            match.groups()
        )
        return [
            SpecItem("Ύψος Εσωτερικής Μονάδας ( mm )", internal_h),
            SpecItem("Πλάτος Εσωτερικής Μονάδας ( mm )", internal_w),
            SpecItem("Βάθος Εσωτερικής Μονάδας ( mm )", internal_d),
            SpecItem("Ύψος Εξωτερικής Μονάδας ( mm )", external_h),
            SpecItem("Πλάτος Εξωτερικής Μονάδας ( mm )", external_w),
            SpecItem("Βάθος Εξωτερικής Μονάδας ( mm )", external_d),
        ]

    def _extract_gallery_images(
        self,
        product_root: Tag | BeautifulSoup,
        soup: BeautifulSoup,
        url: str,
        name: str,
        brand: str,
        product_code: str,
    ) -> tuple[list[GalleryImage], str, float, list[SelectorTraceEntry]]:
        del soup, product_code
        trace: list[SelectorTraceEntry] = []
        selectors = (
            ".main-image img[data-largeimg]",
            ".additional-images img[data-largeimg]",
            ".lightgallery-product-images img[data-largeimg]",
        )
        nodes: list[Tag] = []
        for selector in selectors:
            selected = product_root.select(selector)
            trace.append(
                self._trace_selector(
                    "dom",
                    selector,
                    selected,
                    selected[0] if selected else None,
                    note=f"{len(selected)} gallery candidates",
                )
            )
            nodes.extend(selected)

        image_urls = dedupe_urls_preserve_order(
            [
                make_absolute_url(
                    node.get("data-largeimg")
                    or node.get("data-image")
                    or node.get("data-src")
                    or node.get("src"),
                    url,
                )
                for node in nodes
                if node.get("data-largeimg")
                or node.get("data-image")
                or node.get("data-src")
                or node.get("src")
            ]
        )
        out: list[GalleryImage] = []
        for image_url in image_urls:
            node = next(
                (
                    item
                    for item in nodes
                    if make_absolute_url(
                        item.get("data-largeimg")
                        or item.get("data-image")
                        or item.get("data-src")
                        or item.get("src"),
                        url,
                    )
                    == image_url
                ),
                None,
            )
            alt = normalize_whitespace((node.get("alt") if node else "") or "")
            haystack = normalize_for_match(f"{image_url} {alt} {name} {brand}")
            if "pitsos" not in haystack and "psi12aw32" not in haystack:
                continue
            out.append(GalleryImage(url=image_url, alt=alt, position=len(out) + 1))
        if out:
            return out, "dom:data-largeimg", 0.96, trace
        return [], "missing", 0.0, trace

    def _extract_mpn(
        self,
        key_specs: list[SpecItem],
        spec_sections: list[SpecSection],
        name: str,
        brand: str,
        jsonld: list[dict[str, Any]],
    ) -> tuple[str, str, float, list[SelectorTraceEntry]]:
        del key_specs, spec_sections, jsonld
        title_after_brand = self._extract_model_token_after_brand(name, brand)
        if title_after_brand:
            return title_after_brand, "title_after_brand", 0.86, []
        title_anywhere = self._extract_model_token_from_title(name)
        if title_anywhere:
            return title_anywhere, "title_scan", 0.7, []
        return "", "missing", 0.0, []
