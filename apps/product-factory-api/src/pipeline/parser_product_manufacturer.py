from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from .deterministic_fields import extract_mpn_from_name
from .eprel import resolve_eprel_energy_label_asset_url
from .manufacturer_enrichment import _parse_tefal_shop_product_page
from .models import FieldDiagnostic, GalleryImage, ParsedProduct, SourceProductData, SpecItem, SpecSection
from .normalize import dedupe_urls_preserve_order, make_absolute_url, normalize_for_match, normalize_whitespace, parse_euro_price, safe_text
from .skroutz_taxonomy import build_breadcrumbs, serialize_source_category
from .utils import utcnow_iso

TEFAL_FAMILY_TAXONOMY: dict[str, tuple[str, str, str]] = {
    "ice_cream_maker": ("ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Μικροί Μάγειρες", "Παγωτομηχανές"),
    "coffee_filter": ("ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Καφές-Ροφήματα-Χυμοί", "Καφετιέρες Φίλτρου"),
    "kettle": ("ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Συσκευές Κουζίνας", "Βραστήρες"),
}
WARRANTY_RE = re.compile(r"(\d+)\s+χρόν(?:ι|ια)[^\n]{0,24}εγγ", re.IGNORECASE)
BOSCH_FAMILY_TAXONOMY: dict[str, tuple[str, str, str]] = {
    "built_in_oven": ("ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ", "Εντοιχιζόμενες Συσκευές", "Φούρνοι"),
}
POWER_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*W\b", re.IGNORECASE)
LITERS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:lt|l\b|λίτρ(?:α|ο)?|λιτρ(?:α|ο)?)", re.IGNORECASE)
PROGRAMS_RE = re.compile(r"(\d+)\s+προγράμματ(?:α|ων)", re.IGNORECASE)
BOWLS_RE = re.compile(r"(\d+)\s+(?:μπολ|δοχεία|δοχεια)", re.IGNORECASE)
CUPS_RE = re.compile(r"(\d+(?:\s*-\s*\d+)?)\s*(?:φλιτζ|cups?)", re.IGNORECASE)


