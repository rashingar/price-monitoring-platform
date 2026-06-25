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
    parse_euro_price,
    safe_text,
)
from .utils import utcnow_iso


WASHER_TAXONOMY_SOURCE_CATEGORY = (
    "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ:::"
    "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ///Πλυντήρια-Στεγνωτήρια:::"
    "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ///Πλυντήρια-Στεγνωτήρια///Πλυντήρια Ρούχων"
)


class GuarantyProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        jsonld = self._extract_jsonld_items(soup)
        product_json = self._find_jsonld_type(jsonld, "Product")
        canonical_url = self._extract_canonical_url(soup, product_json, url)
        title = self._extract_title(soup, product_json)
        brand = self._extract_brand(soup, product_json, title)
        mpn = self._extract_mpn(soup, product_json, title)
        product_code = self._extract_product_code(soup, product_json, canonical_url)
        description = self._extract_description(soup, product_json)
        breadcrumbs = clean_breadcrumbs(self._extract_breadcrumbs(soup, jsonld))
        breadcrumbs = self._with_taxonomy_hints(breadcrumbs, title=title, url=url)
        spec_items = self._extract_spec_items(
            soup=soup,
            product_json=product_json,
            title=title,
            brand=brand,
            mpn=mpn,
            description=description,
        )
        gallery_images = self._extract_gallery_images(
            soup, product_json, canonical_url, title
        )
        price_text, price_value = self._extract_price(soup, product_json)
        category_text = self._extract_category(product_json, breadcrumbs, title=title, url=url)

        source = SourceProductData(
            source_name="guaranty",
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=breadcrumbs,
            category_tag_text=category_text,
            taxonomy_source_category=(
                WASHER_TAXONOMY_SOURCE_CATEGORY
                if self._looks_like_washing_machine(title=title, url=url)
                else category_text
            ),
            product_code=product_code,
            brand=brand,
            mpn=mpn,
            name=title,
            hero_summary=description,
            price_text=price_text,
            price_value=price_value,
            gallery_images=gallery_images,
            key_specs=spec_items[:10],
            spec_sections=(
                [SpecSection(section="Χαρακτηριστικά", items=spec_items)]
                if spec_items
                else []
            ),
            presentation_source_text=description,
            presentation_source_html=str(
                soup.select_one("#tab-description, .product-description, .description")
                or ""
            ),
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
        )
        provenance = {
            "name": "dom:h1/jsonld.name/meta:og:title" if title else "missing",
            "brand": "dom:manufacturer/jsonld.brand/title" if brand else "missing",
            "mpn": "jsonld.sku/mpn/title" if mpn else "missing",
            "product_code": "dom:product-code/url" if product_code else "missing",
            "breadcrumbs": "jsonld:BreadcrumbList/dom:breadcrumb/taxonomy_hint"
            if breadcrumbs
            else "missing",
            "gallery_images": "jsonld.image/dom:product-gallery/meta:og:image"
            if gallery_images
            else "missing",
            "spec_sections": "jsonld.additionalProperty/dom:spec_tables/inference"
            if spec_items
            else "missing",
            "hero_summary": "meta:description/jsonld.description/dom:description"
            if description
            else "missing",
            "presentation_blocks": "not_applicable:guaranty_no_sections",
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
        warnings = [] if gallery_images else ["gallery_images_missing"]
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
            node = soup.find("link", rel=lambda value: value and "canonical" in value.lower())
            canonical = normalize_whitespace(node.get("href", "") if node else "")
        return make_absolute_url(canonical or fallback_url, fallback_url)

    def _extract_title(self, soup: BeautifulSoup, product_json: dict[str, Any]) -> str:
        for selector in ("h1", ".pageHeading", ".product-title", ".product-info h2"):
            title = safe_text(soup.select_one(selector))
            if title:
                return title
        title = normalize_whitespace(str(product_json.get("name") or ""))
        if title:
            return title
        meta = soup.select_one("meta[property='og:title']")
        title = normalize_whitespace(meta.get("content", "") if meta else "")
        return title.split("|", 1)[0].strip()

    def _extract_brand(
        self, soup: BeautifulSoup, product_json: dict[str, Any], title: str
    ) -> str:
        for selector in (
            "[itemprop='brand']",
            ".psum p a[href*='/manufacturer/']",
            ".manufacturer a",
            ".brand a",
            ".product-manufacturer a",
        ):
            brand = safe_text(soup.select_one(selector))
            if brand:
                return brand
        raw_brand = product_json.get("brand")
        if isinstance(raw_brand, dict):
            brand = normalize_whitespace(str(raw_brand.get("name") or ""))
        else:
            brand = normalize_whitespace(str(raw_brand or ""))
        return brand or (normalize_whitespace(title.split(" ", 1)[0]) if title else "")

    def _extract_mpn(
        self, soup: BeautifulSoup, product_json: dict[str, Any], title: str
    ) -> str:
        for key in ("mpn", "sku", "model"):
            value = normalize_whitespace(str(product_json.get(key) or ""))
            if value:
                return value
        text = " ".join(
            safe_text(node)
            for node in soup.select("[itemprop='mpn'], [itemprop='sku'], .model, .sku")
        )
        evidence = f"{text} {title}"
        candidates = re.findall(
            r"\b(?=[A-Z0-9/-]*[A-Z])(?=[A-Z0-9/-]*\d)[A-Z0-9][A-Z0-9/-]{3,}\b",
            evidence,
        )
        for candidate in candidates:
            if not candidate.isdigit():
                return candidate
        return ""

    def _extract_product_code(
        self, soup: BeautifulSoup, product_json: dict[str, Any], canonical_url: str
    ) -> str:
        for selector in (
            ".product-code",
            ".product_model",
            "#product_model",
            "[itemprop='productID']",
        ):
            text = safe_text(soup.select_one(selector))
            match = re.search(r"\b\d{6,}\b", text)
            if match:
                return match.group(0)
        for key in ("productID", "productId"):
            value = normalize_whitespace(str(product_json.get(key) or ""))
            if value:
                return value
        match = re.search(r"/product/(\d+)/", canonical_url)
        return f"100{match.group(1)}" if match else ""

    def _extract_description(
        self, soup: BeautifulSoup, product_json: dict[str, Any]
    ) -> str:
        for raw in (product_json.get("description"),):
            text = normalize_whitespace(str(raw or ""))
            if text:
                return text
        for selector, attr in [
            ("meta[name='description']", "content"),
            ("meta[property='og:description']", "content"),
            (".short_desc", None),
            (".tabcontent.inpagecontent[rel='desc'] p", None),
            ("#tab-description", None),
            (".product-description", None),
            (".description", None),
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
        for item in jsonld:
            raw_type = item.get("@type")
            if raw_type != "BreadcrumbList":
                continue
            values = []
            for element in item.get("itemListElement", []):
                if not isinstance(element, dict):
                    continue
                nested = element.get("item")
                if isinstance(nested, dict):
                    values.append(normalize_whitespace(str(nested.get("name") or "")))
                else:
                    values.append(normalize_whitespace(str(element.get("name") or "")))
            if values:
                return [value for value in values if self._is_useful_breadcrumb(value)]
        values = [
            safe_text(node)
            for node in soup.select(
                ".breadcrumb a, .breadcrumbs a, nav[aria-label='breadcrumb'] a"
            )
            if safe_text(node)
        ]
        return [value for value in values if self._is_useful_breadcrumb(value)]

    def _is_useful_breadcrumb(self, value: str) -> bool:
        key = normalize_for_match(value)
        return bool(key) and key not in {
            normalize_for_match("Αρχική"),
            normalize_for_match("Αρχική σελίδα"),
            "home",
        }

    def _with_taxonomy_hints(
        self, breadcrumbs: list[str], *, title: str, url: str
    ) -> list[str]:
        if not self._looks_like_washing_machine(title=title, url=url):
            return breadcrumbs
        out: list[str] = []
        for value in [
            *breadcrumbs,
            "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            "Πλυντήρια-Στεγνωτήρια",
            "Πλυντήρια Ρούχων",
        ]:
            key = normalize_for_match(value)
            if key and key not in {normalize_for_match(item) for item in out}:
                out.append(value)
        return out

    def _extract_spec_items(
        self,
        *,
        soup: BeautifulSoup,
        product_json: dict[str, Any],
        title: str,
        brand: str,
        mpn: str,
        description: str,
    ) -> list[SpecItem]:
        items: list[SpecItem] = []
        if brand:
            items.append(SpecItem("Κατασκευαστής", brand))
        if mpn:
            items.append(SpecItem("MPN", mpn))
        properties = product_json.get("additionalProperty")
        if isinstance(properties, list):
            for prop in properties:
                if not isinstance(prop, dict):
                    continue
                label = self._normalize_spec_label(str(prop.get("name") or ""))
                value = self._normalize_spec_value(str(prop.get("value") or ""))
                if label and value:
                    items.append(SpecItem(label=label, value=value))
        for label, value in self._extract_dom_spec_pairs(soup):
            label = self._normalize_spec_label(label)
            value = self._normalize_spec_value(value)
            if label and value:
                items.append(SpecItem(label=label, value=value))
        items.extend(self._infer_washer_specs(title=title, description=description))
        items.extend(self._derive_washer_template_specs(items))
        return self._dedupe_spec_items(items)

    def _extract_dom_spec_pairs(self, soup: BeautifulSoup) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        product_scope = soup.select_one(".newproductpage") or soup
        for item in product_scope.select(".psum p"):
            strong = item.find("strong")
            if not strong:
                continue
            label = safe_text(strong)
            value = normalize_whitespace(item.get_text(" ", strip=True))
            strong_text = safe_text(strong)
            if value.startswith(strong_text):
                value = value[len(strong_text) :]
            value = normalize_whitespace(value.strip(" :"))
            if label and value:
                pairs.append((label, value))
        description_scope = product_scope.select_one(".tabcontent.inpagecontent[rel='desc']")
        technical_items = self._technical_spec_list_items(description_scope)
        for item in technical_items:
            strong = item.find("strong")
            if not strong:
                continue
            label = safe_text(strong)
            value = normalize_whitespace(item.get_text(" ", strip=True))
            strong_text = safe_text(strong)
            if value.startswith(strong_text):
                value = value[len(strong_text) :]
            value = normalize_whitespace(value.strip(" :"))
            if label and value:
                pairs.append((label, value))
        for row in product_scope.select(
            "#tab-specification tr, .specifications tr, .product-specs tr, "
            ".table-specs tr"
        ):
            cells = [safe_text(cell) for cell in row.find_all(["th", "td"])]
            if len(cells) >= 2:
                pairs.append((cells[0], cells[1]))
        for row in product_scope.select(".specification, .product-attribute, .attribute"):
            label = safe_text(row.select_one(".name, .label, dt"))
            value = safe_text(row.select_one(".value, dd"))
            if label and value:
                pairs.append((label, value))
        for item in product_scope.select("#tab-description li, .product-description li, .description li"):
            text = safe_text(item)
            if ":" in text:
                label, value = text.split(":", 1)
                pairs.append((label, value))
        return pairs

    def _technical_spec_list_items(self, description_scope: Any) -> list[Any]:
        if description_scope is None:
            return []
        marker = None
        for heading in description_scope.find_all(["h3", "h4"]):
            if "πληρη τεχνικα χαρακτηριστικα" in normalize_for_match(safe_text(heading)):
                marker = heading
                break
        if marker is None:
            return list(description_scope.select("li"))
        items: list[Any] = []
        for sibling in marker.find_next_siblings():
            if hasattr(sibling, "select"):
                items.extend(sibling.select("li"))
        return items

    def _normalize_spec_label(self, label: str) -> str:
        cleaned = normalize_whitespace(label).strip(" :")
        key = normalize_for_match(cleaned)
        aliases = {
            "brand": "Κατασκευαστής",
            "manufacturer": "Κατασκευαστής",
            normalize_for_match("Κατασκευαστής"): "Κατασκευαστής",
            normalize_for_match("Μάρκα"): "Κατασκευαστής",
            "model": "MPN",
            normalize_for_match("Μοντέλο"): "MPN",
            normalize_for_match("Κωδικός"): "MPN",
            normalize_for_match("Τύπος Συσκευής"): "Τύπος Συσκευής",
            normalize_for_match("Χωρητικότητα Κάδου"): "Χωρητικότητα Πλύσης",
            normalize_for_match("Χωρητικότητα"): "Χωρητικότητα Πλύσης",
            normalize_for_match("Χωρητικότητα Πλύσης"): "Χωρητικότητα Πλύσης",
            normalize_for_match("Μέγιστη Ταχύτητα Στιψίματος"): "Μέγιστες Στροφές Στυψίματος",
            normalize_for_match("Στροφές"): "Μέγιστες Στροφές Στυψίματος",
            normalize_for_match("Ενεργειακή Κλάση"): "Ενεργειακή Κλάση",
            normalize_for_match("Νέα Ενεργειακή Κλάση"): "Ενεργειακή Κλάση",
            normalize_for_match("Τύπος Φόρτωσης"): "Τύπος Φόρτωσης",
        }
        aliases.update(
            {
                normalize_for_match("Τύπος Συσκευής"): "Τύπος Συσκευής",
                normalize_for_match("Χωρητικότητα Κάδου"): "Χωρητικότητα Πλύσης",
                normalize_for_match("Μέγιστη Ταχύτητα Στιψίματος"): "Μέγιστες Στροφές Στυψίματος",
                normalize_for_match("Δείκτης Απόδοσης Στιψίματος"): "Κλάση Απόδοσης Στυψίματος",
                normalize_for_match("Επίπεδο Θορύβου (κατά το στύψιμο)"): "Επίπεδο Θορύβου Πλυσίματος σε dB",
                normalize_for_match("Επίπεδο Θορύβου (κατά το στίψιμο)"): "Επίπεδο Θορύβου Πλυσίματος σε dB",
                normalize_for_match("Διαστάσεις Συσκευής (Υ x Π x Β)"): "Διαστάσεις Συσκευής σε Εκατοστά (Υ × Π × Β)",
                normalize_for_match("Εγγύηση"): "Εγγύηση Κατασκευαστή",
                normalize_for_match("Ειδικές Επιλογές"): "Ειδικές Επιλογές",
                normalize_for_match("Ασφάλεια"): "Ηλεκτρική Ασφάλεια Παροχής",
            }
        )
        return aliases.get(key, cleaned)

    def _normalize_spec_value(self, value: str) -> str:
        cleaned = normalize_whitespace(value).strip(" :")
        cleaned = re.sub(r"(?<=\d),\s+(?=\d)", ",", cleaned)
        cleaned = re.sub(r"\b(\d+)[,.]0\s*kg\b", r"\1 kg", cleaned, flags=re.I)
        return cleaned

    def _infer_washer_specs(self, *, title: str, description: str) -> list[SpecItem]:
        if not self._looks_like_washing_machine(title=title, url=""):
            return []
        evidence = normalize_whitespace(f"{title} {description}")
        items = [SpecItem("Τύπος Συσκευής", "Πλυντήριο Ρούχων")]
        if any(
            token in normalize_for_match(evidence)
            for token in (normalize_for_match("Άνω Φόρτωσης"), "top loader", "top load")
        ):
            items.append(SpecItem("Τύπος Φόρτωσης", "Άνω"))
        capacity = re.search(r"\b(\d+(?:[,.]\d+)?)\s*kg\b", evidence, re.I)
        if capacity:
            items.append(
                SpecItem("Χωρητικότητα Πλύσης", f"{capacity.group(1).replace(',', '.')}kg")
            )
        spin = re.search(r"\b(1[0-9]{3})\s*(?:rpm|στροφ)", evidence, re.I)
        if spin:
            items.append(SpecItem("Μέγιστες Στροφές Στυψίματος", f"{spin.group(1)}rpm"))
        energy = re.search(
            r"ενεργειακ[ήη]\s+κλάση\s*([A-G](?:\+{1,3})?)", evidence, re.I
        )
        if energy:
            items.append(SpecItem("Ενεργειακή Κλάση", energy.group(1).upper()))
        return items

    def _derive_washer_template_specs(self, items: list[SpecItem]) -> list[SpecItem]:
        values: dict[str, str] = {}
        for item in items:
            values.setdefault(normalize_for_match(item.label), item.value)
        derived: list[SpecItem] = []
        device_type = values.get(normalize_for_match("Τύπος Συσκευής"), "")
        if any(
            token in normalize_for_match(device_type)
            for token in (normalize_for_match("Άνω Φόρτωσης"), "top loader")
        ):
            derived.append(SpecItem("Τρόπος Φόρτωσης Πλυντηρίου", "Άνω"))

        special_options = values.get(normalize_for_match("Ειδικές Επιλογές"), "")
        special_key = normalize_for_match(special_options)
        if normalize_for_match("Πρόπλυση") in special_key:
            derived.append(SpecItem("Πρόπλυσης", "Ναι"))
        if normalize_for_match("Επιπλέον Ξέβγαλμα") in special_key or "rinse+" in special_key:
            derived.append(SpecItem("Επιπλέον Ξεβγάλματος", "Ναι"))
        if normalize_for_match("Ρύθμιση Στροφών") in special_key:
            derived.append(SpecItem("Στροφών", "Ναι"))
        if normalize_for_match("Ρύθμιση Θερμοκρασίας") in special_key:
            derived.append(SpecItem("Θερμοκρασιών", "Ναι"))

        display = values.get(normalize_for_match("Τύπος Οθόνης"), "")
        if display:
            derived.append(SpecItem("Ενδείξεις Λειτουργίας", display))

        systems = values.get(normalize_for_match("Συστήματα Ασφαλείας"), "")
        systems_key = normalize_for_match(systems)
        if "child lock" in systems_key or normalize_for_match("Κλείδωμα ασφαλείας για παιδιά") in systems_key:
            derived.append(SpecItem("Κλείδωμα Ασφαλείας για Παιδιά", "Ναι"))

        delay = values.get(normalize_for_match("Καθυστέρηση Έναρξης έως 24 Ώρες"), "")
        if delay:
            derived.append(SpecItem("Προγραμματισμός Έναρξης", "έως 24 ώρες"))

        dimensions = values.get(
            normalize_for_match("Διαστάσεις Συσκευής σε Εκατοστά (Υ × Π × Β)"), ""
        )
        match = re.search(
            r"(\d+(?:[,.]\d+)?)\s*x\s*(\d+(?:[,.]\d+)?)\s*x\s*(\d+(?:[,.]\d+)?)",
            dimensions,
            re.I,
        )
        if match:
            derived.append(SpecItem("Πλάτος Συσκευής σε Εκατοστά", f"{match.group(2)} cm"))
            derived.append(SpecItem("Βάθος Συσκευής σε Εκατοστά", f"{match.group(3)} cm"))
        return derived

    def _extract_gallery_images(
        self,
        soup: BeautifulSoup,
        product_json: dict[str, Any],
        base_url: str,
        title: str,
    ) -> list[GalleryImage]:
        candidates: list[str] = []
        raw_images = product_json.get("image")
        if isinstance(raw_images, list):
            for image in raw_images:
                candidates.append(str(image.get("url") if isinstance(image, dict) else image))
        elif raw_images:
            candidates.append(str(raw_images))
        for anchor in soup.select(".zoom-gallery a[href], .pimg a[href], .gadg_pic a[href]"):
            href = normalize_whitespace(str(anchor.get("href") or ""))
            if href:
                candidates.append(href)
        for selector in (
            ".product-image img",
            ".product-gallery img",
            ".thumbnails img",
            ".pimg img",
            "#content img",
        ):
            for img in soup.select(selector):
                for attr in ("data-largeimg", "data-large_image", "data-src", "src"):
                    value = normalize_whitespace(str(img.get(attr) or ""))
                    if value:
                        candidates.append(value)
                        break
        meta = soup.select_one("meta[property='og:image']")
        if meta and meta.get("content"):
            candidates.append(str(meta.get("content")))
        urls = [
            make_absolute_url(
                f"/{candidate}"
                if candidate.startswith(("images/", "thumbnails/"))
                else candidate,
                base_url,
            )
            for candidate in candidates
            if normalize_whitespace(candidate)
            and "placeholder" not in normalize_for_match(candidate)
            and "thumbnails/" not in normalize_for_match(candidate)
            and "thumbnails/" not in candidate.lower()
        ]
        return [
            GalleryImage(url=image_url, alt=title, position=index)
            for index, image_url in enumerate(dedupe_urls_preserve_order(urls), start=1)
        ]

    def _extract_price(
        self, soup: BeautifulSoup, product_json: dict[str, Any]
    ) -> tuple[str, float | None]:
        offers = product_json.get("offers") if isinstance(product_json, dict) else {}
        if isinstance(offers, dict):
            raw_price = normalize_whitespace(str(offers.get("price") or ""))
            if raw_price:
                return raw_price, parse_euro_price(raw_price) or float(raw_price.replace(",", "."))
        for selector in (
            "meta[property='product:price:amount']",
            "[itemprop='price']",
            ".sale_price > span",
            ".new_num_price .sale_price > span",
            ".newpricebox",
            ".new_num_price",
            ".price",
            ".product-price",
        ):
            node = soup.select_one(selector)
            text = normalize_whitespace(str(node.get("content") or "")) if node and node.get("content") else safe_text(node)
            if parse_euro_price(text) is not None:
                return text, parse_euro_price(text)
        return "", None

    def _extract_category(
        self,
        product_json: dict[str, Any],
        breadcrumbs: list[str],
        *,
        title: str,
        url: str,
    ) -> str:
        if self._looks_like_washing_machine(title=title, url=url):
            return "Πλυντήρια Ρούχων"
        category = normalize_whitespace(str(product_json.get("category") or ""))
        return category or (breadcrumbs[-1] if breadcrumbs else "")

    def _looks_like_washing_machine(self, *, title: str, url: str) -> bool:
        haystack = normalize_for_match(f"{title} {url}")
        return any(
            token in haystack
            for token in (
                normalize_for_match("πλυντήριο ρούχων"),
                "plyntirio royxwn",
                "plyntirio rouxwn",
                "washing machine",
            )
        )

    def _dedupe_spec_items(self, items: list[SpecItem]) -> list[SpecItem]:
        seen: set[tuple[str, str]] = set()
        seen_labels: set[str] = set()
        out: list[SpecItem] = []
        for item in items:
            label_key = normalize_for_match(item.label)
            key = (label_key, normalize_for_match(item.value or ""))
            if not key[0] or not key[1] or key in seen:
                continue
            if label_key in seen_labels:
                continue
            seen.add(key)
            seen_labels.add(label_key)
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
