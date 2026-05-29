from __future__ import annotations

import json
import re
from html import escape, unescape
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
from .skroutz_taxonomy import classify_skroutz_taxonomy, normalize_category_href_slug
from .utils import utcnow_iso

BESTPRICE_ITEM_ID_RE = re.compile(r"/item/(\d+)/", re.IGNORECASE)


class BestPriceProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        jsonld_items = self._extract_jsonld_items(soup)
        product_json = self._find_jsonld_type(jsonld_items, "Product")
        breadcrumb_json = self._find_jsonld_type(jsonld_items, "BreadcrumbList")

        canonical_url = self._extract_canonical_url(soup, product_json, url)
        title, title_source = self._extract_title(soup, product_json)
        brand = self._extract_brand(product_json, title)
        product_code = self._extract_product_code(product_json, canonical_url)
        presentation_html, presentation_text = self._extract_presentation_source(
            soup, canonical_url
        )
        hero_summary = self._extract_summary(soup, presentation_text)
        price_text, price_value = self._extract_price(product_json)
        category_text, category_href, source_breadcrumbs = self._extract_category(
            breadcrumb_json, canonical_url
        )
        taxonomy_hint = classify_skroutz_taxonomy(
            category_tag_text=category_text,
            category_tag_href=category_href,
            title=title,
            url=canonical_url,
            brand=brand,
        )
        breadcrumbs = clean_breadcrumbs(
            taxonomy_hint.breadcrumbs
            if taxonomy_hint and not taxonomy_hint.ambiguous
            else source_breadcrumbs
        )
        spec_items = self._extract_specs(soup, product_json, brand)
        spec_sections = (
            [SpecSection(section="Χαρακτηριστικά", items=spec_items)]
            if spec_items
            else []
        )
        key_specs = spec_items[:8]
        gallery_images = self._extract_gallery_images(
            soup, product_json, canonical_url, title
        )

        source = SourceProductData(
            source_name="bestprice",
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=breadcrumbs,
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
            name=title,
            hero_summary=hero_summary,
            price_text=price_text,
            price_value=price_value,
            gallery_images=gallery_images,
            key_specs=key_specs,
            spec_sections=spec_sections,
            presentation_source_html=presentation_html,
            presentation_source_text=presentation_text or hero_summary,
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
        )
        missing_fields = self._collect_missing_fields(source)
        critical_missing = self._collect_critical_missing(source)
        provenance = {
            "name": title_source,
            "brand": "jsonld.brand" if brand else "missing",
            "breadcrumbs": (
                "taxonomy_hint"
                if taxonomy_hint and taxonomy_hint.breadcrumbs
                else "jsonld.breadcrumb"
            ),
            "gallery_images": (
                "dom:#item-image-gallery/jsonld.image/meta.og:image"
                if gallery_images
                else "missing"
            ),
            "spec_sections": (
                "jsonld.additionalProperty" if spec_sections else "missing"
            ),
            "hero_summary": self._summary_source(soup, presentation_text, hero_summary),
            "presentation_blocks": (
                "dom:#item-content .content-block"
                if presentation_html
                else "missing"
            ),
        }
        diagnostics = {
            key: self._make_diagnostic(getattr(source, field), strategy)
            for key, field, strategy in [
                ("name", "name", provenance["name"]),
                ("brand", "brand", provenance["brand"]),
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
        warnings = (
            ["bestprice_taxonomy_ambiguous:" + taxonomy_hint.escalation_reason]
            if taxonomy_hint and taxonomy_hint.ambiguous
            else []
        )
        if source_breadcrumbs and taxonomy_hint and taxonomy_hint.breadcrumbs:
            warnings.append("bestprice_source_breadcrumbs_mapped")

        return ParsedProduct(
            source=source,
            provenance=provenance,
            field_diagnostics=diagnostics,
            missing_fields=missing_fields,
            warnings=warnings,
            critical_missing=critical_missing,
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
            out.extend(item for item in graph if isinstance(item, dict))
        return out

    def _find_jsonld_type(
        self, items: list[dict[str, Any]], type_name: str
    ) -> dict[str, Any]:
        for item in items:
            raw_type = item.get("@type")
            if raw_type == type_name or (
                isinstance(raw_type, list) and type_name in raw_type
            ):
                return item
        return {}

    def _extract_canonical_url(
        self, soup: BeautifulSoup, product_json: dict[str, Any], fallback_url: str
    ) -> str:
        canonical = normalize_whitespace(str(product_json.get("url") or ""))
        if not canonical:
            node = soup.select_one("link[rel='canonical']")
            canonical = normalize_whitespace(node.get("href", "") if node else "")
        return make_absolute_url(canonical or fallback_url, fallback_url)

    def _extract_title(
        self, soup: BeautifulSoup, product_json: dict[str, Any]
    ) -> tuple[str, str]:
        title = normalize_whitespace(str(product_json.get("name") or ""))
        if title:
            return title, "jsonld.name"
        node = soup.select_one("h1.item-title, h1")
        if node is not None:
            return safe_text(node), "h1"
        return "", "missing"

    def _extract_brand(self, product_json: dict[str, Any], title: str) -> str:
        raw_brand = product_json.get("brand")
        if isinstance(raw_brand, dict):
            brand = normalize_whitespace(str(raw_brand.get("name") or ""))
        else:
            brand = normalize_whitespace(str(raw_brand or ""))
        if brand:
            return brand
        manufacturer = normalize_whitespace(str(product_json.get("manufacturer") or ""))
        if manufacturer:
            return manufacturer
        return normalize_whitespace(title.split(" ", 1)[0]) if title else ""

    def _extract_product_code(self, product_json: dict[str, Any], url: str) -> str:
        sku = normalize_whitespace(str(product_json.get("sku") or ""))
        if sku:
            return sku
        match = BESTPRICE_ITEM_ID_RE.search(url)
        return match.group(1) if match else ""

    def _extract_summary(self, soup: BeautifulSoup, presentation_text: str = "") -> str:
        node = soup.select_one(".item-description")
        if node is not None:
            summary = safe_text(node)
            if summary:
                return summary
        insight = soup.select_one(".item-insights__summary p")
        if insight is not None:
            summary = safe_text(insight)
            if summary:
                return summary
        if presentation_text:
            first_line = normalize_whitespace(presentation_text.splitlines()[-1])
            if first_line:
                return first_line
        meta = soup.select_one("meta[itemprop='description']")
        summary = normalize_whitespace(meta.get("content", "") if meta else "")
        if summary:
            return summary
        meta = soup.select_one("meta[name='description']")
        return normalize_whitespace(meta.get("content", "") if meta else "")

    def _summary_source(
        self, soup: BeautifulSoup, presentation_text: str, hero_summary: str
    ) -> str:
        if not hero_summary:
            return "missing"
        if soup.select_one(".item-description") is not None:
            return "dom:.item-description"
        if soup.select_one(".item-insights__summary p") is not None:
            return "dom:.item-insights__summary"
        if presentation_text:
            return "dom:#item-content .content-block"
        if soup.select_one("meta[itemprop='description']") is not None:
            return "meta.itemprop.description"
        return "meta.description"

    def _extract_price(self, product_json: dict[str, Any]) -> tuple[str, float | None]:
        offers = product_json.get("offers")
        price = ""
        if isinstance(offers, dict):
            price = normalize_whitespace(
                str(offers.get("lowPrice") or offers.get("price") or "")
            )
        if not price:
            return "", None
        price_text = f"{price} €"
        return price_text, parse_euro_price(price_text)

    def _extract_category(
        self, breadcrumb_json: dict[str, Any], base_url: str
    ) -> tuple[str, str, list[str]]:
        crumbs: list[str] = ["Αρχική"]
        href = ""
        for entry in (
            breadcrumb_json.get("itemListElement", [])
            if isinstance(breadcrumb_json.get("itemListElement"), list)
            else []
        ):
            item = entry.get("item") if isinstance(entry, dict) else None
            if not isinstance(item, dict):
                continue
            name = normalize_whitespace(str(item.get("name") or ""))
            if name:
                crumbs.append(name)
            raw_href = normalize_whitespace(
                str(item.get("@id") or item.get("url") or "")
            )
            if raw_href:
                href = make_absolute_url(raw_href, base_url)
        return (crumbs[-1] if len(crumbs) > 1 else "", href, clean_breadcrumbs(crumbs))

    def _extract_specs(
        self, soup: BeautifulSoup, product_json: dict[str, Any], brand: str
    ) -> list[SpecItem]:
        items: list[SpecItem] = []
        if brand:
            items.append(SpecItem(label="Κατασκευαστής", value=brand))
        seen = {normalize_for_match("Κατασκευαστής")} if brand else set()
        raw_properties = product_json.get("additionalProperty")
        if isinstance(raw_properties, list):
            for prop in raw_properties:
                if not isinstance(prop, dict):
                    continue
                label = normalize_whitespace(str(prop.get("name") or ""))
                value = normalize_whitespace(str(prop.get("value") or ""))
                key = normalize_for_match(label)
                if not label or not value or key in seen:
                    continue
                seen.add(key)
                items.append(SpecItem(label=label, value=value))
        for item in self._extract_visible_specs(soup):
            label = item.label
            value = item.value
            key = normalize_for_match(label)
            if not label or not value or key in seen:
                continue
            seen.add(key)
            items.append(SpecItem(label=label, value=value))
        return items

    def _extract_visible_specs(self, soup: BeautifulSoup) -> list[SpecItem]:
        items: list[SpecItem] = []
        for node in soup.select(".item-header__specs-list li div"):
            text = safe_text(node)
            if ":" not in text:
                continue
            label, value = text.split(":", 1)
            label = normalize_whitespace(label)
            value = normalize_whitespace(value)
            if label and value:
                items.append(SpecItem(label=label, value=value))
        for node in soup.select("#item-specs dl"):
            label_node = node.select_one("dt")
            value_node = node.select_one("dd")
            label = safe_text(label_node) if label_node is not None else ""
            value = safe_text(value_node) if value_node is not None else ""
            if label and value:
                items.append(SpecItem(label=label, value=value))
        return items

    def _extract_presentation_source(
        self, soup: BeautifulSoup, base_url: str
    ) -> tuple[str, str]:
        blocks: list[dict[str, str]] = []
        for block in soup.select("#item-content .content-block"):
            title_node = block.select_one(".content-block__header, h2, h3, h4")
            body_node = block.select_one(".content-block__body")
            image_node = block.select_one("img")
            title = safe_text(title_node) if title_node is not None else ""
            paragraph = (
                normalize_whitespace(body_node.get_text(" ", strip=True))
                if body_node is not None
                else ""
            )
            if not paragraph:
                paragraph = " ".join(
                    normalize_whitespace(node.get_text(" ", strip=True))
                    for node in block.select("p")
                    if normalize_whitespace(node.get_text(" ", strip=True))
                )
            image_url = ""
            if image_node is not None:
                image_url = normalize_whitespace(
                    str(
                        image_node.get("src")
                        or image_node.get("data-src")
                        or image_node.get("data-original")
                        or ""
                    )
                )
            if title and paragraph:
                blocks.append(
                    {
                        "title": title,
                        "paragraph": normalize_whitespace(paragraph),
                        "image_url": (
                            make_absolute_url(image_url, base_url) if image_url else ""
                        ),
                    }
                )

        html_parts: list[str] = []
        text_parts: list[str] = []
        for block in blocks:
            title = normalize_whitespace(block["title"])
            paragraph = normalize_whitespace(block["paragraph"])
            if not title or not paragraph:
                continue
            html_parts.append('<section class="ck-text inline">')
            image_url = normalize_whitespace(block.get("image_url", ""))
            if image_url:
                html_parts.append(
                    f'<img src="{escape(image_url, quote=True)}" '
                    f'alt="{escape(title, quote=True)}">'
                )
            html_parts.append(f"<h3>{escape(title)}</h3>")
            html_parts.append(f"<p>{escape(paragraph)}</p>")
            html_parts.append("</section>")
            text_parts.append(f"{title}\n{paragraph}")
        return "".join(html_parts), "\n\n".join(text_parts)

    def _extract_gallery_images(
        self,
        soup: BeautifulSoup,
        product_json: dict[str, Any],
        base_url: str,
        title: str,
    ) -> list[GalleryImage]:
        urls: list[str] = self._extract_gallery_dom_urls(soup, base_url)
        raw_images = product_json.get("image")
        if not urls:
            if isinstance(raw_images, str):
                urls.append(raw_images)
            elif isinstance(raw_images, list):
                urls.extend(str(item) for item in raw_images if item)
            meta = soup.select_one("meta[property='og:image']")
            if meta is not None:
                urls.append(str(meta.get("content") or ""))
        image_urls = dedupe_urls_preserve_order(
            [make_absolute_url(url, base_url) for url in urls]
        )
        return [
            GalleryImage(url=image_url, alt=title, position=index)
            for index, image_url in enumerate(image_urls, start=1)
        ]

    def _extract_gallery_dom_urls(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        urls: list[str] = []
        for link in soup.select("#item-image-gallery a[href]"):
            href = normalize_whitespace(str(link.get("href") or ""))
            if href:
                urls.append(make_absolute_url(href, base_url))

        if urls:
            return dedupe_urls_preserve_order(urls)

        data_node = soup.select_one(
            "#item-image-gallery[data-items], .item-image__dots[data-items]"
        )
        raw_items = (
            str(data_node.get("data-items") or "") if data_node is not None else ""
        )
        if raw_items:
            page = self._extract_bp_page_data(soup)
            slug = normalize_whitespace(str(page.get("slug") or ""))
            try:
                items = json.loads(unescape(raw_items))
            except json.JSONDecodeError:
                items = []
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    path = normalize_whitespace(
                        str(item.get("path") or item.get("p") or "")
                    )
                    if not path or not slug:
                        continue
                    urls.append(
                        make_absolute_url(
                            f"https://bbpcdn.pstatic.gr/{path.strip('/')}/{slug}.webp",
                            base_url,
                        )
                    )

        return dedupe_urls_preserve_order(urls)

    def _extract_bp_page_data(self, soup: BeautifulSoup) -> dict[str, Any]:
        node = soup.select_one("script#bp-data[type='application/json']")
        raw = ""
        if node is not None:
            raw = node.string or node.get_text()
        if not normalize_whitespace(raw):
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        page = payload.get("PAGE") if isinstance(payload, dict) else None
        return page if isinstance(page, dict) else {}

    def _collect_missing_fields(self, source: SourceProductData) -> list[str]:
        missing: list[str] = []
        if not source.name:
            missing.append("name")
        if not source.brand:
            missing.append("brand")
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
        critical = [
            field
            for field in [
                "name",
                "brand",
                "breadcrumbs",
                "gallery_images",
                "spec_sections",
            ]
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