class ManufacturerProductParser:
    def parse(
        self,
        html: str,
        url: str,
        *,
        source_name: str,
        fallback_used: bool = False,
    ) -> ParsedProduct:
        normalized_source = normalize_for_match(source_name)
        if normalized_source == normalize_for_match("manufacturer_bosch"):
            return self._parse_bosch_product(html, url, source_name=source_name, fallback_used=fallback_used)
        if normalized_source != normalize_for_match("manufacturer_tefal"):
            raise ValueError(f"Unsupported manufacturer parser source: {source_name}")
        return self._parse_tefal_product(html, url, source_name=source_name, fallback_used=fallback_used)

    def _parse_bosch_product(
        self,
        html: str,
        url: str,
        *,
        source_name: str,
        fallback_used: bool,
    ) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        canonical_url = self._extract_canonical_url(soup, url)
        product = self._extract_bosch_next_product(soup)
        jsonld = self._extract_bosch_product_jsonld(soup)
        mpn = (
            normalize_whitespace(str(product.get("productCode", "")))
            or normalize_whitespace(str(product.get("eNumber", "")))
            or normalize_whitespace(str(jsonld.get("mpn", "")))
            or self._extract_model_from_url(canonical_url)
        )
        brand = self._normalize_bosch_brand(product.get("productBrand") or jsonld.get("brand") or "BOSCH")
        title = self._build_bosch_title(product, jsonld, soup)
        family_key = self._infer_bosch_family(canonical_url, title, product)
        taxonomy_fields = self._build_bosch_taxonomy_fields(family_key)
        spec_sections = self._build_bosch_spec_sections(product)
        key_specs = self._build_bosch_key_specs(spec_sections, family_key)
        gallery_images = self._build_bosch_gallery_images(product, jsonld, title)
        energy_label = product.get("energyLabel") if isinstance(product.get("energyLabel"), dict) else {}
        energy_label_asset_url = resolve_eprel_energy_label_asset_url(
            family_key=family_key,
            breadcrumbs=taxonomy_fields["breadcrumbs"],
            taxonomy_source_category=str(taxonomy_fields["source_category"] or ""),
            title=title,
            canonical_url=canonical_url,
            model_identifier=mpn,
            gtin=product.get("ean"),
            eprel_registration_number=self._nested_text(product, ["energyLabel", "eprelRegistrationNumber"]),
        )
        energy_label_pdf = self._nested_text(product, ["energyLabel", "pdf", "link", "value"])
        product_sheet_asset_url = self._nested_text(product, ["dataSheet", "url"]) or energy_label_pdf
        presentation_source_html, presentation_source_text = self._build_bosch_presentation_source(product)
        hero_summary = self._build_bosch_hero_summary(product, title)
        warnings: list[str] = []
        if not product:
            warnings.append("manufacturer_bosch_next_product_missing")
        if not family_key:
            warnings.append("manufacturer_family_unresolved")
        if not gallery_images:
            warnings.append("gallery_images_missing")
        if energy_label_pdf and not energy_label_asset_url:
            warnings.append("energy_label_pdf_available_without_image")

        source = SourceProductData(
            source_name=source_name,
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=taxonomy_fields["breadcrumbs"],
            skroutz_family="built_in_appliance" if family_key == "built_in_oven" else family_key,
            category_tag_text="",
            category_tag_href="",
            category_tag_slug="",
            taxonomy_source_category=taxonomy_fields["source_category"],
            taxonomy_match_type=taxonomy_fields["match_type"],
            taxonomy_rule_id=taxonomy_fields["rule_id"],
            taxonomy_ambiguity=False,
            taxonomy_escalation_reason="manufacturer_family_unresolved" if not family_key else "",
            taxonomy_tv_inches=None,
            product_code=mpn,
            brand=brand,
            name=title,
            hero_summary=hero_summary,
            price_text="",
            price_value=None,
            gallery_images=gallery_images,
            energy_label_asset_url=energy_label_asset_url,
            product_sheet_asset_url=product_sheet_asset_url,
            key_specs=key_specs,
            spec_sections=spec_sections,
            manufacturer_spec_sections=[],
            manufacturer_source_text=self._bosch_specs_text(spec_sections),
            manufacturer_documents=(
                [{"name": "energy_label", "document_type": "pdf", "url": energy_label_pdf}]
                if energy_label_pdf
                else []
            ),
            presentation_source_html=presentation_source_html,
            presentation_source_text=presentation_source_text,
            raw_html_path="",
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
            mpn=mpn,
        )
        provenance = {
            "name": "next:product.title" if title else "missing",
            "brand": "next:productBrand",
            "product_code": "next:productCode" if mpn else "missing",
            "price": "missing",
            "hero_summary": "next:highlights",
            "breadcrumbs": taxonomy_fields["rule_id"] or "missing",
            "gallery_images": "next:product.images",
            "spec_sections": "next:product.specifications",
            "mpn": "next:productCode" if mpn else "missing",
        }
        diagnostics = {
            "name": self._diagnostic(title, provenance["name"], 0.96 if title else 0.0),
            "brand": self._diagnostic(brand, provenance["brand"], 0.98 if brand else 0.0),
            "product_code": self._diagnostic(mpn, provenance["product_code"], 0.98 if mpn else 0.0),
            "price": self._diagnostic(None, provenance["price"], 0.0),
            "hero_summary": self._diagnostic(hero_summary, provenance["hero_summary"], 0.9 if hero_summary else 0.0),
            "breadcrumbs": self._diagnostic(source.breadcrumbs, provenance["breadcrumbs"], 0.9 if source.breadcrumbs else 0.0),
            "gallery_images": self._diagnostic(gallery_images, provenance["gallery_images"], 0.94 if gallery_images else 0.0),
            "spec_sections": self._diagnostic(spec_sections, provenance["spec_sections"], 0.94 if spec_sections else 0.0),
            "mpn": self._diagnostic(mpn, provenance["mpn"], 0.98 if mpn else 0.0),
        }
        missing_fields = self._collect_missing_fields(source)
        critical_missing = self._collect_critical_missing(source)
        return ParsedProduct(
            source=source,
            provenance=provenance,
            field_diagnostics=diagnostics,
            missing_fields=missing_fields,
            warnings=warnings,
            critical_missing=critical_missing,
        )

    def _parse_tefal_product(
        self,
        html: str,
        url: str,
        *,
        source_name: str,
        fallback_used: bool,
    ) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        canonical_url = self._extract_canonical_url(soup, url)
        title = self._extract_title(soup)
        json_item = self._extract_json_item(soup, title=title, canonical_url=canonical_url)
        brand = self._normalize_brand(str(json_item.get("item_brand", ""))) or self._infer_brand_from_title(title) or "Tefal"
        raw_product_code = normalize_whitespace(str(json_item.get("item_id", ""))) or self._extract_product_code_from_scripts(html)
        mpn = extract_mpn_from_name(title, brand) or raw_product_code
        product_code = mpn or raw_product_code
        price_text, price_value = self._extract_price(soup, json_item)
        parsed_page = _parse_tefal_shop_product_page(html)
        hero_summary = normalize_whitespace(parsed_page.hero_summary)
        presentation_source_html = parsed_page.presentation_source_html
        presentation_source_text = normalize_whitespace(parsed_page.presentation_source_text)
        family_key = self._infer_tefal_family(title, canonical_url, hero_summary, presentation_source_text)
        taxonomy_fields = self._build_taxonomy_fields(family_key)
        feature_sections = self._build_feature_sections(
            family_key=family_key,
            title=title,
            url=canonical_url,
            hero_summary=hero_summary,
            presentation_source_text=presentation_source_text,
            product_code=product_code or mpn,
        )
        manufacturer_sections = list(parsed_page.manufacturer_spec_sections)
        all_spec_sections = self._merge_sections(feature_sections, manufacturer_sections)
        key_specs = self._build_key_specs(all_spec_sections)
        gallery_images = self._extract_gallery_images(soup, canonical_url, fallback_alt=title)
        warnings: list[str] = []
        if not family_key:
            warnings.append("manufacturer_family_unresolved")
        if not gallery_images:
            warnings.append("gallery_images_missing")

        source = SourceProductData(
            source_name=source_name,
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=taxonomy_fields["breadcrumbs"],
            skroutz_family=family_key,
            category_tag_text="",
            category_tag_href="",
            category_tag_slug="",
            taxonomy_source_category=taxonomy_fields["source_category"],
            taxonomy_match_type=taxonomy_fields["match_type"],
            taxonomy_rule_id=taxonomy_fields["rule_id"],
            taxonomy_ambiguity=False,
            taxonomy_escalation_reason="manufacturer_family_unresolved" if not family_key else "",
            taxonomy_tv_inches=None,
            product_code=product_code or mpn,
            brand=brand,
            name=title,
            hero_summary=hero_summary,
            price_text=price_text,
            price_value=price_value,
            gallery_images=gallery_images,
            key_specs=key_specs,
            spec_sections=feature_sections,
            manufacturer_spec_sections=manufacturer_sections,
            manufacturer_source_text=normalize_whitespace(parsed_page.manufacturer_source_text),
            presentation_source_html=presentation_source_html,
            presentation_source_text=presentation_source_text,
            raw_html_path="",
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
            mpn=mpn,
        )
        product_code_strategy = (
            "heuristic:title_model_token"
            if product_code == mpn and mpn
            else "script:json-item"
            if json_item.get("item_id")
            else "regex:script"
        )
        provenance = {
            "name": "dom:h1",
            "brand": "script:json-item" if json_item.get("item_brand") else "heuristic:title",
            "product_code": product_code_strategy,
            "price": "dom:.t-h3" if price_text else "script:json-item",
            "hero_summary": "tefal:title_description_sidebar",
            "breadcrumbs": taxonomy_fields["rule_id"] or "missing",
            "gallery_images": "dom:clrz-slider-product",
            "spec_sections": "tefal:feature_inference_and_specs",
            "mpn": "heuristic:title_model_token",
        }
        diagnostics = {
            "name": self._diagnostic(title, provenance["name"], 0.99),
            "brand": self._diagnostic(brand, provenance["brand"], 0.95),
            "product_code": self._diagnostic(product_code or mpn, provenance["product_code"], 0.92 if product_code or mpn else 0.0),
            "price": self._diagnostic(price_text or price_value, provenance["price"], 0.95 if price_text or price_value else 0.0),
            "hero_summary": self._diagnostic(hero_summary, provenance["hero_summary"], 0.94 if hero_summary else 0.0),
            "breadcrumbs": self._diagnostic(source.breadcrumbs, provenance["breadcrumbs"], 0.9 if source.breadcrumbs else 0.0),
            "gallery_images": self._diagnostic(gallery_images, provenance["gallery_images"], 0.9 if gallery_images else 0.0),
            "spec_sections": self._diagnostic(all_spec_sections, provenance["spec_sections"], 0.88 if all_spec_sections else 0.0),
            "mpn": self._diagnostic(mpn, provenance["mpn"], 0.9 if mpn else 0.0),
        }
        missing_fields = self._collect_missing_fields(source)
        critical_missing = self._collect_critical_missing(source)
        return ParsedProduct(
            source=source,
            provenance=provenance,
            field_diagnostics=diagnostics,
            missing_fields=missing_fields,
            warnings=warnings,
            critical_missing=critical_missing,
        )

    def _extract_bosch_next_product(self, soup: BeautifulSoup) -> dict[str, Any]:
        chunks: list[str] = []
        for script in soup.find_all("script"):
            raw = script.string or script.get_text()
            if "self.__next_f.push" not in raw:
                continue
            match = re.search(r"self\.__next_f\.push\((\[.*\])\)", raw, flags=re.DOTALL)
            if not match:
                continue
            try:
                payload = json.loads(match.group(1))
            except Exception:
                continue
            if len(payload) > 1 and isinstance(payload[1], str):
                chunks.append(payload[1])
        joined = "".join(chunks)
        marker = '"productCode"'
        for marker_match in re.finditer(marker, joined):
            product = self._extract_enclosing_json_object(joined, marker_match.start())
            if product.get("productCode") or product.get("eNumber"):
                return product
        return {}

    def _extract_enclosing_json_object(self, text: str, index: int) -> dict[str, Any]:
        candidate_starts = [match.start() for match in re.finditer(r"\{", text[:index])]
        for start in reversed(candidate_starts[-5000:]):
            end = self._find_matching_json_object_end(text, start)
            if end is None or end <= index:
                continue
            try:
                candidate = json.loads(text[start:end])
            except Exception:
                continue
            if isinstance(candidate, dict):
                return candidate
        return {}

    def _find_matching_json_object_end(self, text: str, start: int) -> int | None:
        in_string = False
        escaped = False
        depth = 0
        for offset, char in enumerate(text[start:], start=start):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return offset + 1
        return None

    def _extract_bosch_product_jsonld(self, soup: BeautifulSoup) -> dict[str, Any]:
        for script in soup.select("script[type='application/ld+json']"):
            raw = script.string or script.get_text(" ", strip=True)
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            candidates = payload if isinstance(payload, list) else [payload]
            for candidate in candidates:
                if isinstance(candidate, dict) and normalize_for_match(candidate.get("@type", "")) == "product":
                    return candidate
        return {}

    def _build_bosch_title(self, product: dict[str, Any], jsonld: dict[str, Any], soup: BeautifulSoup) -> str:
        title = product.get("title") if isinstance(product.get("title"), dict) else {}
        parts = [
            normalize_whitespace(str(title.get("valueClass", ""))),
            normalize_whitespace(str(title.get("headline", ""))),
        ]
        joined = normalize_whitespace(" ".join(part for part in parts if part))
        if joined:
            return joined
        value = normalize_whitespace(str(jsonld.get("name", "")))
        if value:
            return value
        return self._extract_title(soup)

    def _normalize_bosch_brand(self, value: Any) -> str:
        if isinstance(value, dict):
            value = value.get("name", "")
        normalized = normalize_for_match(str(value or ""))
        if normalized == normalize_for_match("BOSCH"):
            return "Bosch"
        return normalize_whitespace(str(value or ""))

    def _extract_model_from_url(self, url: str) -> str:
        tail = normalize_whitespace(url.rstrip("/").rsplit("/", 1)[-1])
        return tail.upper() if MODEL_TOKEN_RE.match(tail.upper()) else ""

    def _infer_bosch_family(self, canonical_url: str, title: str, product: dict[str, Any]) -> str:
        breadcrumbs = " ".join(
            normalize_whitespace(str(item.get("title") or item.get("seoName") or ""))
            for item in (product.get("combinedBreadcrumbs") or [])
            if isinstance(item, dict)
        )
        haystack = normalize_for_match(" ".join([canonical_url, title, breadcrumbs]))
        if any(token in haystack for token in ["entoixizomenoi fournoi", "εντοιχιζομενοι φουρνοι", "φουρνος", "fournos", "oven"]):
            return "built_in_oven"
        return ""

    def _build_bosch_taxonomy_fields(self, family_key: str) -> dict[str, str | list[str]]:
        if not family_key or family_key not in BOSCH_FAMILY_TAXONOMY:
            return {
                "breadcrumbs": [],
                "source_category": "",
                "match_type": "",
                "rule_id": "",
            }
        parent, leaf, sub = BOSCH_FAMILY_TAXONOMY[family_key]
        return {
            "breadcrumbs": build_breadcrumbs(parent, leaf, sub),
            "source_category": serialize_source_category(parent, leaf, [sub]),
            "match_type": "exact_category",
            "rule_id": f"manufacturer_bosch:{family_key}",
        }

    def _build_bosch_spec_sections(self, product: dict[str, Any]) -> list[SpecSection]:
        sections: list[SpecSection] = []
        for group in (product.get("specifications") or []):
            if not isinstance(group, dict):
                continue
            title = normalize_whitespace(str(group.get("name", "")))
            items: list[SpecItem] = []
            for item in (group.get("specifications") or []):
                if not isinstance(item, dict):
                    continue
                label = self._localized_text(item.get("name"))
                value = self._bosch_spec_value(item)
                if label and value:
                    items.append(SpecItem(label=label, value=value))
            if title and items:
                sections.append(SpecSection(section=title, items=self._dedupe_items(items)))
        return sections

    def _build_bosch_key_specs(self, spec_sections: list[SpecSection], family_key: str) -> list[SpecItem]:
        specs_by_label: dict[str, str] = {}
        for section in spec_sections:
            for item in section.items:
                if item.label and item.value and item.label not in specs_by_label:
                    specs_by_label[item.label] = item.value

        key_specs: list[SpecItem] = []
        if family_key == "built_in_oven":
            key_specs.append(SpecItem(label="Τύπος Φούρνου", value="Ηλεκτρικός"))
        canonical_aliases = [
            ("Χωρητικότητα Φούρνου", ["Ωφέλιμος όγκος θαλάμου - ΝΕΟ (2010/30/ΕΚ)", "Ωφέλιμος όγκος θαλάμου"]),
            ("Ενεργειακή Κλάση", ["Ενεργειακή κλάση"]),
            ("Χρώμα", ["Χρώμα συσκευής", "Χρώμα / Υλικό πορτών", "Χρώμα/Υλικό μετόπης χειρισμού"]),
        ]
        for canonical_label, aliases in canonical_aliases:
            value = next((specs_by_label[alias] for alias in aliases if specs_by_label.get(alias)), "")
            if value:
                key_specs.append(SpecItem(label=canonical_label, value=value))
        return [*key_specs, *self._build_key_specs(spec_sections)]

    def _bosch_spec_value(self, item: dict[str, Any]) -> str:
        value = self._localized_text(item.get("value"))
        if bool(item.get("requiresValueTranslation")):
            normalized = normalize_for_match(value)
            if normalized.endswith("translatedboolean yes"):
                value = "Ναι"
            elif normalized.endswith("translatedboolean no"):
                value = "Όχι"
        unit = normalize_whitespace(str(item.get("unit", "") or ""))
        if unit and value and not normalize_for_match(value).endswith(normalize_for_match(unit)):
            value = f"{value} {unit}"
        return normalize_whitespace(value)

    def _localized_text(self, payload: Any) -> str:
        if isinstance(payload, dict):
            return normalize_whitespace(str(payload.get("text", "")))
        return normalize_whitespace(str(payload or ""))

    def _build_bosch_gallery_images(self, product: dict[str, Any], jsonld: dict[str, Any], title: str) -> list[GalleryImage]:
        urls: list[str] = []
        for image in (product.get("images") or []):
            image_url = self._build_bosch_media_url(image)
            if image_url:
                urls.append(image_url)
        images = jsonld.get("image")
        if isinstance(images, list):
            urls.extend(str(item) for item in images if item)
        elif isinstance(images, str) and images:
            urls.append(images)
        return [
            GalleryImage(url=image_url, alt=title, position=index)
            for index, image_url in enumerate(dedupe_urls_preserve_order(urls), start=1)
        ]

    def _build_bosch_media_url(self, media: Any, *, size: str = "") -> str:
        if not isinstance(media, dict):
            return ""
        direct_url = normalize_whitespace(str(media.get("url", "")))
        if direct_url:
            return direct_url
        media_id = normalize_whitespace(str(media.get("id", "")))
        media_type = normalize_whitespace(str(media.get("mediaType", "")))
        if not media_id or not media_type:
            return ""
        if media_type == "Feature_Icons" and size:
            return f"https://media3.bsh-group.com/{media_type}/{size}/{media_id}.webp"
        return f"https://media3.bsh-group.com/{media_type}/{media_id}.webp"

    def _build_bosch_presentation_source(self, product: dict[str, Any]) -> tuple[str, str]:
        blocks: list[str] = []
        text_parts: list[str] = []
        for highlight in (product.get("highlights") or []):
            if not isinstance(highlight, dict):
                continue
            title = self._localized_text(highlight.get("headline"))
            body = self._localized_text(highlight.get("text"))
            image_url = ""
            for image in highlight.get("images") or []:
                image_url = self._build_bosch_media_url(image)
                if image_url:
                    break
            if not title or not body:
                continue
            image_html = f'<img src="{image_url}" alt="{title}" />' if image_url else ""
            blocks.append(f"<section><h3>{title}</h3><p>{body}</p>{image_html}</section>")
            text_parts.append(f"{title} {body}")
        return "\n".join(blocks), normalize_whitespace(" ".join(text_parts))

    def _build_bosch_hero_summary(self, product: dict[str, Any], title: str) -> str:
        for highlight in (product.get("highlights") or []):
            if not isinstance(highlight, dict):
                continue
            text = self._localized_text(highlight.get("headline"))
            if text:
                return text
        return title

    def _nested_text(self, payload: dict[str, Any], path: list[str]) -> str:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return ""
            current = current.get(key)
        return normalize_whitespace(str(current or ""))

    def _bosch_specs_text(self, spec_sections: list[SpecSection]) -> str:
        return normalize_whitespace(
            " ".join(
                f"{item.label}: {item.value}"
                for section in spec_sections
                for item in section.items
                if item.label and item.value
            )
        )

    def _extract_canonical_url(self, soup: BeautifulSoup, url: str) -> str:
        link = soup.find("link", rel=lambda value: value and "canonical" in str(value).lower())
        if isinstance(link, Tag) and link.get("href"):
            return make_absolute_url(link["href"], url)
        return url

    def _extract_title(self, soup: BeautifulSoup) -> str:
        for selector in ["h1", "meta[property='og:title']", "title"]:
            node = soup.select_one(selector)
            if not isinstance(node, Tag):
                continue
            value = normalize_whitespace(node.get("content")) if selector.startswith("meta[") else safe_text(node)
            if selector == "title":
                value = normalize_whitespace(value.split(" - ", 1)[0])
            if value:
                return value
        return ""

    def _extract_json_item(self, soup: BeautifulSoup, *, title: str = "", canonical_url: str = "") -> dict[str, Any]:
        title_key = normalize_for_match(title)
        canonical_key = normalize_for_match(canonical_url)
        brand_hint = normalize_for_match(self._infer_brand_from_title(title))
        best_item: dict[str, Any] = {}
        best_score = -1

        for script in soup.select("script.json-item, script[type='application/ld+json']"):
            raw = script.string or script.get_text(" ", strip=True)
            raw = normalize_whitespace(raw)
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            candidate = self._normalize_json_item_payload(payload, canonical_url=canonical_url)
            if not candidate:
                continue
            item_name_key = normalize_for_match(str(candidate.get("item_name", "")))
            item_url_key = normalize_for_match(str(candidate.get("url", "")))
            item_brand_key = normalize_for_match(str(candidate.get("item_brand", "")))
            score = 0
            if title_key and item_name_key:
                if item_name_key == title_key:
                    score += 6
                elif title_key in item_name_key or item_name_key in title_key:
                    score += 4
            if canonical_key and item_url_key == canonical_key:
                score += 5
            if brand_hint and item_brand_key == brand_hint:
                score += 2
            if candidate.get("item_brand"):
                score += 1
            if candidate.get("price") not in {None, ""}:
                score += 1
            if score > best_score:
                best_item = candidate
                best_score = score
        return best_item

    def _normalize_json_item_payload(self, payload: Any, *, canonical_url: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}

        product = payload.get("product") if isinstance(payload.get("product"), dict) else {}
        variants = product.get("variants") if isinstance(product.get("variants"), list) else []
        first_variant = variants[0] if variants and isinstance(variants[0], dict) else {}

        item_name = (
            payload.get("item_name")
            or payload.get("name")
            or product.get("title")
            or payload.get("title")
        )
        item_brand = (
            payload.get("item_brand")
            or payload.get("vendor")
            or product.get("vendor")
            or payload.get("brand")
        )
        item_id = (
            payload.get("item_id")
            or payload.get("sku")
            or first_variant.get("sku")
            or product.get("id")
        )
        url = payload.get("url") or product.get("url") or canonical_url
        if url:
            url = make_absolute_url(str(url), canonical_url)

        price = payload.get("price")
        if price in {None, ""}:
            price = first_variant.get("price")
            if isinstance(price, int) and price >= 1000:
                price = price / 100

        candidate = {
            "item_name": normalize_whitespace(str(item_name or "")),
            "item_brand": normalize_whitespace(str(item_brand or "")),
            "item_id": normalize_whitespace(str(item_id or "")),
            "price": price,
            "url": normalize_whitespace(str(url or "")),
        }
        if not any(candidate.get(key) not in {None, ""} for key in ["item_name", "item_brand", "item_id", "price"]):
            return {}
        return candidate

    def _extract_product_code_from_scripts(self, html: str) -> str:
        match = re.search(r'"sku":"?([^",}]+)', html)
        if match:
            return normalize_whitespace(match.group(1))
        return ""

    def _extract_price(self, soup: BeautifulSoup, json_item: dict[str, Any]) -> tuple[str, float | None]:
        for selector in [".t-h3", "meta[property='og:price:amount']"]:
            node = soup.select_one(selector)
            if not isinstance(node, Tag):
                continue
            text = normalize_whitespace(node.get("content")) if selector.startswith("meta[") else safe_text(node)
            compact_numeric = text.replace(" ", "")
            if re.fullmatch(r"\d+(?:[.,]\d{1,2})?", compact_numeric):
                try:
                    return text, float(compact_numeric.replace(",", "."))
                except ValueError:
                    pass
            value = parse_euro_price(text)
            if value is not None:
                return text, value
        raw_price = json_item.get("price")
        if raw_price is not None:
            price_text = normalize_whitespace(str(raw_price))
            try:
                return price_text, float(str(raw_price).replace(",", "."))
            except ValueError:
                return price_text, None
        return "", None

    def _normalize_brand(self, value: str) -> str:
        normalized = normalize_for_match(value)
        if normalized == normalize_for_match("TEFAL"):
            return "Tefal"
        return normalize_whitespace(value)

    def _infer_brand_from_title(self, title: str) -> str:
        normalized = normalize_whitespace(title)
        if not normalized:
            return ""
        return normalized.split(" ", 1)[0]

    def _extract_gallery_images(self, soup: BeautifulSoup, base_url: str, fallback_alt: str) -> list[GalleryImage]:
        ordered_urls = dedupe_urls_preserve_order(
            [
                image_url
                for slide in soup.select("clrz-slider-product .product-slider-main .swiper-slide")
                for image_url in [self._extract_image_url(slide, base_url)]
                if image_url
            ]
        )
        out: list[GalleryImage] = []
        for position, image_url in enumerate(ordered_urls, start=1):
            out.append(GalleryImage(url=image_url, alt=fallback_alt, position=position))
        return out

    def _extract_image_url(self, container: Tag, base_url: str) -> str:
        for node in container.select("img, source"):
            raw = ""
            if node.name == "img":
                raw = node.get("src") or node.get("data-src") or ""
            if not raw:
                raw = self._pick_first_srcset_candidate(node.get("srcset", "") or node.get("data-srcset", ""))
            image_url = make_absolute_url(raw, base_url) if raw else ""
            if image_url:
                return image_url
        return ""

    def _pick_first_srcset_candidate(self, srcset: str) -> str:
        normalized = normalize_whitespace(srcset)
        if not normalized:
            return ""
        first = normalized.split(",", 1)[0].strip()
        return first.split(" ", 1)[0].strip()

    def _infer_tefal_family(self, title: str, url: str, hero_summary: str, presentation_source_text: str) -> str:
        haystack = normalize_for_match(" ".join([title, url, hero_summary, presentation_source_text]))
        if any(token in haystack for token in ["παγωτομηχαν", "pagotomichan"]):
            return "ice_cream_maker"
        if any(token in haystack for token in ["καφετιερ", "kafetier"]) and any(token in haystack for token in ["φιλτρ", "filtr"]):
            return "coffee_filter"
        if any(token in haystack for token in ["βραστηρ", "vrastir", "brasth"]):
            return "kettle"
        return ""

    def _build_taxonomy_fields(self, family_key: str) -> dict[str, str | list[str]]:
        if not family_key or family_key not in TEFAL_FAMILY_TAXONOMY:
            return {
                "breadcrumbs": [],
                "source_category": "",
                "match_type": "",
                "rule_id": "",
            }
        parent, leaf, sub = TEFAL_FAMILY_TAXONOMY[family_key]
        return {
            "breadcrumbs": build_breadcrumbs(parent, leaf, sub),
            "source_category": serialize_source_category(parent, leaf, [sub]),
            "match_type": "exact_category",
            "rule_id": f"manufacturer_tefal:{family_key}",
        }

    def _build_feature_sections(
        self,
        *,
        family_key: str,
        title: str,
        url: str,
        hero_summary: str,
        presentation_source_text: str,
        product_code: str,
    ) -> list[SpecSection]:
        combined_text = normalize_whitespace(" ".join([title, url, hero_summary, presentation_source_text]))
        sections: list[SpecSection] = []
        general_items: list[SpecItem] = []
        if product_code:
            general_items.append(SpecItem(label="Κωδικός Προϊόντος", value=product_code))
        warranty = self._extract_warranty(combined_text)
        if warranty:
            general_items.append(SpecItem(label="Εγγύηση Κατασκευαστή", value=warranty))
        if general_items:
            sections.append(SpecSection(section="Γενικά", items=self._dedupe_items(general_items)))

        if family_key == "ice_cream_maker":
            production_items: list[SpecItem] = []
            capacity = self._extract_liters(combined_text)
            if capacity:
                production_items.append(SpecItem(label="Χωρητικότητα", value=capacity))
            bowls = self._extract_count(combined_text, BOWLS_RE)
            if bowls:
                production_items.append(SpecItem(label="Αριθμός Δοχείων", value=bowls))
            programs = self._extract_count(combined_text, PROGRAMS_RE)
            if programs:
                production_items.append(SpecItem(label="Αριθμός Προγραμμάτων", value=programs))
            if normalize_for_match(combined_text).find("vegan") >= 0:
                production_items.append(SpecItem(label="Διατροφικές Επιλογές", value="Vegan"))
            if production_items:
                sections.append(SpecSection(section="Παραγωγή & Δυνατότητες", items=self._dedupe_items(production_items)))
            color = self._extract_color(title, url, combined_text)
            if color:
                sections.append(SpecSection(section="Σχεδιασμός & Εμφάνιση", items=[SpecItem(label="Χρώμα", value=color)]))

        if family_key == "coffee_filter":
            overview_items: list[SpecItem] = []
            power = self._extract_power(combined_text)
            if power:
                overview_items.append(SpecItem(label="Ισχύς σε Watts", value=power))
            liters = self._extract_liters(combined_text)
            if liters:
                overview_items.append(SpecItem(label="Χωρητικότητα Δοχείου Νερού σε Λίτρα", value=liters))
            cups = self._extract_cups(combined_text)
            if cups:
                overview_items.append(SpecItem(label="Χωρητικότητα σε Φλιτζάνια", value=cups))
            if overview_items:
                sections.append(SpecSection(section="Επισκόπηση Προϊόντος", items=self._dedupe_items(overview_items)))
            color = self._extract_color(title, url, combined_text)
            if color:
                sections.append(SpecSection(section="Γενικά Χαρακτηριστικά", items=[SpecItem(label="Χρώμα", value=color)]))

        if family_key == "kettle":
            overview_items = []
            liters = self._extract_liters(combined_text)
            if liters:
                overview_items.append(SpecItem(label="Χωρητικότητα σε Λίτρα", value=liters))
            power = self._extract_power(combined_text)
            if power:
                overview_items.append(SpecItem(label="Ισχύς", value=power))
            if overview_items:
                sections.append(SpecSection(section="Επισκόπηση Προϊόντος", items=self._dedupe_items(overview_items)))
            color = self._extract_color(title, url, combined_text)
            if color:
                sections.append(SpecSection(section="Γενικά Χαρακτηριστικά", items=[SpecItem(label="Χρώμα", value=color)]))

        return sections

    def _merge_sections(self, primary: list[SpecSection], secondary: list[SpecSection]) -> list[SpecSection]:
        merged = [SpecSection(section=section.section, items=list(section.items)) for section in primary]
        merged.extend(SpecSection(section=section.section, items=list(section.items)) for section in secondary if section.items)
        return [SpecSection(section=section.section, items=self._dedupe_items(section.items)) for section in merged if section.items]

    def _build_key_specs(self, spec_sections: list[SpecSection]) -> list[SpecItem]:
        items: list[SpecItem] = []
        seen: set[str] = set()
        for section in spec_sections:
            for item in section.items:
                label = normalize_for_match(item.label)
                value = normalize_whitespace(item.value)
                if not label or not value or label in seen:
                    continue
                seen.add(label)
                items.append(SpecItem(label=item.label, value=value))
                if len(items) >= 8:
                    return items
        return items

    def _extract_warranty(self, text: str) -> str:
        match = WARRANTY_RE.search(text)
        if not match:
            return ""
        years = match.group(1)
        return f"{years} Χρόνια" if years != "1" else "1 Χρόνος"

    def _extract_power(self, text: str) -> str:
        match = POWER_RE.search(text)
        if not match:
            return ""
        numeric = match.group(1).replace(".", ",")
        return f"{numeric} W"

    def _extract_liters(self, text: str) -> str:
        match = LITERS_RE.search(text)
        if not match:
            return ""
        numeric = match.group(1)
        return f"{numeric} lt"

    def _extract_count(self, text: str, pattern: re.Pattern[str]) -> str:
        match = pattern.search(text)
        if not match:
            return ""
        return normalize_whitespace(match.group(1))

    def _extract_cups(self, text: str) -> str:
        match = CUPS_RE.search(text)
        if not match:
            return ""
        numeric = normalize_whitespace(match.group(1)).replace(" - ", "-")
        return f"{numeric} Φλιτζάνια"

    def _extract_color(self, title: str, url: str, combined_text: str) -> str:
        haystacks = [normalize_for_match(title), normalize_for_match(url), normalize_for_match(combined_text)]
        color_map = [
            ("kafe", "Καφέ"),
            ("καφε", "Καφέ"),
            ("leyk", "Λευκό"),
            ("λευκ", "Λευκό"),
            ("mayr", "Μαύρο"),
            ("μαυρ", "Μαύρο"),
            ("inox", "Inox"),
            ("mpez", "Μπεζ"),
            ("μπεζ", "Μπεζ"),
            ("kokkin", "Κόκκινο"),
            ("red", "Κόκκινο"),
        ]
        for needle, value in color_map:
            if any(needle in haystack for haystack in haystacks):
                return value
        return ""

    def _dedupe_items(self, items: list[SpecItem]) -> list[SpecItem]:
        deduped: list[SpecItem] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            key = (normalize_for_match(item.label), normalize_for_match(item.value or ""))
            if not key[0] or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _collect_missing_fields(self, source: SourceProductData) -> list[str]:
        missing: list[str] = []
        has_specs = bool(source.spec_sections or source.manufacturer_spec_sections)
        if not source.product_code:
            missing.append("product_code")
        if not source.brand:
            missing.append("brand")
        if not source.name:
            missing.append("name")
        if source.price_value is None:
            missing.append("price")
        if not source.breadcrumbs:
            missing.append("breadcrumbs")
        if not source.hero_summary:
            missing.append("hero_summary")
        if not source.gallery_images:
            missing.append("gallery_images")
        if not has_specs:
            missing.append("spec_sections")
        return missing

    def _collect_critical_missing(self, source: SourceProductData) -> list[str]:
        critical: list[str] = []
        has_specs = bool(source.spec_sections or source.manufacturer_spec_sections)
        if not source.name:
            critical.append("name")
        if source.price_value is None:
            critical.append("price")
        if not source.breadcrumbs:
            critical.append("breadcrumbs")
        if not source.gallery_images:
            critical.append("gallery_images")
        if not has_specs:
            critical.append("spec_sections")
        return critical

    def _diagnostic(self, value: Any, selected_strategy: str, confidence: float) -> FieldDiagnostic:
        return FieldDiagnostic(
            confidence=round(confidence, 4),
            selected_strategy=selected_strategy,
            value_present=self._value_present(value),
            value_preview=self._preview_value(value),
            selector_trace=[],
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
            if not value:
                return ""
            first = value[0]
            if isinstance(first, SpecSection):
                return f"{len(value)} sections; first={first.section}"
            if isinstance(first, GalleryImage):
                return f"{len(value)} images; first={first.url}"
            if isinstance(first, SpecItem):
                return f"{len(value)} items; first={first.label}"
            return f"{len(value)} items"
        return normalize_whitespace(str(value))[:160]
