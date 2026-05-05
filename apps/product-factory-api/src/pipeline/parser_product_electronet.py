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
    nullify_dash_values,
    parse_euro_price,
    safe_text,
    split_visible_lines,
)
from .utils import utcnow_iso

STOP_HEADINGS = {
    normalize_for_match("Σχετικά προϊόντα"),
    normalize_for_match("Περισσότερες φωτογραφίες"),
    normalize_for_match("Το ήξερες;"),
}
CRITICAL_FIELDS = ["name", "product_code", "price", "breadcrumbs", "spec_sections", "gallery_images", "hero_summary"]
PRICE_RE = re.compile(r"\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?\s*€")
INSTALLMENTS_RE = re.compile(r"\d+\s+άτοκες\s+δόσεις", re.IGNORECASE)
CODE_RE = re.compile(r"ΚΩΔΙΚΟΣ\s+ΠΡΟΪΟΝΤΟΣ\s*:?\s*([0-9]{6})", re.IGNORECASE)
PURE_NUMERIC_TOKEN_RE = re.compile(r"^\d+(?:[.,]\d+)?$")
STRIP_PUNCT_RE = re.compile(r"^[^\w]+|[^\w+./-]+$")
EPREL_HOST = "https://eprel.ec.europa.eu"


class ElectronetProductParser:
    def __init__(self, known_section_titles: set[str] | None = None) -> None:
        self.known_section_titles = known_section_titles or set()

    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        product_root = self._find_product_root(soup)
        product_lines = split_visible_lines(product_root.get_text("\n")) if product_root else []
        full_lines = split_visible_lines(soup.get_text("\n"))
        jsonld = self._parse_jsonld(soup)
        provenance: dict[str, str] = {}
        field_diagnostics: dict[str, FieldDiagnostic] = {}
        warnings: list[str] = []

        canonical_url = self._extract_canonical_url(soup, url)

        breadcrumbs, breadcrumbs_source, breadcrumbs_confidence, breadcrumbs_trace = self._extract_breadcrumbs(soup, full_lines)
        provenance["breadcrumbs"] = breadcrumbs_source
        field_diagnostics["breadcrumbs"] = self._make_diagnostic(
            breadcrumbs,
            breadcrumbs_source,
            breadcrumbs_confidence,
            breadcrumbs_trace,
        )

        product_code, product_code_source, product_code_confidence, product_code_trace = self._extract_product_code(
            soup,
            product_root,
            product_lines,
            jsonld,
        )
        provenance["product_code"] = product_code_source
        field_diagnostics["product_code"] = self._make_diagnostic(
            product_code,
            product_code_source,
            product_code_confidence,
            product_code_trace,
        )

        name, name_source, name_confidence, name_trace = self._extract_name(product_root, soup, jsonld)
        provenance["name"] = name_source
        field_diagnostics["name"] = self._make_diagnostic(name, name_source, name_confidence, name_trace)

        brand, brand_source, brand_confidence, brand_trace = self._extract_brand(product_root, product_lines, jsonld, name)
        provenance["brand"] = brand_source
        field_diagnostics["brand"] = self._make_diagnostic(brand, brand_source, brand_confidence, brand_trace)

        price_text, price_value, price_source, price_confidence, price_trace = self._extract_price(
            product_root,
            soup,
            product_lines,
            jsonld,
        )
        provenance["price"] = price_source
        field_diagnostics["price"] = self._make_diagnostic(price_text or price_value, price_source, price_confidence, price_trace)

        installments_text = self._extract_installments_text(product_root, product_lines)
        delivery_text, pickup_text = self._extract_delivery_and_pickup(product_root, product_lines)

        hero_summary, hero_source, hero_confidence, hero_trace = self._extract_hero_summary(product_root, soup, product_lines, jsonld, name)
        provenance["hero_summary"] = hero_source
        field_diagnostics["hero_summary"] = self._make_diagnostic(hero_summary, hero_source, hero_confidence, hero_trace)

        presentation_html, presentation_text, presentation_count, presentation_source, presentation_confidence, presentation_trace = (
            self._extract_presentation_source(product_root, soup)
        )
        provenance["presentation_blocks"] = presentation_source
        field_diagnostics["presentation_blocks"] = self._make_diagnostic(
            presentation_count,
            presentation_source,
            presentation_confidence,
            presentation_trace,
        )

        key_specs, key_specs_source, key_specs_confidence, key_specs_trace = self._extract_key_specs(product_root, product_lines, name)
        provenance["key_specs"] = key_specs_source
        field_diagnostics["key_specs"] = self._make_diagnostic(
            key_specs,
            key_specs_source,
            key_specs_confidence,
            key_specs_trace,
        )

        spec_sections, spec_sections_source, spec_sections_confidence, spec_sections_trace = self._extract_spec_sections(
            product_root,
            product_lines,
        )
        provenance["spec_sections"] = spec_sections_source
        field_diagnostics["spec_sections"] = self._make_diagnostic(
            spec_sections,
            spec_sections_source,
            spec_sections_confidence,
            spec_sections_trace,
        )

        mpn, mpn_source, mpn_confidence, mpn_trace = self._extract_mpn(key_specs, spec_sections, name, brand, jsonld)
        provenance["mpn"] = mpn_source
        field_diagnostics["mpn"] = self._make_diagnostic(mpn, mpn_source, mpn_confidence, mpn_trace)

        gallery_images, gallery_source, gallery_confidence, gallery_trace = self._extract_gallery_images(
            product_root,
            soup,
            url,
            name,
            brand,
            product_code,
        )
        provenance["gallery_images"] = gallery_source
        field_diagnostics["gallery_images"] = self._make_diagnostic(
            gallery_images,
            gallery_source,
            gallery_confidence,
            gallery_trace,
        )
        if not gallery_images:
            warnings.append("gallery_images_missing")

        energy_label_asset_url, product_sheet_asset_url = self._extract_assets(product_root or soup, soup, url)

        source = SourceProductData(
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=breadcrumbs,
            product_code=product_code,
            brand=brand,
            name=name,
            hero_summary=hero_summary,
            price_text=price_text,
            price_value=price_value,
            installments_text=installments_text,
            delivery_text=delivery_text,
            pickup_text=pickup_text,
            gallery_images=gallery_images,
            energy_label_asset_url=energy_label_asset_url,
            product_sheet_asset_url=product_sheet_asset_url,
            key_specs=key_specs,
            spec_sections=spec_sections,
            presentation_source_html=presentation_html,
            presentation_source_text=presentation_text,
            raw_html_path="",
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
            mpn=mpn,
        )
        missing_fields = self._collect_missing_fields(source)
        critical_missing = self._collect_critical_missing(source)
        return ParsedProduct(
            source=source,
            provenance=provenance,
            field_diagnostics=field_diagnostics,
            missing_fields=missing_fields,
            warnings=warnings,
            critical_missing=critical_missing,
        )

    def _parse_jsonld(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text(" ", strip=True)
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            self._append_jsonld_payload(payload, parsed)
        return payload

    def _append_jsonld_payload(self, out: list[dict[str, Any]], parsed: Any) -> None:
        if isinstance(parsed, list):
            for item in parsed:
                self._append_jsonld_payload(out, item)
            return
        if not isinstance(parsed, dict):
            return
        graph = parsed.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                self._append_jsonld_payload(out, item)
        out.append(parsed)

    def _product_jsonld_items(self, jsonld: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        for item in jsonld:
            item_type = normalize_for_match(self._jsonld_type_text(item.get("@type")))
            if "product" in item_type:
                items.append(item)
        return items or jsonld

    def _jsonld_type_text(self, value: Any) -> str:
        if isinstance(value, list):
            return " ".join(str(item) for item in value)
        return str(value or "")

    def _find_product_root(self, soup: BeautifulSoup) -> Tag | BeautifulSoup:
        for selector in ["article.product-page", "article[data-sku]", ".product-page", "main article", "main"]:
            node = soup.select_one(selector)
            if node:
                return node
        return soup.body or soup

    def _extract_canonical_url(self, soup: BeautifulSoup, url: str) -> str:
        link = soup.find("link", rel=lambda value: value and "canonical" in value.lower())
        if link and link.get("href"):
            return make_absolute_url(link["href"], url)
        return url

    def _extract_breadcrumbs(
        self,
        soup: BeautifulSoup,
        text_lines: list[str],
    ) -> tuple[list[str], str, float, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        for selector, confidence in [
            ("#block-mytheme-breadcrumbs .breadcrumb__link", 0.99),
            ("nav.breadcrumb a", 0.96),
            (".breadcrumb a", 0.94),
            (".breadcrumb li", 0.9),
        ]:
            nodes = soup.select(selector)
            values = [safe_text(node) for node in nodes if safe_text(node)]
            cleaned = clean_breadcrumbs(values)
            trace.append(self._trace_selector("dom", selector, nodes, next((node for node in nodes if safe_text(node)), None), note=f"{len(cleaned)} breadcrumbs"))
            if cleaned:
                return cleaned, f"dom:{selector}", confidence, trace

        if "Breadcrumb" in text_lines:
            start = text_lines.index("Breadcrumb") + 1
            extracted: list[str] = []
            for line in text_lines[start : start + 10]:
                match = re.match(r"\d+\.\s*(.+)", line)
                if match:
                    extracted.append(match.group(1))
            cleaned = clean_breadcrumbs(extracted)
            if cleaned:
                return cleaned, "lines:breadcrumb", 0.45, trace
        return [], "missing", 0.0, trace

    def _extract_product_code(
        self,
        soup: BeautifulSoup,
        product_root: Tag | BeautifulSoup,
        product_lines: list[str],
        jsonld: list[dict[str, Any]],
    ) -> tuple[str, str, float, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []

        nodes = soup.select("#cscp-sku")
        text = next((safe_text(node) for node in nodes if re.fullmatch(r"\d{6}", safe_text(node))), "")
        trace.append(self._trace_selector("dom", "#cscp-sku", nodes, next((node for node in nodes if re.fullmatch(r"\d{6}", safe_text(node))), None)))
        if text:
            return text, "dom:#cscp-sku", 0.99, trace

        for selector, confidence in [("article.product-page[data-sku]", 0.98), ("[data-sku]", 0.95)]:
            nodes = soup.select(selector)
            chosen = None
            value = ""
            for node in nodes:
                candidate = normalize_whitespace(node.get("data-sku"))
                if re.fullmatch(r"\d{6}", candidate):
                    chosen = node
                    value = candidate
                    break
            trace.append(self._trace_selector("dom_attr", selector, nodes, chosen, note=value))
            if value:
                return value, f"dom_attr:{selector}", confidence, trace

        page_text = product_root.get_text(" ", strip=True)
        match = CODE_RE.search(page_text)
        if match:
            return match.group(1), "regex:product_scope", 0.75, trace
        for line in product_lines:
            match = CODE_RE.search(line)
            if match:
                return match.group(1), "regex:lines", 0.6, trace
        for item in self._product_jsonld_items(jsonld):
            sku = item.get("sku") or item.get("productID")
            candidate = normalize_whitespace(str(sku)) if sku is not None else ""
            if re.fullmatch(r"\d{6}", candidate):
                return candidate, "jsonld:sku", 0.92, trace
        return "", "missing", 0.0, trace

    def _extract_name(
        self,
        product_root: Tag | BeautifulSoup,
        soup: BeautifulSoup,
        jsonld: list[dict[str, Any]],
    ) -> tuple[str, str, float, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        for selector, confidence in [("h1.product-title", 0.99), ("h1", 0.94)]:
            nodes = product_root.select(selector)
            chosen = next((node for node in nodes if safe_text(node)), None)
            trace.append(self._trace_selector("dom", selector, nodes, chosen))
            if chosen:
                return safe_text(chosen), f"dom:{selector}", confidence, trace

        for selector, attr, confidence in [
            ("meta[property='og:title']", "content", 0.88),
            ("meta[name='twitter:title']", "content", 0.86),
            ("title", None, 0.8),
        ]:
            nodes = soup.select(selector)
            chosen = next((node for node in nodes if self._node_attr_or_text(node, attr)), None)
            trace.append(self._trace_selector("dom", selector, nodes, chosen))
            if chosen:
                text = self._node_attr_or_text(chosen, attr)
                if selector == "title":
                    text = text.split(" - ")[0].strip()
                return normalize_whitespace(text), f"dom:{selector}", confidence, trace

        for item in self._product_jsonld_items(jsonld):
            name = item.get("name")
            if name:
                return normalize_whitespace(str(name)), "jsonld:name", 0.9, trace
        return "", "missing", 0.0, trace

    def _extract_brand(
        self,
        product_root: Tag | BeautifulSoup,
        product_lines: list[str],
        jsonld: list[dict[str, Any]],
        name: str,
    ) -> tuple[str, str, float, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []

        nodes = product_root.select("#product-brand-logo a")
        chosen = next((node for node in nodes if safe_text(node)), None)
        trace.append(self._trace_selector("dom", "#product-brand-logo a", nodes, chosen))
        if chosen:
            return safe_text(chosen), "dom:#product-brand-logo a", 0.99, trace

        nodes = product_root.select("#product-brand-logo img")
        chosen = next((node for node in nodes if normalize_whitespace(node.get("alt"))), None)
        trace.append(self._trace_selector("dom", "#product-brand-logo img", nodes, chosen))
        if chosen:
            return normalize_whitespace(chosen.get("alt")), "dom:#product-brand-logo img", 0.97, trace

        for item in self._product_jsonld_items(jsonld):
            brand = item.get("brand") or item.get("manufacturer")
            if isinstance(brand, dict):
                brand = brand.get("name")
            candidate = normalize_whitespace(str(brand)) if brand else ""
            if candidate:
                return candidate, "jsonld:brand", 0.95, trace

        compare_idx = next((idx for idx, line in enumerate(product_lines) if normalize_for_match(line) == normalize_for_match("Σύγκριση")), -1)
        if compare_idx >= 0 and compare_idx + 1 < len(product_lines):
            candidate = normalize_whitespace(product_lines[compare_idx + 1])
            if candidate and len(candidate.split()) <= 3:
                return candidate, "lines:compare_label", 0.55, trace

        candidate = self._infer_brand_from_name(name)
        if candidate:
            return candidate, "heuristic:title_token", 0.42, trace
        return "", "missing", 0.0, trace

    def _extract_price(
        self,
        product_root: Tag | BeautifulSoup,
        soup: BeautifulSoup,
        product_lines: list[str],
        jsonld: list[dict[str, Any]],
    ) -> tuple[str, float | None, str, float, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []

        nodes = product_root.select("#product-price .price")
        chosen = next((node for node in nodes if parse_euro_price(safe_text(node)) is not None), None)
        trace.append(self._trace_selector("dom", "#product-price .price", nodes, chosen))
        if chosen:
            text = safe_text(chosen)
            price = parse_euro_price(text)
            if price is not None:
                return text, price, "dom:#product-price .price", 0.99, trace

        nodes = product_root.select("#product-price")
        for node in nodes:
            candidate = normalize_whitespace(node.get("data-price"))
            if candidate and re.search(r"\d", candidate):
                price = parse_euro_price(candidate)
                if price is None:
                    try:
                        price = float(candidate)
                    except ValueError:
                        price = None
                if price is not None:
                    trace.append(self._trace_selector("dom_attr", "#product-price", nodes, node, note=candidate))
                    return candidate, price, "dom_attr:#product-price[data-price]", 0.96, trace
        trace.append(self._trace_selector("dom_attr", "#product-price", nodes, None))

        for selector, attr, confidence in [
            ("meta[property='product:price:amount']", "content", 0.93),
            ("meta[itemprop='price']", "content", 0.92),
            ("[itemprop='price']", "content", 0.88),
        ]:
            nodes = soup.select(selector)
            chosen = next((node for node in nodes if self._node_attr_or_text(node, attr)), None)
            trace.append(self._trace_selector("dom", selector, nodes, chosen))
            if chosen:
                text = normalize_whitespace(self._node_attr_or_text(chosen, attr))
                price = parse_euro_price(text)
                if price is None and text:
                    try:
                        price = float(text.replace(",", "."))
                    except ValueError:
                        price = None
                if price is not None:
                    return text, price, f"dom:{selector}", confidence, trace

        for line in product_lines:
            if PRICE_RE.search(line):
                price = parse_euro_price(line)
                if price is not None:
                    return normalize_whitespace(line), price, "lines:price", 0.68, trace

        for item in self._product_jsonld_items(jsonld):
            offers = item.get("offers")
            if isinstance(offers, dict):
                price = offers.get("price")
                text = normalize_whitespace(str(price)) if price is not None else ""
                if text:
                    try:
                        return text, float(price), "jsonld:offers.price", 0.9, trace
                    except (TypeError, ValueError):
                        pass
        return "", None, "missing", 0.0, trace

    def _extract_installments_text(self, product_root: Tag | BeautifulSoup, product_lines: list[str]) -> str:
        for selector in ["#product-price .prod-tags-freeinstallments", "#product-price li"]:
            for node in product_root.select(selector):
                text = safe_text(node)
                if INSTALLMENTS_RE.search(text):
                    return normalize_whitespace(text)
        for line in product_lines:
            if INSTALLMENTS_RE.search(line):
                return normalize_whitespace(line)
        return ""

    def _extract_delivery_and_pickup(self, product_root: Tag | BeautifulSoup, product_lines: list[str]) -> tuple[str, str]:
        delivery = ""
        pickup = ""
        for label_node in product_root.select(".cpa-label"):
            label = safe_text(label_node)
            container = label_node.parent if isinstance(label_node.parent, Tag) else None
            if container is None:
                continue
            lines = split_visible_lines(container.get_text("\n"))
            value = next((line for line in lines if line != label), "")
            if normalize_for_match(label) == normalize_for_match("Παράδοση"):
                delivery = value
            if normalize_for_match(label) == normalize_for_match("Παραλαβή"):
                pickup = value
        if delivery or pickup:
            return delivery, pickup

        for idx, line in enumerate(product_lines):
            if normalize_for_match(line) == normalize_for_match("Παράδοση") and idx + 1 < len(product_lines):
                delivery = product_lines[idx + 1]
            if normalize_for_match(line) == normalize_for_match("Παραλαβή") and idx + 1 < len(product_lines):
                pickup = product_lines[idx + 1]
        return delivery, pickup

    def _extract_hero_summary(
        self,
        product_root: Tag | BeautifulSoup,
        soup: BeautifulSoup,
        product_lines: list[str],
        jsonld: list[dict[str, Any]],
        name: str,
    ) -> tuple[str, str, float, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []

        for selector, confidence in [(".product-desc p", 0.95), (".product-desc", 0.91)]:
            nodes = product_root.select(selector)
            chosen = next((node for node in nodes if safe_text(node)), None)
            trace.append(self._trace_selector("dom", selector, nodes, chosen))
            if chosen:
                return safe_text(chosen), f"dom:{selector}", confidence, trace

        for selector, attr, confidence in [
            ("meta[name='description']", "content", 0.9),
            ("meta[property='og:description']", "content", 0.88),
            ("meta[name='twitter:description']", "content", 0.86),
        ]:
            nodes = soup.select(selector)
            chosen = next((node for node in nodes if self._node_attr_or_text(node, attr)), None)
            trace.append(self._trace_selector("dom", selector, nodes, chosen))
            if chosen:
                return normalize_whitespace(self._node_attr_or_text(chosen, attr)), f"dom:{selector}", confidence, trace

        for item in self._product_jsonld_items(jsonld):
            description = item.get("description")
            if description:
                return normalize_whitespace(str(description)), "jsonld:description", 0.88, trace

        start = 0
        if name and name in product_lines:
            start = product_lines.index(name) + 1
        for idx in range(start, min(len(product_lines), start + 25)):
            line = product_lines[idx]
            if not line or PRICE_RE.search(line) or INSTALLMENTS_RE.search(line):
                continue
            if normalize_for_match(line) in {
                normalize_for_match("Φωτογραφίες"),
                normalize_for_match("Παρουσίαση Προϊόντος"),
                normalize_for_match("Τεχνικά Χαρακτηριστικά"),
                normalize_for_match("Παράδοση"),
                normalize_for_match("Παραλαβή"),
            }:
                continue
            if len(line) >= 40 and not line.isupper():
                return line, "lines:product_scope", 0.55, trace
        return "", "missing", 0.0, trace

    def _extract_key_specs(
        self,
        product_root: Tag | BeautifulSoup,
        product_lines: list[str],
        name: str,
    ) -> tuple[list[SpecItem], str, float, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        rows = product_root.select("#product-main-attributes .product-main-attribute")
        trace.append(self._trace_selector("dom", "#product-main-attributes .product-main-attribute", rows, rows[0] if rows else None, note=f"{len(rows)} rows"))
        if rows:
            items: list[SpecItem] = []
            for row in rows:
                label = safe_text(row.select_one(".my-label"))
                value = safe_text(row.select_one(".my-value"))
                if label and value:
                    items.append(SpecItem(label=label, value=nullify_dash_values(value)))
            items = self._dedupe_spec_items(items)
            if items:
                confidence = 0.94 if len(items) >= 3 else 0.84
                return items, "dom:#product-main-attributes .product-main-attribute", confidence, trace

        items = self._extract_key_specs_from_lines(product_lines, name)
        if items:
            return items, "lines:product_scope", 0.5, trace
        return [], "missing", 0.0, trace

    def _extract_key_specs_from_lines(self, product_lines: list[str], name: str) -> list[SpecItem]:
        items: list[SpecItem] = []
        start = 0
        if name and name in product_lines:
            start = product_lines.index(name) + 1
        hero_seen = False
        idx = start
        while idx < len(product_lines):
            line = product_lines[idx]
            normalized = normalize_for_match(line)
            if normalized in {
                normalize_for_match("Παράδοση"),
                normalize_for_match("Παρουσίαση Προϊόντος"),
                normalize_for_match("Τεχνικά Χαρακτηριστικά"),
            }:
                break
            if len(line) >= 40 and not hero_seen and not PRICE_RE.search(line) and not INSTALLMENTS_RE.search(line):
                hero_seen = True
                idx += 1
                continue
            if PRICE_RE.search(line) or INSTALLMENTS_RE.search(line):
                idx += 1
                continue
            if idx + 1 < len(product_lines):
                value = product_lines[idx + 1]
                if value and normalize_for_match(value) not in {
                    normalize_for_match("Παρουσίαση Προϊόντος"),
                    normalize_for_match("Τεχνικά Χαρακτηριστικά"),
                    normalize_for_match("Παράδοση"),
                    normalize_for_match("Παραλαβή"),
                }:
                    items.append(SpecItem(label=line, value=nullify_dash_values(value)))
                    idx += 2
                    continue
            idx += 1
        return self._dedupe_spec_items(items)

    def _extract_presentation_source(
        self,
        product_root: Tag | BeautifulSoup,
        soup: BeautifulSoup,
    ) -> tuple[str, str, int, str, float, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        all_blocks = product_root.select("#product-presentation .ck-text.whole, #product-presentation .ck-text.inline")
        inline_blocks = [block for block in all_blocks if "inline" in (block.get("class") or [])]
        trace.append(
            self._trace_selector(
                "dom",
                "#product-presentation .ck-text.whole, #product-presentation .ck-text.inline",
                all_blocks,
                all_blocks[0] if all_blocks else None,
                note=f"{len(all_blocks)} blocks ({len(inline_blocks)} inline)",
            )
        )
        if all_blocks:
            chunks = [str(node) for node in all_blocks]
            text_parts = [safe_text(node) for node in all_blocks if safe_text(node)]
            return (
                "\n".join(chunks).strip(),
                "\n".join(text_parts).strip(),
                len(inline_blocks),
                "dom:#product-presentation .ck-text.whole, #product-presentation .ck-text.inline",
                0.95,
                trace,
            )

        html, text = self._extract_presentation_between_headings(soup)
        if html or text:
            count = html.count("ck-text inline") or len(split_visible_lines(text))
            return html, text, count, "headings:Παρουσίαση Προϊόντος", 0.65, trace
        return "", "", 0, "missing", 0.0, trace

    def _extract_presentation_between_headings(self, soup: BeautifulSoup) -> tuple[str, str]:
        start_heading = self._find_heading(soup, "Παρουσίαση Προϊόντος")
        stop_heading = self._find_heading(soup, "Τεχνικά Χαρακτηριστικά")
        if not start_heading or not stop_heading:
            return "", ""
        chunks: list[str] = []
        text_parts: list[str] = []
        for node in start_heading.next_siblings:
            if node == stop_heading:
                break
            if isinstance(node, Tag):
                chunks.append(str(node))
                text = safe_text(node)
                if text:
                    text_parts.append(text)
            else:
                text = normalize_whitespace(str(node))
                if text:
                    text_parts.append(text)
        return "\n".join(chunks).strip(), "\n".join(text_parts).strip()

    def _find_heading(self, soup: BeautifulSoup | Tag, exact_text: str) -> Tag | None:
        target = normalize_for_match(exact_text)
        for tag in soup.find_all(re.compile(r"^h[1-6]$")):
            if normalize_for_match(safe_text(tag)) == target:
                return tag
        return None

    def _extract_spec_sections(
        self,
        product_root: Tag | BeautifulSoup,
        product_lines: list[str],
    ) -> tuple[list[SpecSection], str, float, list[SelectorTraceEntry]]:
        sections, trace = self._extract_spec_sections_from_product_details(product_root)
        if sections:
            return sections, "dom:#product-details .prop-group-wrapper", 0.98, trace

        sections, heading_trace = self._extract_spec_sections_from_heading_dom(product_root)
        trace.extend(heading_trace)
        if sections:
            return sections, "dom:headings", 0.8, trace

        sections = self._extract_spec_sections_from_lines(product_lines)
        if sections:
            return sections, "lines:product_scope", 0.55, trace
        return [], "missing", 0.0, trace

    def _extract_spec_sections_from_product_details(
        self,
        product_root: Tag | BeautifulSoup,
    ) -> tuple[list[SpecSection], list[SelectorTraceEntry]]:
        wrappers = product_root.select("#product-details .prop-group-wrapper")
        trace = [
            self._trace_selector(
                "dom",
                "#product-details .prop-group-wrapper",
                wrappers,
                wrappers[0] if wrappers else None,
                note=f"{len(wrappers)} sections",
            )
        ]
        sections: list[SpecSection] = []
        for wrapper in wrappers:
            title_node = wrapper.select_one(".prop-group-title")
            title = safe_text(title_node)
            if not title:
                continue
            items: list[SpecItem] = []
            for row in wrapper.select(".property"):
                cells = [safe_text(cell) for cell in row.find_all(["div", "span"], recursive=False) if safe_text(cell)]
                if len(cells) >= 2:
                    items.append(SpecItem(label=cells[0], value=nullify_dash_values(cells[-1])))
            if items:
                sections.append(SpecSection(section=title, items=items))
        return sections, trace

    def _extract_spec_sections_from_heading_dom(
        self,
        soup: BeautifulSoup | Tag,
    ) -> tuple[list[SpecSection], list[SelectorTraceEntry]]:
        start_heading = self._find_heading(soup, "Τεχνικά Χαρακτηριστικά")
        trace = [
            SelectorTraceEntry(
                strategy="dom",
                selector="heading:Τεχνικά Χαρακτηριστικά",
                match_count=1 if start_heading else 0,
                success=start_heading is not None,
                chosen_preview=safe_text(start_heading) if start_heading else "",
                note="heading fallback",
            )
        ]
        if not start_heading:
            return [], trace

        sections: list[SpecSection] = []
        current: SpecSection | None = None
        for node in start_heading.next_elements:
            if not isinstance(node, Tag):
                continue
            if node == start_heading:
                continue
            if node.name and re.fullmatch(r"h[1-6]", node.name):
                heading = safe_text(node)
                norm = normalize_for_match(heading)
                if norm in STOP_HEADINGS:
                    break
                if heading != "Τεχνικά Χαρακτηριστικά":
                    current = SpecSection(section=heading, items=[])
                    sections.append(current)
                continue
            if current is None:
                continue
            if node.name == "tr":
                cells = [safe_text(cell) for cell in node.find_all(["th", "td"])]
                if len(cells) >= 2:
                    current.items.append(SpecItem(label=cells[0], value=nullify_dash_values(cells[1])))
            elif node.name == "dt":
                sibling = node.find_next_sibling("dd")
                current.items.append(SpecItem(label=safe_text(node), value=nullify_dash_values(safe_text(sibling))))
        return [section for section in sections if section.items], trace

    def _extract_spec_sections_from_lines(self, text_lines: list[str]) -> list[SpecSection]:
        marker = "Τεχνικά Χαρακτηριστικά"
        if marker not in text_lines:
            return []
        start = text_lines.index(marker) + 1
        sections: list[SpecSection] = []
        current: SpecSection | None = None
        idx = start
        while idx < len(text_lines):
            line = text_lines[idx]
            norm = normalize_for_match(line)
            if norm in STOP_HEADINGS:
                break
            if self._is_section_title(line):
                current = SpecSection(section=line, items=[])
                sections.append(current)
                idx += 1
                continue
            if current is None:
                idx += 1
                continue
            label = line
            if idx + 1 >= len(text_lines):
                current.items.append(SpecItem(label=label, value=None))
                idx += 1
                continue
            next_line = text_lines[idx + 1]
            if self._is_section_title(next_line) or normalize_for_match(next_line) in STOP_HEADINGS:
                current.items.append(SpecItem(label=label, value=None))
                idx += 1
                continue
            current.items.append(SpecItem(label=label, value=nullify_dash_values(next_line)))
            idx += 2
        return [section for section in sections if section.items]

    def _is_section_title(self, line: str) -> bool:
        norm = normalize_for_match(line)
        if not norm:
            return False
        if norm in self.known_section_titles:
            return True
        if line.startswith("### "):
            return True
        return False

    def _extract_gallery_images(
        self,
        product_root: Tag | BeautifulSoup,
        soup: BeautifulSoup,
        url: str,
        name: str,
        brand: str,
        product_code: str,
    ) -> tuple[list[GalleryImage], str, float, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        nodes = product_root.select("img.lightbox")
        trace.append(
            self._trace_selector(
                "dom",
                "img.lightbox",
                nodes,
                nodes[0] if nodes else None,
                note=f"{len(nodes)} gallery candidates",
            )
        )
        if nodes:
            ordered_urls = dedupe_urls_preserve_order(
                [
                    make_absolute_url(node.get("src") or node.get("data-src") or node.get("data-original"), url)
                    for node in nodes
                    if node.get("src") or node.get("data-src") or node.get("data-original")
                ]
            )
            out: list[GalleryImage] = []
            for position, image_url in enumerate(ordered_urls, start=1):
                node = next(
                    (
                        item
                        for item in nodes
                        if make_absolute_url(item.get("src") or item.get("data-src") or item.get("data-original"), url) == image_url
                    ),
                    None,
                )
                alt = normalize_whitespace((node.get("alt") if node else "") or (node.get("title") if node else ""))
                out.append(GalleryImage(url=image_url, alt=alt, position=position))
            if out:
                return out, "dom:img.lightbox", 0.96, trace

        scored: list[tuple[int, int, str, str]] = []
        product_tokens = [token for token in normalize_for_match(name).split() if len(token) > 2][:8]
        brand_token = normalize_for_match(brand)
        for position, img in enumerate((product_root or soup).find_all("img"), start=1):
            src = img.get("src") or img.get("data-src") or img.get("data-original")
            if not src:
                continue
            abs_url = make_absolute_url(src, url)
            alt = normalize_whitespace(img.get("alt") or img.get("title") or "")
            haystack = normalize_for_match(f"{abs_url} {alt}")
            score = 0
            if any(token in haystack for token in product_tokens):
                score += 4
            if brand_token and brand_token in haystack:
                score += 1
            if product_code and product_code in haystack:
                score += 3
            if "/image/" in abs_url or "/catalog/" in abs_url or "/cache/" in abs_url:
                score += 1
            if "lightbox" in normalize_whitespace(img.get("class")):
                score += 3
            bad = ["logo", "icon", "energy", "share", "facebook", "twitter", "payment", "visa", "mastercard"]
            if any(token in haystack for token in bad):
                score -= 5
            if score > 0:
                scored.append((score, position, abs_url, alt))
        scored.sort(key=lambda item: (-item[0], item[1]))
        ordered_urls = dedupe_urls_preserve_order([item[2] for item in scored])
        out: list[GalleryImage] = []
        for position, image_url in enumerate(ordered_urls, start=1):
            alt = next((item[3] for item in scored if item[2] == image_url), "")
            out.append(GalleryImage(url=image_url, alt=alt, position=position))
        if out:
            return out, "heuristic:product_scope_images", 0.55, trace
        return [], "missing", 0.0, trace

    def _extract_assets(
        self,
        product_root: Tag | BeautifulSoup,
        soup: BeautifulSoup,
        url: str,
    ) -> tuple[str, str]:
        energy_label = ""
        product_sheet = ""
        for scope in [product_root, soup]:
            for trigger in scope.select(".eprel-modal-trigger"):
                label_candidate = self._resolve_eprel_asset_url(trigger.get("data-label-url"), url)
                if label_candidate and not energy_label:
                    energy_label = label_candidate
                sheet_candidate = self._resolve_eprel_asset_url(trigger.get("data-pdf-url"), url)
                if sheet_candidate and not product_sheet:
                    product_sheet = sheet_candidate
            for link in scope.find_all("a", href=True):
                text = normalize_for_match(link.get_text(" ", strip=True))
                img = link.find("img")
                img_alt = normalize_for_match(img.get("alt") if img else "")
                href = make_absolute_url(link["href"], url)
                if ("δελτίο προϊόντος" in text or "product sheet" in text) and href != url and not product_sheet:
                    product_sheet = href
                if any(token in f"{text} {img_alt}" for token in ["energy class", "ενεργειακ", "ενεργειακή κλάση"]):
                    if img and img.get("src") and not energy_label:
                        energy_label = make_absolute_url(img["src"], url)
            if energy_label or product_sheet:
                break
        return energy_label, product_sheet

    def _resolve_eprel_asset_url(self, raw_url: Any, page_url: str) -> str:
        candidate = normalize_whitespace(raw_url)
        if not candidate:
            return ""
        if candidate.startswith("/labels/") or candidate.startswith("/fiches/"):
            return f"{EPREL_HOST}{candidate}"
        return make_absolute_url(candidate, page_url)

    def _extract_mpn(
        self,
        key_specs: list[SpecItem],
        spec_sections: list[SpecSection],
        name: str,
        brand: str,
        jsonld: list[dict[str, Any]],
    ) -> tuple[str, str, float, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        mpn_labels = {
            normalize_for_match(label)
            for label in ["MPN", "Μοντέλο", "Model", "Κωδικός Μοντέλου", "Model Number"]
        }
        for item in key_specs:
            if normalize_for_match(item.label) in mpn_labels and item.value:
                return item.value, "key_specs:label_match", 0.96, trace
        for section in spec_sections:
            for item in section.items:
                if normalize_for_match(item.label) in mpn_labels and item.value:
                    return item.value, "spec_sections:label_match", 0.95, trace
        for item in self._product_jsonld_items(jsonld):
            for key in ["mpn", "model"]:
                candidate = normalize_whitespace(item.get(key))
                if candidate:
                    return candidate, f"jsonld:{key}", 0.9, trace

        title_after_brand = self._extract_model_token_after_brand(name, brand)
        if title_after_brand:
            return title_after_brand, "title_after_brand", 0.8, trace

        title_anywhere = self._extract_model_token_from_title(name)
        if title_anywhere:
            return title_anywhere, "title_scan", 0.68, trace
        return "", "missing", 0.0, trace

    def _extract_model_token_after_brand(self, name: str, brand: str) -> str:
        tokens = self._title_tokens(name)
        brand_norm = normalize_for_match(brand)
        if not tokens or not brand_norm:
            return ""
        for idx, token in enumerate(tokens):
            if normalize_for_match(token) == brand_norm:
                best = self._select_best_model_token(tokens[idx + 1 :])
                if best:
                    return best
                best_sequence = self._select_best_model_sequence(tokens[idx + 1 :])
                if best_sequence:
                    return best_sequence
        return ""

    def _extract_model_token_from_title(self, name: str) -> str:
        tokens = self._title_tokens(name)
        return self._select_best_model_token(tokens) or self._select_best_model_sequence(tokens)

    def _title_tokens(self, name: str) -> list[str]:
        tokens: list[str] = []
        for raw in normalize_whitespace(name).split():
            token = STRIP_PUNCT_RE.sub("", raw)
            if token:
                tokens.append(token)
        return tokens

    def _infer_brand_from_name(self, name: str) -> str:
        tokens = self._title_tokens(name)
        for idx, token in enumerate(tokens):
            if self._score_model_token(token) > 0 and idx > 0:
                return tokens[idx - 1]
        return ""

    def _select_best_model_token(self, tokens: list[str]) -> str:
        best_token = ""
        best_score = 0
        for token in tokens:
            score = self._score_model_token(token)
            if score > best_score:
                best_token = token.upper()
                best_score = score
        return best_token

    def _select_best_model_sequence(self, tokens: list[str]) -> str:
        best_sequence: list[str] = []
        best_score = 0
        max_len = 4
        for start in range(len(tokens)):
            for end in range(start + 2, min(len(tokens), start + max_len) + 1):
                sequence = tokens[start:end]
                score = self._score_model_sequence(sequence)
                if score > best_score:
                    best_sequence = sequence
                    best_score = score
        return normalize_whitespace(" ".join(best_sequence))

    def _score_model_sequence(self, tokens: list[str]) -> int:
        if len(tokens) < 2:
            return 0
        if not all(self._is_model_sequence_fragment(token) for token in tokens):
            return 0
        combined = "".join(tokens)
        if PURE_NUMERIC_TOKEN_RE.fullmatch(combined):
            return 0
        if not any(ch.isalpha() for ch in combined) or not any(ch.isdigit() for ch in combined):
            return 0
        score = 20 + len(combined)
        if tokens[0][0].isalpha():
            score += 3
        if tokens[-1][-1].isalpha():
            score += 3
        return score

    def _is_model_sequence_fragment(self, token: str) -> bool:
        normalized = normalize_whitespace(token)
        if not normalized or not all(ch.isalnum() or ch in "._/-" for ch in normalized):
            return False
        if PURE_NUMERIC_TOKEN_RE.fullmatch(normalized):
            return 2 <= len(normalized) <= 6
        if normalized.isalpha():
            return normalized == normalized.upper() and len(normalized) <= 4
        return self._score_model_token(normalized) > 0

    def _score_model_token(self, token: str) -> int:
        upper = token.upper()
        if PURE_NUMERIC_TOKEN_RE.fullmatch(token):
            return 0
        if len(upper) < 3:
            return 0
        if not all(ch.isalnum() or ch in "._/-" for ch in upper):
            return 0
        if not any(ch.isalpha() for ch in upper) or not any(ch.isdigit() for ch in upper):
            return 0
        score = 10
        if any(ch.isalpha() for ch in upper):
            score += 5
        if any(ch.isdigit() for ch in upper):
            score += 3
        if upper[0].isalpha():
            score += 2
        if len(upper) >= 6:
            score += 1
        return score

    def _dedupe_spec_items(self, items: list[SpecItem]) -> list[SpecItem]:
        deduped: list[SpecItem] = []
        seen: set[str] = set()
        for item in items:
            key = normalize_for_match(item.label)
            if key and key not in seen:
                seen.add(key)
                deduped.append(item)
        return deduped

    def _collect_missing_fields(self, source: SourceProductData) -> list[str]:
        missing: list[str] = []
        if not source.product_code:
            missing.append("product_code")
        if not source.brand:
            missing.append("brand")
        if not source.name:
            missing.append("name")
        if not source.price_text:
            missing.append("price")
        if not source.breadcrumbs:
            missing.append("breadcrumbs")
        if not source.hero_summary:
            missing.append("hero_summary")
        if not source.gallery_images:
            missing.append("gallery_images")
        if not source.spec_sections:
            missing.append("spec_sections")
        return missing

    def _collect_critical_missing(self, source: SourceProductData) -> list[str]:
        critical: list[str] = []
        if not source.name:
            critical.append("name")
        if not source.product_code:
            critical.append("product_code")
        if source.price_value is None:
            critical.append("price")
        if not source.breadcrumbs:
            critical.append("breadcrumbs")
        if not source.spec_sections:
            critical.append("spec_sections")
        if not source.gallery_images:
            critical.append("gallery_images")
        if not source.hero_summary:
            critical.append("hero_summary")
        return critical

    def _make_diagnostic(
        self,
        value: Any,
        selected_strategy: str,
        confidence: float,
        selector_trace: list[SelectorTraceEntry],
    ) -> FieldDiagnostic:
        return FieldDiagnostic(
            confidence=round(confidence, 4),
            selected_strategy=selected_strategy,
            value_present=self._value_present(value),
            value_preview=self._preview_value(value),
            selector_trace=selector_trace,
        )

    def _value_present(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(normalize_whitespace(value))
        if isinstance(value, list):
            return bool(value)
        if isinstance(value, (int, float)):
            return True
        return bool(value)

    def _preview_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return normalize_whitespace(value)[:160]
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            if not value:
                return ""
            first = value[0]
            if isinstance(first, SpecSection):
                return f"{len(value)} sections; first={first.section}"
            if isinstance(first, SpecItem):
                first_value = first.value or ""
                return f"{len(value)} items; first={first.label}:{first_value}"
            if isinstance(first, GalleryImage):
                return f"{len(value)} images; first={first.url}"
            return f"{len(value)} items"
        return normalize_whitespace(str(value))[:160]

    def _trace_selector(
        self,
        strategy: str,
        selector: str,
        nodes: list[Tag],
        chosen: Tag | None,
        note: str = "",
    ) -> SelectorTraceEntry:
        return SelectorTraceEntry(
            strategy=strategy,
            selector=selector,
            match_count=len(nodes),
            success=chosen is not None,
            chosen_preview=self._node_preview(chosen),
            note=normalize_whitespace(note),
        )

    def _node_preview(self, node: Tag | None) -> str:
        if node is None:
            return ""
        if node.name == "img":
            src = node.get("src") or node.get("data-src") or node.get("data-original") or ""
            alt = node.get("alt") or ""
            return normalize_whitespace(f"{alt} {src}")[:160]
        return safe_text(node)[:160]

    def _node_attr_or_text(self, node: Tag, attr: str | None) -> str:
        if attr:
            return normalize_whitespace(node.get(attr))
        return safe_text(node)
