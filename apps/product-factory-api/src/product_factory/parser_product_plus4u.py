from __future__ import annotations

import ast
import json
import re
from html import unescape
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

PLUS4U_TOKEN_MAP = {
    "ALFA": "\u0391",
    "alfa": "\u03b1",
    "alfa_tonos": "\u03ac",
    "BITA": "\u0392",
    "bita": "\u03b2",
    "GAMA": "\u0393",
    "gama": "\u03b3",
    "DELTA": "\u0394",
    "delta": "\u03b4",
    "EPSILON": "\u0395",
    "epsilon": "\u03b5",
    "epsilon_tonos": "\u03ad",
    "ZITA": "\u0396",
    "zita": "\u03b6",
    "ITA": "\u0397",
    "ita": "\u03b7",
    "ita_tonos": "\u03ae",
    "THITA": "\u0398",
    "thita": "\u03b8",
    "IOTA": "\u0399",
    "iota": "\u03b9",
    "iota_tonos": "\u03af",
    "iota_dia": "\u03ca",
    "KAPA": "\u039a",
    "kapa": "\u03ba",
    "LAMDA": "\u039b",
    "lamda": "\u03bb",
    "MI": "\u039c",
    "mi": "\u03bc",
    "NI": "\u039d",
    "ni": "\u03bd",
    "XI": "\u03a7",
    "xi": "\u03c7",
    "OMIKRON": "\u039f",
    "omikron": "\u03bf",
    "omikron_tonos": "\u03cc",
    "PI": "\u03a0",
    "pi": "\u03c0",
    "RO": "\u03a1",
    "ro": "\u03c1",
    "SIGMA": "\u03a3",
    "sigma": "\u03c3",
    "sigma_teliko": "\u03c2",
    "TAF": "\u03a4",
    "taf": "\u03c4",
    "IPSILON": "\u03a5",
    "ipsilon": "\u03c5",
    "ipsilon_tonos": "\u03cd",
    "FI": "\u03a6",
    "fi": "\u03c6",
    "CHI": "\u03a7",
    "chi": "\u03c7",
    "PSI": "\u03a8",
    "psi": "\u03c8",
    "OMEGA": "\u03a9",
    "omega": "\u03c9",
    "omega_tonos": "\u03ce",
    "return": "\n",
    "new_line": "\n",
    "backslash_quote": '"',
}
TOKEN_RE = re.compile(r"\{!([A-Za-z_]+)!\}")


