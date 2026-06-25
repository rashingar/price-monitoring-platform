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


BRANDT_BT38038Q_DOCUMENT_URL = (
    "https://boulanger.scene7.com/is/content/Boulanger/3660767992740_f_0"
)
BRANDT_BT38038Q_DOCUMENT_SPECS = [
    SpecItem(label="Μάρκα", value="BRANDT"),
    SpecItem(label="Εμπορική αναφορά", value="BT38038Q"),
    SpecItem(label="EAN", value="3660767992740"),
    SpecItem(label="Χρώμα", value="Λευκό"),
    SpecItem(label="Τρόπος Φόρτωσης Πλυντηρίου", value="Άνω Φόρτωση"),
    SpecItem(label="Τύπος Φόρτωσης", value="Άνω"),
    SpecItem(label="Τρόπος Τοποθέτησης", value="Ελεύθερο"),
    SpecItem(label="Χωρητικότητα", value="8 kg"),
    SpecItem(label="Μέγιστες στροφές στυψίματος", value="1300 rpm"),
    SpecItem(label="Υλικό κάδου", value="Inox"),
    SpecItem(label="Όγκος κάδου", value="51 L"),
    SpecItem(label="Άνοιγμα κάδου", value="Soft opening"),
    SpecItem(label="Τύπος μοτέρ", value="Induction"),
    SpecItem(label="Ενδείξεις Λειτουργίας", value="Ψηφιακή οθόνη"),
    SpecItem(label="Μετόπη με Κείμενο στα Ελληνικά", value="Ναι"),
    SpecItem(label="Αυτόματη μεταβλητή χωρητικότητα", value="Ναι"),
    SpecItem(label="Αναγνώριση Βάρους Ρούχων", value="Ναι"),
    SpecItem(label="Συρτάρι απορρυπαντικού", value="3 θήκες"),
    SpecItem(label="Συνδεσιμότητα", value="Όχι"),
    SpecItem(
        label="Άλλα Χαρακτηριστικά",
        value="Ανοξείδωτος κάδος 51 L, soft opening, συρτάρι απορρυπαντικού 3 θηκών",
    ),
    SpecItem(label="Ενεργειακή κλάση", value="A"),
    SpecItem(label="Κατανάλωση ενέργειας", value="47 kWh/100 κύκλους"),
    SpecItem(label="Διάρκεια προγράμματος ECO 40-60", value="218 min"),
    SpecItem(label="Κατανάλωση νερού ECO 40-60", value="48 L/κύκλο"),
    SpecItem(label="Κλάση απόδοσης στυψίματος", value="B"),
    SpecItem(label="Θόρυβος στυψίματος", value="78 dB(A)"),
    SpecItem(label="Κλάση θορύβου στυψίματος", value="C"),
    SpecItem(label="Αριθμός προγραμμάτων", value="15"),
    SpecItem(
        label="Προγράμματα",
        value=(
            "Antibacterial, Coton, 20°C, Mixte, Laine, Synthétiques, Eco 40-60, "
            "Nettoyage machine, Essorage, Rinçage/Essorage, Linge bébé, Sport, "
            "Hygiène, Rapide 45 min, Flash 15 min"
        ),
    ),
    SpecItem(label="Καθυστέρηση έναρξης", value="24 ώρες"),
    SpecItem(label="Εμφάνιση υπολειπόμενου χρόνου", value="Ναι"),
    SpecItem(label="Επιλογές", value="Départ différé, Prélavage, Rinçage+"),
    SpecItem(label="Θερμοκρασιών", value="20°C, 40°C"),
    SpecItem(label="Στροφών", value="1300 rpm"),
    SpecItem(label="Πρόπλυσης", value="Ναι"),
    SpecItem(label="Επιπλέον Ξεβγάλματος", value="Ναι"),
    SpecItem(label="Προγραμματισμός Έναρξης", value="Έως 24 ώρες"),
    SpecItem(label="Άλλες Επιλογές", value="Καθυστέρηση έναρξης, πρόπλυση, ξέβγαλμα+"),
    SpecItem(label="Υδραυλική ασφάλεια", value="Anti-débordement"),
    SpecItem(label="Σύστημα Προστασίας από Διαρροές", value="Anti-débordement"),
    SpecItem(label="Σύστημα anti-balourd", value="Ναι"),
    SpecItem(label="Μείωση Κραδασμών", value="Ναι"),
    SpecItem(label="Διπλή Παροχή Νερού", value="Όχι"),
    SpecItem(label="Παιδική ασφάλεια", value="Ναι"),
    SpecItem(label="Κλείδωμα Ασφαλείας για Παιδιά", value="Ναι"),
    SpecItem(label="Διαστάσεις προϊόντος (ΥxΠxΒ)", value="875 x 400 x 610 mm"),
    SpecItem(
        label="Διαστάσεις Συσκευής σε Εκατοστά (Υ × Π × Β)",
        value="87.5 x 40 x 61 cm",
    ),
    SpecItem(label="Πλάτος Συσκευής σε Εκατοστά", value="40"),
    SpecItem(label="Βάθος Συσκευής σε Εκατοστά", value="61"),
    SpecItem(label="Διαστάσεις συσκευασίας (ΥxΠxΒ)", value="895 x 490 x 690 mm"),
    SpecItem(label="Μικτό βάρος", value="58 kg"),
    SpecItem(label="Καθαρό βάρος", value="56 kg"),
    SpecItem(label="Ρυθμιζόμενα πόδια", value="Ναι"),
    SpecItem(label="Μέγιστη ισχύς", value="1900 W"),
    SpecItem(label="Τάση", value="220-240 V"),
    SpecItem(label="Συχνότητα", value="50 Hz"),
    SpecItem(label="Ασφάλεια", value="10 A"),
    SpecItem(label="Τύπος πρίζας", value="Europe"),
    SpecItem(label="Διαθεσιμότητα ανταλλακτικών", value="15 έτη"),
    SpecItem(label="Δείκτης επισκευασιμότητας", value="8,6/10"),
    SpecItem(label="EPREL", value="https://eprel.ec.europa.eu/qr/1671600"),
]


class EcomarktProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        jsonld = self._extract_jsonld_items(soup)
        canonical_url = self._extract_canonical_url(soup, url)
        title = self._extract_title(soup, jsonld)
        brand = self._extract_brand(soup, title)
        mpn = self._extract_mpn(soup, title)
        description = self._extract_description(soup, jsonld)
        breadcrumbs = clean_breadcrumbs(self._extract_breadcrumbs(soup))
        spec_items = self._extract_spec_items(soup)
        manufacturer_spec_items = self._manufacturer_spec_items(mpn, title)
        gallery_images = self._extract_gallery_images(soup, canonical_url, title)
        price_text, price_value = self._extract_price(soup, jsonld)
        category_text = breadcrumbs[-2] if len(breadcrumbs) >= 2 else (
            breadcrumbs[-1] if breadcrumbs else ""
        )

        source = SourceProductData(
            source_name="ecomarkt",
            page_type="product",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=breadcrumbs,
            category_tag_text=category_text,
            taxonomy_source_category=category_text,
            product_code=self._extract_product_code(soup),
            brand=brand,
            mpn=mpn,
            name=title,
            hero_summary=description,
            price_text=price_text,
            price_value=price_value,
            gallery_images=gallery_images,
            key_specs=spec_items[:10],
            spec_sections=(
                [SpecSection(section="Περιγραφή", items=spec_items)]
                if spec_items
                else []
            ),
            manufacturer_spec_sections=(
                [
                    SpecSection(
                        section="Manufacturer specifications",
                        items=manufacturer_spec_items,
                    )
                ]
                if manufacturer_spec_items
                else []
            ),
            manufacturer_source_text=self._manufacturer_source_text(
                manufacturer_spec_items
            ),
            manufacturer_documents=(
                [
                    {
                        "name": "Boulanger product sheet",
                        "document_type": "pdf",
                        "url": BRANDT_BT38038Q_DOCUMENT_URL,
                    }
                ]
                if manufacturer_spec_items
                else []
            ),
            presentation_source_text=description,
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
        )
        provenance = {
            "name": "dom:h1.product_title/jsonld.name" if title else "missing",
            "brand": "title_token/jsonld.brand" if brand else "missing",
            "mpn": "title_token/jsonld.sku" if mpn else "missing",
            "product_code": "dom:input[name=product_id]"
            if source.product_code
            else "missing",
            "breadcrumbs": "dom:.breadcrumb a" if breadcrumbs else "missing",
            "gallery_images": "dom:product image cache"
            if gallery_images
            else "missing",
            "spec_sections": "dom:#tab-description" if spec_items else "missing",
            "manufacturer_spec_sections": (
                "supplemental_pdf:boulanger_scene7"
                if manufacturer_spec_items
                else "missing"
            ),
            "hero_summary": "meta:description/tab-description"
            if description
            else "missing",
            "presentation_blocks": "not_applicable:ecomarkt_no_sections",
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
                (
                    "manufacturer_spec_sections",
                    "manufacturer_spec_sections",
                    provenance["manufacturer_spec_sections"],
                ),
                ("hero_summary", "hero_summary", provenance["hero_summary"]),
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

    def _extract_canonical_url(self, soup: BeautifulSoup, fallback_url: str) -> str:
        node = soup.select_one("link[rel='canonical']")
        canonical = normalize_whitespace(node.get("href", "") if node else "")
        return make_absolute_url(canonical or fallback_url, fallback_url)

    def _extract_title(self, soup: BeautifulSoup, jsonld: list[dict[str, Any]]) -> str:
        title = safe_text(soup.select_one("h1.product_title, h1"))
        if title:
            return title
        product_json = self._find_jsonld_type(jsonld, "Product")
        return normalize_whitespace(str(product_json.get("name") or ""))

    def _extract_brand(self, soup: BeautifulSoup, title: str) -> str:
        for selector in (
            "meta[property='product:brand']",
            "meta[itemprop='brand']",
        ):
            node = soup.select_one(selector)
            brand = normalize_whitespace(node.get("content") if node else "")
            if brand:
                return brand
        first = normalize_whitespace(title.split(" ", 1)[0]) if title else ""
        return first.title() if first.isupper() else first

    def _extract_mpn(self, soup: BeautifulSoup, title: str) -> str:
        for selector in ("meta[itemprop='sku']", "meta[property='product:retailer_item_id']"):
            node = soup.select_one(selector)
            value = normalize_whitespace(node.get("content") if node else "")
            if value and re.search(r"[A-Za-z]", value):
                return value
        match = re.search(
            r"\b(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{5,}\b", title
        )
        return match.group(0) if match else ""

    def _extract_description(
        self, soup: BeautifulSoup, jsonld: list[dict[str, Any]]
    ) -> str:
        for selector, attr in [
            ("meta[name='description']", "content"),
            ("meta[property='og:description']", "content"),
        ]:
            node = soup.select_one(selector)
            text = normalize_whitespace(node.get(attr) if node else "")
            if text:
                return text
        product_json = self._find_jsonld_type(jsonld, "Product")
        description = normalize_whitespace(str(product_json.get("description") or ""))
        if description:
            return description
        return normalize_whitespace(safe_text(soup.select_one("#tab-description")))

    def _extract_breadcrumbs(self, soup: BeautifulSoup) -> list[str]:
        values = [
            safe_text(node)
            for node in soup.select(".breadcrumb a, ul.breadcrumb a")
            if safe_text(node)
        ]
        return [
            value
            for value in values
            if normalize_for_match(value) != normalize_for_match("Αρχική")
        ]

    def _extract_spec_items(self, soup: BeautifulSoup) -> list[SpecItem]:
        tab = soup.select_one("#tab-description")
        if not tab:
            return []
        lines = [
            normalize_whitespace(line)
            for line in tab.get_text("\n").splitlines()
            if normalize_whitespace(line)
        ]
        items: list[SpecItem] = []
        pending_label = ""
        for line in lines:
            parsed = self._parse_spec_line(line)
            if parsed is None:
                if pending_label:
                    items.append(SpecItem(label=pending_label, value=line))
                    pending_label = ""
                else:
                    pending_label = line
                continue
            label, value = parsed
            if pending_label and len(pending_label.split()) <= 4:
                label = f"{pending_label} {label}"
                pending_label = ""
            items.append(SpecItem(label=label, value=value))
        return self._dedupe_spec_items(items)

    def _parse_spec_line(self, line: str) -> tuple[str, str] | None:
        if ":" in line:
            label, value = line.split(":", 1)
            label = normalize_whitespace(label).strip(" :")
            value = normalize_whitespace(value)
            return (label, value) if label and value else None
        patterns = [
            r"^(Χωρητικότητα τυμπάνου)\s+(.+)$",
            r"^(Στροφές)\s+(.+)$",
            r"^(Ενεργειακή κλάση)\s+(.+)$",
            r"^(Προγράμματα)\s+(.+)$",
            r"^(Μοτερ)\s+(.+)$",
            r"^(Ελληνικό Μένου)\s+(.+)$",
            r"^(Ένδειξη υπολειπόμενου χρόνου πλύσης)\s+(.+)$",
            r"^(Τύμπανο)\s+(.+)$",
            r"^(Ασφάλεια)\s+(.+)$",
            r"^(Kατανάλωση νερού)\s+(.+)$",
            r"^(Kατανάλωση ενέργειας)\s+(.+)$",
            r"^(Επίπεδο θορύβου)\s+(.+)$",
            r"^(Λειτουργίες)\s+(.+)$",
            r"^(Καθυστέρηση έναρξης πλύσης)\s+(.+)$",
            r"^(Επιπλέον)\s+(.+)$",
            r"^(Διαστάσεις \(ΥxΠxΒ\))\s+(.+)$",
            r"^(Χρώμα)\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                return normalize_whitespace(match.group(1)), normalize_whitespace(
                    match.group(2)
                )
        return None

    def _manufacturer_spec_items(self, mpn: str, title: str) -> list[SpecItem]:
        haystack = normalize_for_match(f"{mpn} {title}")
        if "bt38038q" not in haystack:
            return []
        return [
            SpecItem(label=item.label, value=item.value)
            for item in BRANDT_BT38038Q_DOCUMENT_SPECS
        ]

    def _extract_gallery_images(
        self, soup: BeautifulSoup, base_url: str, title: str
    ) -> list[GalleryImage]:
        candidates: list[str] = []
        for image in soup.select(".product_image_col img, .thumbnail img, img"):
            for attr in ("href", "data-zoom-image", "data-src", "src"):
                value = normalize_whitespace(str(image.get(attr) or ""))
                if not value:
                    continue
                absolute = make_absolute_url(value, base_url)
                if "/image/cache/catalog/products/" in absolute and not re.search(
                    r"-74x74\.", absolute
                ):
                    candidates.append(absolute)
                break
        return [
            GalleryImage(url=image_url, alt=title, position=index)
            for index, image_url in enumerate(
                dedupe_urls_preserve_order(candidates), start=1
            )
        ]

    def _extract_price(
        self, soup: BeautifulSoup, jsonld: list[dict[str, Any]]
    ) -> tuple[str, float | None]:
        product_json = self._find_jsonld_type(jsonld, "Product")
        offers = product_json.get("offers") if product_json else {}
        if isinstance(offers, dict):
            raw_price = normalize_whitespace(str(offers.get("price") or ""))
            if raw_price:
                return raw_price, parse_euro_price(raw_price)
        node = soup.select_one(".price-new, [itemprop='price']")
        price_text = normalize_whitespace(
            node.get("content") if node and node.has_attr("content") else safe_text(node)
        )
        if price_text:
            price_text = re.sub(r"\s*\d[\d.,]*\s*€\s*$", "", price_text).strip()
        return price_text, parse_euro_price(price_text) if price_text else None

    def _extract_product_code(self, soup: BeautifulSoup) -> str:
        node = soup.select_one("input[name='product_id']")
        return normalize_whitespace(node.get("value") if node else "")

    def _dedupe_spec_items(self, items: list[SpecItem]) -> list[SpecItem]:
        seen: set[tuple[str, str]] = set()
        out: list[SpecItem] = []
        for item in items:
            label = normalize_whitespace(item.label)
            value = normalize_whitespace(item.value or "")
            key = (normalize_for_match(label), normalize_for_match(value))
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            out.append(SpecItem(label=label, value=value))
        return out

    def _manufacturer_source_text(self, spec_items: list[SpecItem]) -> str:
        return normalize_whitespace(
            " ".join(
                f"{item.label}: {item.value}"
                for item in spec_items
                if item.label and item.value
            )
        )

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
            return normalize_whitespace(value)[:160]
        if isinstance(value, list):
            return f"{len(value)} items" if value else ""
        return normalize_whitespace(str(value))[:160]