class Plus4UProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        payload = self._extract_product_payload(html)
        canonical_url = self._extract_canonical_url(soup, payload, url)
        name = self._extract_name(soup, payload)
        brand = normalize_whitespace(str(payload.get("developer") or ""))
        product_code = normalize_whitespace(
            str(payload.get("kodikos") or payload.get("id") or "")
        )
        breadcrumbs = self._extract_breadcrumbs(payload)
        description = self._extract_description(soup, payload)
        spec_items = self._extract_spec_items(payload, soup)
        spec_sections = (
            [SpecSection(section="\u0391\u03bd\u03b1\u03bb\u03c5\u03c4\u03b9\u03ba\u03ac \u03a7\u03b1\u03c1\u03b1\u03ba\u03c4\u03b7\u03c1\u03b9\u03c3\u03c4\u03b9\u03ba\u03ac", items=spec_items)]
            if spec_items
            else []
        )
        mpn = self._extract_mpn(spec_items, name, brand)
        price_text, price_value = self._extract_price(payload, soup)
        gallery_images = self._extract_gallery_images(soup, payload, canonical_url, name)

        source = SourceProductData(
            source_name="plus4u",
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=breadcrumbs,
            product_code=product_code,
            brand=brand,
            mpn=mpn,
            name=name,
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
            "name": "js:product.title/dom:title" if name else "missing",
            "brand": "js:product.developer" if brand else "missing",
            "mpn": "spec_or_title:model_token" if mpn else "missing",
            "product_code": "js:product.kodikos" if product_code else "missing",
            "breadcrumbs": "js:product.category" if breadcrumbs else "missing",
            "gallery_images": "dom:plus4u_image_paths" if gallery_images else "missing",
            "spec_sections": "js:product.DescFields/dom:.product_details_group"
            if spec_sections
            else "missing",
            "hero_summary": "js:product.description/dom:.new_item_description"
            if description
            else "missing",
            "presentation_blocks": "not_applicable:plus4u_description_only",
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
                    "presentation_source_text",
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
                if field in {"name", "brand", "breadcrumbs", "gallery_images"}
            ],
            warnings=warnings,
        )

    def _extract_product_payload(self, html: str) -> dict[str, Any]:
        match = re.search(r"var\s+product\s*=\s*JsonFromPHP\('(.+?)'\);", html, re.S)
        if not match:
            return {}
        raw = match.group(1)
        try:
            json_text = ast.literal_eval("'" + raw + "'")
            payload = json.loads(json_text)
        except Exception:
            return {}
        decoded = self._decode_placeholders(payload)
        return decoded if isinstance(decoded, dict) else {}

    def _decode_placeholders(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(self._decode_placeholders(key)): self._decode_placeholders(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._decode_placeholders(item) for item in value]
        if isinstance(value, str):
            return normalize_whitespace(
                TOKEN_RE.sub(lambda match: PLUS4U_TOKEN_MAP.get(match.group(1), ""), value)
            )
        return value

    def _extract_canonical_url(
        self, soup: BeautifulSoup, payload: dict[str, Any], fallback_url: str
    ) -> str:
        candidate = normalize_whitespace(str(payload.get("item_link") or ""))
        if not candidate:
            node = soup.select_one("meta[property='og:url'], link[rel='canonical']")
            candidate = normalize_whitespace(node.get("content") or node.get("href") if node else "")
        return make_absolute_url(candidate or fallback_url, fallback_url)

    def _extract_name(self, soup: BeautifulSoup, payload: dict[str, Any]) -> str:
        title = normalize_whitespace(str(payload.get("title") or ""))
        if title:
            return title
        node = soup.select_one("meta[property='og:title'], title")
        text = normalize_whitespace(node.get("content") if node and node.has_attr("content") else safe_text(node))
        return re.sub(r"\s*\|\s*Plus4u\s*$", "", text, flags=re.I)

    def _extract_breadcrumbs(self, payload: dict[str, Any]) -> list[str]:
        category = normalize_whitespace(str(payload.get("category") or ""))
        subcat = normalize_whitespace(str(payload.get("subcat") or ""))
        category2 = normalize_whitespace(str(payload.get("category2") or ""))
        values = []
        if category:
            if " " in category:
                values.extend(part.title() for part in category.split() if part)
            else:
                values.append(category.title())
        if subcat and normalize_for_match(subcat) != normalize_for_match(category2):
            values.append(subcat.title())
        elif category2 and normalize_for_match(category2) != normalize_for_match(category):
            values.append(category2.title())
        return clean_breadcrumbs(values)

    def _extract_description(self, soup: BeautifulSoup, payload: dict[str, Any]) -> str:
        raw = normalize_whitespace(str(payload.get("description") or ""))
        lines = self._description_lines_from_html(raw)
        if not lines:
            node = soup.select_one(".new_item_description")
            lines = [
                normalize_whitespace(line)
                for line in (node.get_text("\n") if node else "").splitlines()
                if normalize_whitespace(line)
            ]
        return normalize_whitespace(" ".join(line for line in lines if not line.startswith("<")))

    def _description_lines_from_html(self, raw: str) -> list[str]:
        if not raw:
            return []
        main = raw.split("<tab2>", 1)[0].replace("<tab1>", "")
        main = main.replace("<li>", "\n")
        text = BeautifulSoup(unescape(main), "lxml").get_text("\n")
        return [
            normalize_whitespace(line)
            for line in text.splitlines()
            if normalize_whitespace(line)
        ]

    def _extract_spec_items(
        self, payload: dict[str, Any], soup: BeautifulSoup
    ) -> list[SpecItem]:
        items: list[SpecItem] = []
        desc_fields = payload.get("DescFields")
        if isinstance(desc_fields, dict):
            for label, value in desc_fields.items():
                label_text = self._normalize_spec_label(
                    normalize_whitespace(str(label)).strip(" :"),
                    normalize_whitespace(str(value)).strip(" :"),
                )
                value_text = self._normalize_spec_value(label_text, str(value))
                if label_text and value_text:
                    items.append(SpecItem(label_text, value_text))
        if not items:
            for row in soup.select(".product_details_group_row, .new_item_details tr"):
                cells = [safe_text(cell) for cell in row.find_all(["td", "th", "div"])]
                cells = [cell for cell in cells if cell]
                if len(cells) >= 2:
                    items.append(SpecItem(cells[0].rstrip(":"), cells[1]))
        items.extend(self._derived_spec_items(payload, items))
        return self._dedupe_items(items)

    def _normalize_spec_label(self, label: str, value: str) -> str:
        label_key = normalize_for_match(label)
        value_key = normalize_for_match(value)
        if label_key == "bar" or "πιεση" in value_key and "bar" in value_key:
            return "\u03a0\u03af\u03b5\u03c3\u03b7 \u0391\u03c4\u03bc\u03bf\u03cd"
        if label_key in {
            normalize_for_match("\u0399\u03c3\u03c7\u03cd\u03c2 (Watt)"),
            normalize_for_match("\u0399\u03c3\u03c7\u03cd\u03c2"),
        }:
            return "\u0399\u03c3\u03c7\u03cd\u03c2 \u03c3\u03b5 Watts"
        if "διαστασεις" in label_key:
            return "\u0394\u03b9\u03b1\u03c3\u03c4\u03ac\u03c3\u03b5\u03b9\u03c2 \u03a3\u03c5\u03c3\u03ba\u03b5\u03c5\u03ae\u03c2 \u03c3\u03b5 \u0395\u03ba\u03b1\u03c4\u03bf\u03c3\u03c4\u03ac. (\u03a5 x \u03a0 x \u0392)"
        if label_key == normalize_for_match("\u0392\u03ac\u03c1\u03bf\u03c2"):
            return "\u0392\u03ac\u03c1\u03bf\u03c2 \u03a3\u03c5\u03c3\u03ba\u03b5\u03c5\u03ae\u03c2 \u03c3\u03b5 \u039a\u03b9\u03bb\u03ac"
        return label

    def _normalize_spec_value(self, label: str, value: str) -> str:
        normalized = normalize_whitespace(str(value)).strip(" :")
        if label == "\u03a0\u03af\u03b5\u03c3\u03b7 \u0391\u03c4\u03bc\u03bf\u03cd":
            match = re.search(r"\d+(?:[.,]\d+)?\s*bar", normalized, re.I)
            return match.group(0) if match else normalized
        if label == "\u0399\u03c3\u03c7\u03cd\u03c2 \u03c3\u03b5 Watts":
            match = re.search(r"\d+(?:[.,]\d+)?\s*(?:watt|w)\b", normalized, re.I)
            return match.group(0).replace("watt", "Watt") if match else normalized
        return normalized

    def _derived_spec_items(
        self, payload: dict[str, Any], existing_items: list[SpecItem]
    ) -> list[SpecItem]:
        derived: list[SpecItem] = []
        labels = {normalize_for_match(item.label) for item in existing_items}
        description = normalize_whitespace(str(payload.get("description") or ""))
        title = normalize_whitespace(str(payload.get("title") or ""))
        combined = normalize_whitespace(f"{title} {description}")
        if normalize_for_match("\u03a4\u03cd\u03c0\u03bf\u03c2 \u039a\u03b1\u03c6\u03ad") not in labels:
            if "nespresso" in normalize_for_match(combined):
                derived.append(SpecItem("\u03a4\u03cd\u03c0\u03bf\u03c2 \u039a\u03b1\u03c6\u03ad", "Nespresso"))
        if normalize_for_match("\u03a7\u03c1\u03ce\u03bc\u03b1") not in labels:
            color = self._extract_color(title)
            if color:
                derived.append(SpecItem("\u03a7\u03c1\u03ce\u03bc\u03b1", color))
        if (
            normalize_for_match(
                "\u03a7\u03c9\u03c1\u03b7\u03c4\u03b9\u03ba\u03cc\u03c4\u03b7\u03c4\u03b1 \u0394\u03bf\u03c7\u03b5\u03af\u03bf\u03c5 \u039d\u03b5\u03c1\u03bf\u03cd (\u039b\u03af\u03c4\u03c1\u03b1)"
            )
            not in labels
        ):
            match = re.search(r"\b(\d+(?:[,.]\d+)?)\s*(?:lt|l|λίτρ)", combined, re.I)
            if match:
                derived.append(
                    SpecItem(
                        "\u03a7\u03c9\u03c1\u03b7\u03c4\u03b9\u03ba\u03cc\u03c4\u03b7\u03c4\u03b1 \u0394\u03bf\u03c7\u03b5\u03af\u03bf\u03c5 \u039d\u03b5\u03c1\u03bf\u03cd (\u039b\u03af\u03c4\u03c1\u03b1)",
                        match.group(1).replace(",", "."),
                    )
                )
        return derived

    def _extract_color(self, title: str) -> str:
        key = normalize_for_match(title)
        if "μαυρο" in key:
            return "\u039c\u03b1\u03cd\u03c1\u03bf"
        if "λευκο" in key:
            return "\u039b\u03b5\u03c5\u03ba\u03cc"
        if "ασημι" in key or "inox" in key:
            return "\u0391\u03c3\u03b7\u03bc\u03af"
        return ""

    def _extract_mpn(self, spec_items: list[SpecItem], name: str, brand: str) -> str:
        labels = {
            normalize_for_match("MPN"),
            normalize_for_match("\u039c\u03bf\u03bd\u03c4\u03ad\u03bb\u03bf"),
            normalize_for_match("Model"),
        }
        for item in spec_items:
            if normalize_for_match(item.label) in labels and item.value:
                return normalize_whitespace(item.value)
        title = normalize_whitespace(name)
        if brand and normalize_for_match(title).startswith(normalize_for_match(brand)):
            title = title[len(brand) :].strip()
        candidates = re.findall(
            r"\b(?=[A-Z0-9.-]*[A-Z])(?=[A-Z0-9.-]*\d)[A-Z0-9][A-Z0-9.-]{3,}\b",
            title,
            flags=re.I,
        )
        return candidates[-1].upper() if candidates else ""

    def _extract_price(
        self, payload: dict[str, Any], soup: BeautifulSoup
    ) -> tuple[str, float | None]:
        for key in ("price", "originalprice", "price30"):
            value = normalize_whitespace(str(payload.get(key) or ""))
            if value and value != "0":
                return value, parse_euro_price(value)
        node = soup.select_one("[itemprop='price'], .price, .new_item_price")
        text = normalize_whitespace(node.get("content") if node and node.has_attr("content") else safe_text(node))
        return text, parse_euro_price(text) if text else None

    def _extract_gallery_images(
        self, soup: BeautifulSoup, payload: dict[str, Any], base_url: str, name: str
    ) -> list[GalleryImage]:
        candidates: list[str] = []
        for script in soup.find_all("script"):
            text = script.string or script.get_text()
            candidates.extend(re.findall(r"['\"]([^'\"]+/images/\d+/(?:BIG|ZOOM|SMALL|VSMALL)/[^'\"]+\.(?:jpe?g|png|webp)(?:\?[^'\"]*)?)['\"]", text, re.I))
        for image in soup.find_all("img"):
            for attr in ("data-big-img", "data-zoom-image", "data-src", "src"):
                value = normalize_whitespace(str(image.get(attr) or ""))
                if re.search(r"/images/\d+/(?:BIG|ZOOM|SMALL|VSMALL)/", value, re.I):
                    candidates.append(value)
        table = normalize_whitespace(str(payload.get("table") or ""))
        product_id = normalize_whitespace(str(payload.get("id") or payload.get("kodikos") or ""))
        if table and product_id:
            candidates.insert(0, f"/images/{table}/BIG/{product_id}.jpg")
        urls = dedupe_urls_preserve_order(
            [make_absolute_url(candidate, base_url) for candidate in candidates if candidate]
        )
        return [
            GalleryImage(url=image_url, alt=name, position=position)
            for position, image_url in enumerate(urls, start=1)
        ]

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
        if not source.product_code:
            missing.append("product_code")
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
            confidence=0.92 if present else 0.0,
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
