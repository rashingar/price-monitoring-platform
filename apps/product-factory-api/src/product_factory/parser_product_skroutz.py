from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from .eprel import resolve_eprel_energy_label_asset_url
from .models import FieldDiagnostic, GalleryImage, ParsedProduct, SelectorTraceEntry, SourceProductData, SpecItem, SpecSection
from .normalize import clean_breadcrumbs, dedupe_urls_preserve_order, make_absolute_url, normalize_for_match, normalize_whitespace, parse_euro_price, safe_text
from .skroutz_taxonomy import classify_skroutz_taxonomy, normalize_category_href_slug, serialize_source_category
from .utils import utcnow_iso

INTERSTITIAL_MARKERS = {"just a moment", "enable javascript and cookies", "περιμένετε"}
MODEL_TOKEN_RE = re.compile(r"^(?=.*[A-Z])(?=.*\d)[A-Z0-9][A-Z0-9._/-]{2,}$")
NUMERIC_RE = re.compile(r"\d+(?:[.,]\d+)?")
CUPS_RE = re.compile(r"(\d+(?:\s*-\s*\d+)?)\s*(?:φλιτζ|cups?)", re.IGNORECASE)
CAPACITY_LT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*lt", re.IGNORECASE)
DIMENSIONS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)(?:\s*[xX×]\s*(\d+(?:[.,]\d+)?))?")
WEIGHT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*kg\b", re.IGNORECASE)
WARRANTY_RE = re.compile(r"(\d+)\s*(?:έτη|έτος|χρόνια|χρονα|years?)", re.IGNORECASE)
TITLE_CODE_SUFFIX_RE = re.compile(r"\s+Κωδικός:\s*[A-Z0-9.-]+\s*$", re.IGNORECASE)
SUMMARY_PAIR_RE = re.compile(r"([^:]{2,80}?):\s*(.+?)(?=(?:\s+[A-Za-zΑ-ΩΆ-Ώα-ωά-ώ][^:]{1,40}:)|$)")

SKROUTZ_FAMILIES: dict[str, dict[str, Any]] = {
    "soundbar": {
        "category_labels": {"Soundbar", "Soundbars", "Sound Bars"},
        "category_href_tokens": {"soundbar"},
        "title_tokens": {"soundbar"},
        "breadcrumbs": ["Αρχική", "ΕΙΚΟΝΑ & ΗΧΟΣ", "Audio Systems", "Sound Bars"],
        "sections": [],
        "spec_mode": "custom",
        "taxonomy_mode": "family",
    },
    "coffee_filter": {
        "category_labels": {"Καφετιέρες Φίλτρου"},
        "category_href_tokens": {"kafetieres filtrou"},
        "title_tokens": {"kafetiera filtrou", "kafetier", "filtr"},
        "breadcrumbs": ["Αρχική", "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Καφές-Ροφήματα-Χυμοί", "Καφετιέρες Φίλτρου"],
        "sections": [
            ("Επισκόπηση Προϊόντος", ["Χωρητικότητα σε Φλυτζάνια", "Υλικό Κανάτας", "Ισχύς σε Watts", "Χωρητικότητα Δοχείου Νερού σε Λίτρα", "Ένδειξη Στάθμης Νερού", "Αποσπώμενο Δοχείο Νερού", "Θερμαινόμενη Βάση", "Ενδεικτική Λυχνία Λειτουργίας", "Ηχητικό Σήμα Ειδοποίησης", "Αποθήκευση Καλωδίου"]),
            ("Ειδικές Λειτουργίες", ["Διακοπή Σταξίματος", "Λειτουργία Aroma", "Αυτόματη Διακοπή Λειτουργίας", "Χρονοδιακόπτης Λειτουργίας"]),
            ("Γενικά Χαρακτηριστικά", ["Χρώμα", "Βάρος Συσκευής σε Κιλά", "Διαστάσεις Συσκευής σε Εκατοστά. (Υ χ Π χ Β", "Εγγύηση Κατασκευαστή"]),
        ],
        "spec_mode": "custom",
        "taxonomy_mode": "family",
    },
    "kettle": {
        "category_labels": {"Βραστήρες"},
        "category_href_tokens": {"brasthres", "vrastires"},
        "title_tokens": {"vrastir", "brasth"},
        "breadcrumbs": ["Αρχική", "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Συσκευές Κουζίνας", "Βραστήρες"],
        "sections": [
            ("Επισκόπηση Προϊόντος", ["Χωρητικότητα σε Λίτρα", "Ισχύς σε Watts", "Αποσπώμενη Βάση", "Βάση 360 Μοιρών", "Φίλτρο Νερού", "Άνοιγμα του Καπακιού με το Πάτημα ενός Κουμπιού", "Καλυμμένη Αντίσταση", "Υλικό Κατασκευής", "Αποθήκευση Καλωδίου"]),
            ("Λειτουργίες - Ενδείξεις", ["Ένδειξη Στάθμης Νερού", "Ένδειξη Λειτουργίας", "Ηχητικό Σήμα Ειδοποίησης", "Επιλογές Θερμοκρασίας Βρασμού", "Λειτουργία Διατήρησης Θερμοκρασίας", "Αυτόματος Τερματισμός Λειτουργίας", "Προστασία από Βρασμό Χωρίς Νερό"]),
            ("Γενικά Χαρακτηριστικά", ["Χρώμα", "Βάρος Συσκευής σε Κιλά", "Διαστάσεις Συσκευής σε Εκατοστά. (Υ χ Π χ Β", "Εγγύηση Κατασκευαστή"]),
        ],
        "spec_mode": "custom",
        "taxonomy_mode": "family",
    },
    "tabletop_hob": {
        "category_labels": {"Επιτραπέζιες Εστίες"},
        "category_href_tokens": {"epitrapezies esties"},
        "title_tokens": {"epitrapezia estia"},
        "breadcrumbs": ["Αρχική", "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Μικροί Μάγειρες", "Εστίες"],
        "sections": [("Χαρακτηριστικά Μοντέλου", ["Κατασκευαστής", "Μοντέλο"]), ("Γενικά Χαρακτηριστικά", ["Εστία"]), ("Διαστάσεις", ["Πλάτος", "Βάθος"])],
        "spec_mode": "custom",
        "taxonomy_mode": "family",
    },
    "ice_cream_maker": {
        "category_labels": {"Παγωτομηχανές"},
        "category_href_tokens": {"pagotomichanes"},
        "title_tokens": {"pagotomichan"},
        "breadcrumbs": ["Αρχική", "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Μικροί Μάγειρες", "Παγωτομηχανές"],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "family",
    },
    "hair_straightener": {
        "category_labels": {"Πρέσες Μαλλιών"},
        "category_href_tokens": {"preses mallion"},
        "title_tokens": {"presa mallion", "isiotik", "straightener"},
        "breadcrumbs": ["Αρχική", "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Προσωπική Φροντίδα", "Βούρτσες-Ψαλίδια-ισιωτικά"],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "family",
    },
    "ironing_board": {
        "category_labels": {"Σιδερώστρες"},
        "category_href_tokens": {"siderostres"},
        "title_tokens": {"siderostra", "siderostres", "ironing board"},
        "breadcrumbs": ["Αρχική", "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Σιδέρωμα", "Σιδερώστρες"],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "family",
    },
    "television": {
        "category_labels": {"Τηλεοράσεις"},
        "category_href_tokens": {"tileoraseis", "television"},
        "title_tokens": {"tileorasi", "tv"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
    "speaker": {
        "category_labels": {"Ηχεία", "Karaoke"},
        "category_href_tokens": {"hxeia", "ixeia", "audio systems", "speaker", "speakers", "karaoke"},
        "title_tokens": {"icheio", "ixeio", "speaker", "karaoke"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
    "dishwasher": {
        "category_labels": {"Πλυντήρια Πιάτων"},
        "category_href_tokens": {"plyntiria piaton", "plynthria piatwn", "dishwashers"},
        "title_tokens": {"plyntirio piaton", "dishwasher"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
    "cooker": {
        "category_labels": {"Κουζίνες", "Κουζίνες & Φούρνοι"},
        "category_href_tokens": {"kouzines", "koyzines"},
        "title_tokens": {"kouzina"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
    "microwave": {
        "category_labels": {"Φούρνοι Μικροκυμάτων"},
        "category_href_tokens": {"fournoi mikrokymatwn", "fournoi mikrokymaton", "mikrokymatwn", "mikrokymaton"},
        "title_tokens": {"fournos mikrokymat", "mikrokymat", "microwave"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
    "refrigeration": {
        "category_labels": {"Ψυγεία", "Καταψύκτες", "Ψυγεία & Καταψύκτες"},
        "category_href_tokens": {"psygeia", "psigeia", "katapsyktes", "katapsiktes"},
        "title_tokens": {"psygei", "katapsykt", "fridge", "freezer"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
    "laundry": {
        "category_labels": {"Πλυντήρια Ρούχων", "Στεγνωτήρια Ρούχων", "Πλυντήρια-Στεγνωτήρια"},
        "category_href_tokens": {"plyntiria stegnotiria", "plynthria stegnwthria", "plyntiria", "plynthria", "stegnotiria"},
        "title_tokens": {"plyntir", "stegnotir", "washer", "dryer"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
    "built_in_appliance": {
        "category_labels": {"Εντοιχιζόμενες Συσκευές"},
        "category_href_tokens": {"entoixizomenes", "entoixizomenes syskeyes", "entoichizomenes syskeves", "esties kouzinas"},
        "title_tokens": {"entoichiz", "built in"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
    "hood": {
        "category_labels": {"Απορροφητήρες"},
        "category_href_tokens": {"aporrofitires"},
        "title_tokens": {"aporrofit"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
    "home_appliance_accessory": {
        "category_labels": {"Αξεσουάρ Οικιακών Συσκευών"},
        "category_href_tokens": {"axesouar oikiakon syskeyon", "aksesouar oikiakon syskevon"},
        "title_tokens": {"syndetiko", "axesouar", "aksesouar"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
    "heat_pump": {
        "category_labels": {"Αντλίες Θερμότητας"},
        "category_href_tokens": {"antlies thermotitas"},
        "title_tokens": {"antlia thermotitas", "heat pump"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
    "air_conditioner": {
        "category_labels": {"Κλιματιστικά"},
        "category_href_tokens": {"klimatistika", "air condition"},
        "title_tokens": {"klimatist", "air condition", "btu", "inverter"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
    "robot_vacuum": {
        "category_labels": {"Σκούπες Ρομπότ"},
        "category_href_tokens": {"skoypa rompot", "skoupa rompot"},
        "title_tokens": {"rompot", "robot vacuum", "robot mop"},
        "breadcrumbs": ["Αρχική", "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Σκούπισμα", "Σκούπες Ρομπότ"],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "family",
    },
    "lpg_heater": {
        "category_labels": {"Θερμαντικά"},
        "category_href_tokens": {"thermantika"},
        "title_tokens": {"ygraeri", "soba", "thermantik"},
        "breadcrumbs": [],
        "sections": [],
        "spec_mode": "raw",
        "taxonomy_mode": "helper",
    },
}


class SkroutzProductParser:
    def parse(self, html: str, url: str, fallback_used: bool = False) -> ParsedProduct:
        soup = BeautifulSoup(html, "lxml")
        if self._is_interstitial(soup):
            source = SourceProductData(source_name="skroutz", page_type="interstitial", url=url, canonical_url=url, raw_html_path="", scraped_at=utcnow_iso(), fallback_used=fallback_used)
            return ParsedProduct(source=source, missing_fields=["name", "brand", "breadcrumbs", "gallery_images", "spec_sections"], warnings=["skroutz_interstitial_detected"], critical_missing=["name", "breadcrumbs", "gallery_images", "spec_sections"])

        jsonld = self._parse_product_jsonld(soup)
        provenance: dict[str, str] = {}
        diagnostics: dict[str, FieldDiagnostic] = {}
        warnings: list[str] = []
        canonical_url = self._extract_canonical_url(soup, url)

        title, title_source, title_trace = self._extract_title(soup, jsonld)
        provenance["name"] = title_source
        diagnostics["name"] = self._make_diagnostic(title, title_source, 0.99 if title else 0.0, title_trace)

        category_tag_text, category_tag_href, category_source, category_trace = self._extract_category_tag(soup, jsonld, canonical_url)
        provenance["category_tag"] = category_source
        diagnostics["category_tag"] = self._make_diagnostic(category_tag_text or category_tag_href, category_source, 0.95 if category_tag_text or category_tag_href else 0.0, category_trace)

        family = self._resolve_family(category_tag_text, category_tag_href, title, canonical_url)
        family_config = SKROUTZ_FAMILIES.get(family, {})

        merchant_titles = self._extract_merchant_titles(soup)
        brand, brand_source, brand_trace = self._extract_brand(soup, jsonld, title, merchant_titles)
        provenance["brand"] = brand_source
        diagnostics["brand"] = self._make_diagnostic(brand, brand_source, 0.96 if brand else 0.0, brand_trace)

        product_code, code_source, code_trace = self._extract_page_sku(soup, jsonld, canonical_url)
        provenance["product_code"] = code_source
        diagnostics["product_code"] = self._make_diagnostic(product_code, code_source, 0.95 if product_code else 0.0, code_trace)

        summary_html, hero_summary, summary_source, summary_trace, summary_pairs = self._extract_summary_block(soup)
        provenance["hero_summary"] = summary_source
        diagnostics["hero_summary"] = self._make_diagnostic(hero_summary, summary_source, 0.88 if hero_summary else 0.0, summary_trace)

        raw_sections, raw_pairs, spec_source, spec_trace = self._extract_raw_specs(soup)
        if raw_pairs and summary_pairs:
            warnings.append("merchant_summary_and_structured_characteristics_present")

        mpn, mpn_source, mpn_trace = self._extract_mpn(soup, jsonld, title, brand, product_code, merchant_titles)
        provenance["mpn"] = mpn_source
        diagnostics["mpn"] = self._make_diagnostic(mpn, mpn_source, 0.92 if mpn else 0.0, mpn_trace)

        price_text, price_value, price_source, price_trace = self._extract_price(soup, jsonld)
        provenance["price"] = price_source
        diagnostics["price"] = self._make_diagnostic(price_text or price_value, price_source, 0.95 if price_text or price_value else 0.0, price_trace)

        taxonomy_hint = None
        if family_config.get("taxonomy_mode") == "helper" or not family:
            taxonomy_hint = classify_skroutz_taxonomy(
                category_tag_text=category_tag_text,
                category_tag_href=category_tag_href,
                title=title,
                url=canonical_url,
                brand=brand,
                family_key=family,
            )

        if taxonomy_hint and taxonomy_hint.ambiguous:
            warnings.append(f"skroutz_taxonomy_ambiguous:{taxonomy_hint.escalation_reason}")
        elif taxonomy_hint and family_config.get("taxonomy_mode") == "helper":
            warnings.append(f"skroutz_taxonomy_helper_used:{taxonomy_hint.matched_rule_id}")

        breadcrumbs = clean_breadcrumbs(
            SKROUTZ_FAMILIES.get(family, {}).get("breadcrumbs", [])
            or (taxonomy_hint.breadcrumbs if taxonomy_hint and not taxonomy_hint.ambiguous else [])
        )
        provenance["breadcrumbs"] = category_source if breadcrumbs else "missing"
        diagnostics["breadcrumbs"] = self._make_diagnostic(breadcrumbs, provenance["breadcrumbs"], 0.95 if breadcrumbs else 0.0, category_trace)

        family_source_category = ""
        family_match_type = ""
        if family and family_config.get("taxonomy_mode") != "helper" and len(breadcrumbs) >= 3:
            family_source_category = serialize_source_category(
                breadcrumbs[1],
                breadcrumbs[2],
                breadcrumbs[3:],
            )
            family_match_type = "exact_category"

        canonical_sections = self._build_canonical_sections(
            family=family,
            brand=brand,
            mpn=mpn,
            title=title,
            hero_summary=hero_summary,
            raw_sections=raw_sections,
            raw_pairs=raw_pairs,
            summary_pairs=summary_pairs,
            merchant_titles=merchant_titles,
        )
        provenance["spec_sections"] = spec_source
        diagnostics["spec_sections"] = self._make_diagnostic(canonical_sections, spec_source, 0.92 if canonical_sections else 0.0, spec_trace)
        key_specs = self._build_key_specs(family, canonical_sections, raw_sections, raw_pairs, summary_pairs)
        provenance["key_specs"] = "canonical_from_specs" if key_specs else "missing"
        diagnostics["key_specs"] = self._make_diagnostic(key_specs, provenance["key_specs"], 0.9 if key_specs else 0.0, [])
        energy_label_asset_url = resolve_eprel_energy_label_asset_url(
            family_key=family,
            breadcrumbs=breadcrumbs,
            taxonomy_source_category=(taxonomy_hint.source_category if taxonomy_hint and not taxonomy_hint.ambiguous else family_source_category),
            title=title,
            canonical_url=canonical_url,
            model_identifier=mpn,
        )
        product_sheet_asset_url = self._build_bsh_energy_label_pdf_url(brand, mpn)

        gallery_images, gallery_source, gallery_trace = self._extract_gallery_images(soup, jsonld, canonical_url, title)
        provenance["gallery_images"] = gallery_source
        diagnostics["gallery_images"] = self._make_diagnostic(gallery_images, gallery_source, 0.95 if gallery_images else 0.0, gallery_trace)

        supported_page = bool(
            (family and family_config.get("taxonomy_mode") != "helper")
            or (
                taxonomy_hint
                and not taxonomy_hint.ambiguous
                and taxonomy_hint.parent_category
                and taxonomy_hint.leaf_category
            )
        )
        if not supported_page:
            warnings.append("unsupported_skroutz_category")

        source = SourceProductData(
            source_name="skroutz",
            page_type="product" if supported_page else "unsupported_family",
            url=url,
            canonical_url=canonical_url,
            breadcrumbs=breadcrumbs,
            skroutz_family=family or "",
            category_tag_text=category_tag_text,
            category_tag_href=category_tag_href,
            category_tag_slug=normalize_category_href_slug(category_tag_href),
            taxonomy_source_category=(taxonomy_hint.source_category if taxonomy_hint and not taxonomy_hint.ambiguous else family_source_category),
            taxonomy_match_type=(taxonomy_hint.match_type if taxonomy_hint and not taxonomy_hint.ambiguous else family_match_type),
            taxonomy_rule_id=(taxonomy_hint.matched_rule_id if taxonomy_hint else (f"family:{family}" if family else "")),
            taxonomy_ambiguity=bool(taxonomy_hint.ambiguous if taxonomy_hint else False),
            taxonomy_escalation_reason=taxonomy_hint.escalation_reason if taxonomy_hint else "",
            taxonomy_tv_inches=taxonomy_hint.tv_inches if taxonomy_hint else None,
            product_code=product_code,
            brand=brand,
            name=title,
            hero_summary=hero_summary,
            price_text=price_text,
            price_value=price_value,
            gallery_images=gallery_images,
            energy_label_asset_url=energy_label_asset_url,
            product_sheet_asset_url=product_sheet_asset_url,
            key_specs=key_specs,
            spec_sections=canonical_sections,
            presentation_source_html=summary_html,
            presentation_source_text=hero_summary,
            raw_html_path="",
            scraped_at=utcnow_iso(),
            fallback_used=fallback_used,
            mpn=mpn,
        )
        missing_fields = self._collect_missing_fields(source)
        critical_missing = self._collect_critical_missing(source, supported_page)
        return ParsedProduct(source=source, provenance=provenance, field_diagnostics=diagnostics, missing_fields=missing_fields, warnings=warnings, critical_missing=critical_missing)

    def _is_interstitial(self, soup: BeautifulSoup) -> bool:
        title = normalize_whitespace(soup.title.get_text(" ", strip=True) if soup.title else "")
        body_text = normalize_for_match(safe_text(soup.body)[:1000])
        haystack = normalize_for_match(f"{title} {body_text}")
        return any(marker in haystack for marker in INTERSTITIAL_MARKERS)

    def _parse_product_jsonld(self, soup: BeautifulSoup) -> dict[str, Any]:
        node = soup.select_one("#product-schema") or soup.select_one("script[type='application/ld+json']")
        if not node:
            return {}
        raw = node.string or node.get_text(" ", strip=True)
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _extract_canonical_url(self, soup: BeautifulSoup, fallback_url: str) -> str:
        node = soup.select_one("link[rel='canonical']")
        href = node.get("href") if node else ""
        return make_absolute_url(href, fallback_url) if href else fallback_url

    def _extract_title(self, soup: BeautifulSoup, jsonld: dict[str, Any]) -> tuple[str, str, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        node = soup.select_one("div.sku-title h1.page-title")
        trace.append(self._trace("dom", "div.sku-title h1.page-title", [node] if node else [], node))
        if node:
            clone = BeautifulSoup(str(node), "lxml").select_one("h1")
            small = clone.select_one("small") if clone else None
            if small:
                small.decompose()
            title = self._clean_title(safe_text(clone))
            if title:
                return title, "dom:div.sku-title h1.page-title", trace
        for selector in ["meta[property='og:title']", "meta[name='twitter:title']", "title"]:
            node = soup.select_one(selector)
            trace.append(self._trace("dom", selector, [node] if node else [], node))
            if not node:
                continue
            value = normalize_whitespace(node.get("content") or safe_text(node))
            if selector == "title":
                value = value.split("|")[0].strip()
            value = self._clean_title(value)
            if value:
                return value, f"dom:{selector}", trace
        title = self._clean_title(normalize_whitespace(jsonld.get("name")))
        return (title, "jsonld:name", trace) if title else ("", "missing", trace)

    def _clean_title(self, title: str) -> str:
        cleaned = normalize_whitespace(title)
        if not cleaned:
            return ""
        return TITLE_CODE_SUFFIX_RE.sub("", cleaned).strip()

    def _extract_category_tag(
        self,
        soup: BeautifulSoup,
        jsonld: dict[str, Any],
        base_url: str,
    ) -> tuple[str, str, str, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        node = soup.select_one("div.sku-title a.category-tag")
        trace.append(self._trace("dom", "div.sku-title a.category-tag", [node] if node else [], node))
        value = safe_text(node)
        href = make_absolute_url(node.get("href"), base_url) if node and node.get("href") else ""
        if value or href:
            return value, href, "dom:div.sku-title a.category-tag", trace
        value = normalize_whitespace(jsonld.get("category"))
        return (value, "", "jsonld:category", trace) if value else ("", "", "missing", trace)

    def _resolve_family(self, category_hint: str, category_href: str, title: str, canonical_url: str = "") -> str | None:
        category_norm = normalize_for_match(category_hint)
        slug_norm = normalize_for_match(normalize_category_href_slug(category_href))
        title_norm = normalize_for_match(title)
        canonical_norm = (canonical_url or "").strip().lower()
        if (
            "entoichiz" in title_norm
            or "built in" in title_norm
            or "ano pagkou" in title_norm
            or "entoichiz" in canonical_norm
            or "ano-pagou" in canonical_norm
        ):
            return "built_in_appliance"
        for family, config in SKROUTZ_FAMILIES.items():
            labels = {normalize_for_match(label) for label in config.get("category_labels", set())}
            href_tokens = {normalize_for_match(token) for token in config.get("category_href_tokens", set())}
            if labels and category_norm in labels:
                return family
            if href_tokens and any(token and token in slug_norm for token in href_tokens):
                return family
        for family, config in SKROUTZ_FAMILIES.items():
            title_tokens = {normalize_for_match(token) for token in config.get("title_tokens", set())}
            if title_tokens and any(token and token in title_norm for token in title_tokens):
                return family
            if family == "soundbar" and "soundbar" in title_norm:
                return family
            if family == "coffee_filter" and "καφετιερ" in title_norm and "φιλτρ" in title_norm:
                return family
            if family == "kettle" and "βραστηρ" in title_norm:
                return family
        return None

    def _extract_brand(self, soup: BeautifulSoup, jsonld: dict[str, Any], title: str, merchant_titles: list[str]) -> tuple[str, str, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        for selector in ["a.brand-page-link img", "a.brand-page-link span"]:
            node = soup.select_one(selector)
            trace.append(self._trace("dom", selector, [node] if node else [], node))
            if not node:
                continue
            value = normalize_whitespace(node.get("alt") if node.name == "img" else safe_text(node)).replace(" στο Skroutz", "").strip()
            if value:
                return value, f"dom:{selector}", trace
        brand = jsonld.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")
        value = normalize_whitespace(brand)
        if value:
            return value, "jsonld:brand", trace
        fallback = self._derive_brand_from_titles([title, *merchant_titles])
        return (fallback, "heuristic:title_brand", trace) if fallback else ("", "missing", trace)

    def _derive_brand_from_titles(self, texts: list[str]) -> str:
        for text in texts:
            tokens = normalize_whitespace(text).split()
            if tokens and not NUMERIC_RE.fullmatch(tokens[0]):
                return tokens[0].strip(" -–/|,.;:()[]{}")
        return ""

    def _extract_page_sku(self, soup: BeautifulSoup, jsonld: dict[str, Any], url: str) -> tuple[str, str, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        node = soup.select_one("h1 small.sku-code")
        trace.append(self._trace("dom", "h1 small.sku-code", [node] if node else [], node))
        if node:
            match = re.search(r"([A-Z0-9.-]{3,})$", safe_text(node), re.IGNORECASE)
            if match:
                return match.group(1), "dom:h1 small.sku-code", trace
        value = normalize_whitespace(jsonld.get("sku"))
        if value:
            return value, "jsonld:sku", trace
        match = re.search(r"/s/(\d+)/", url)
        return (match.group(1), "url:path_sku", trace) if match else ("", "missing", trace)

    def _extract_mpn(self, soup: BeautifulSoup, jsonld: dict[str, Any], title: str, brand: str, product_code: str, merchant_titles: list[str]) -> tuple[str, str, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        value = normalize_whitespace(jsonld.get("mpn"))
        if value:
            return value, "jsonld:mpn", trace
        node = soup.select_one("#specs dt:-soup-contains('Κωδικός Προϊόντος') + dd")
        trace.append(self._trace("dom", "#specs dt:-soup-contains('Κωδικός Προϊόντος') + dd", [node] if node else [], node))
        if node and safe_text(node):
            return safe_text(node), "dom:#specs dt+dd", trace
        if product_code and not product_code.isdigit():
            return product_code, "heuristic:page_code", trace
        best = self._best_model_token([title, *merchant_titles], brand)
        return (best, "heuristic:model_token", trace) if best else ("", "missing", trace)

    def _extract_price(self, soup: BeautifulSoup, jsonld: dict[str, Any]) -> tuple[str, float | None, str, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        node = soup.select_one(".prices .final-price")
        trace.append(self._trace("dom", ".prices .final-price", [node] if node else [], node))
        if node:
            integer_part = safe_text(node.select_one(".integer-part"))
            decimal_part = safe_text(node.select_one(".decimal-part"))
            if integer_part and decimal_part:
                text = f"{integer_part},{decimal_part} €"
                try:
                    price = float(f"{integer_part}.{decimal_part}")
                except ValueError:
                    price = parse_euro_price(text)
                return text, price, "dom:.prices .final-price", trace
            text = safe_text(node)
            price = parse_euro_price(text)
            if price is not None:
                return text, price, "dom:.prices .final-price", trace
        offers = jsonld.get("offers") or {}
        price_value = offers.get("price")
        if price_value is not None:
            text = normalize_whitespace(str(price_value))
            try:
                numeric = float(str(price_value))
            except ValueError:
                numeric = parse_euro_price(text)
            return text, numeric, "jsonld:offers.price", trace
        return "", None, "missing", trace

    def _extract_summary_block(self, soup: BeautifulSoup) -> tuple[str, str, str, list[SelectorTraceEntry], list[tuple[str, str, str]]]:
        trace: list[SelectorTraceEntry] = []
        selectors = [".sku-description", "#description .simple-description", "div.summary .description.long", "div.summary .description.bullets"]
        for selector in selectors:
            node = soup.select_one(selector)
            trace.append(self._trace("dom", selector, [node] if node else [], node))
            if not node:
                continue
            segments = self._collect_summary_segments(node)
            pairs = self._extract_summary_pairs(node)
            supplemental = soup.select_one("div.summary .description.bullets")
            if supplemental is not None and supplemental is not node:
                for pair in self._extract_summary_pairs(supplemental):
                    if pair not in pairs:
                        pairs.append(pair)
            text = normalize_whitespace(" ".join(segments))
            if text or pairs:
                return str(node), text, f"dom:{selector}", trace, pairs
        return "", "", "missing", trace, []

    def _collect_summary_segments(self, node: Tag) -> list[str]:
        chunks: list[str] = []
        for body_text in node.select(".body-text"):
            text = safe_text(body_text)
            if text:
                chunks.append(text)
        if not chunks:
            for paragraph in node.find_all("p"):
                text = safe_text(paragraph)
                if text:
                    chunks.append(text)
        for item in node.find_all("li"):
            text = safe_text(item)
            if text and text not in chunks:
                chunks.append(text)
        if not chunks:
            text = safe_text(node)
            if text:
                chunks.append(text)
        return self._dedupe_preserve_order(chunks)

    def _extract_summary_pairs(self, node: Tag) -> list[tuple[str, str, str]]:
        pairs: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        chunks: list[str] = []
        for text_node in [*node.select(".body-text"), *node.find_all("li"), *node.find_all("p")]:
            text = safe_text(text_node)
            if text:
                chunks.append(text)
        for chunk in chunks:
            for label, value in self._scan_pairs(chunk):
                key = (normalize_for_match(label), normalize_for_match(value))
                if not key[0] or key in seen:
                    continue
                seen.add(key)
                pairs.append(("Σύνοψη", label, value))
        return pairs

    def _scan_pairs(self, text: str) -> list[tuple[str, str]]:
        normalized = normalize_whitespace(text)
        if not normalized or ":" not in normalized:
            return []
        pairs: list[tuple[str, str]] = []
        for label, value in SUMMARY_PAIR_RE.findall(normalized):
            clean_label = normalize_whitespace(label)
            clean_value = normalize_whitespace(value)
            if clean_label and clean_value:
                pairs.append((clean_label, clean_value))
        return pairs

    def _extract_raw_specs(self, soup: BeautifulSoup) -> tuple[list[SpecSection], list[tuple[str, str, str]], str, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        containers = soup.select("#specs .spec-groups, #combined-specs-content .spec-groups")
        trace.append(self._trace("dom", "#specs .spec-groups", containers, containers[0] if containers else None))
        if not containers:
            return [], [], "missing", trace

        sections: list[SpecSection] = []
        flat_pairs: list[tuple[str, str, str]] = []
        seen_pairs: set[tuple[str, str, str]] = set()
        for container in containers:
            for detail in container.find_all("div", class_="spec-details", recursive=False):
                section_title = safe_text(detail.find("h3", recursive=False)) or "Γενικά"
                items: list[SpecItem] = []
                for block in detail.find_all("dl", recursive=False):
                    dt = block.find("dt", recursive=False)
                    dd = block.find("dd", recursive=False)
                    label = safe_text(dt)
                    value = safe_text(dd)
                    if not label or not value:
                        continue
                    pair_key = (section_title, label, value)
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    items.append(SpecItem(label=label, value=value))
                    flat_pairs.append(pair_key)
                if items:
                    sections.append(SpecSection(section=section_title, items=items))
        return sections, flat_pairs, "dom:#specs .spec-groups", trace

    def _extract_gallery_images(self, soup: BeautifulSoup, jsonld: dict[str, Any], url: str, title: str) -> tuple[list[GalleryImage], str, list[SelectorTraceEntry]]:
        trace: list[SelectorTraceEntry] = []
        images = jsonld.get("image")
        urls: list[str] = []
        if isinstance(images, list):
            urls.extend(make_absolute_url(item, url) for item in images if item)
        elif isinstance(images, str) and images:
            urls.append(make_absolute_url(images, url))
        if urls:
            normalized = dedupe_urls_preserve_order(urls)
            return [GalleryImage(url=item, alt=title, position=index) for index, item in enumerate(normalized, start=1)], "jsonld:image", trace

        nodes = soup.select("img[data-modal-data], img[data-sku-page--gallery--swipe-gallery-target='image']")
        trace.append(self._trace("dom", "img[data-modal-data]", nodes, nodes[0] if nodes else None))
        for node in nodes:
            src = node.get("data-fallback-src") or node.get("data-src") or node.get("src") or ""
            if src:
                urls.append(make_absolute_url(src, url))
        normalized = dedupe_urls_preserve_order(urls)
        return [GalleryImage(url=item, alt=title, position=index) for index, item in enumerate(normalized, start=1)], "dom:img[data-modal-data]", trace

    def _find_energy_class(self, sections: list[SpecSection]) -> str:
        for section in sections:
            for item in section.items:
                if normalize_for_match(item.label) in {normalize_for_match("Ενεργειακή Κλάση"), normalize_for_match("Ενεργειακή κλάση")}:
                    return normalize_whitespace(item.value or "")
        return ""

    def _build_bsh_energy_label_icon_url(self, brand: str, energy_class: str) -> str:
        if normalize_for_match(brand) not in {normalize_for_match("Bosch"), normalize_for_match("Neff")}:
            return ""
        suffix = self._bsh_energy_class_icon_suffix(energy_class)
        if not suffix:
            return ""
        return f"https://media3.bsh-group.com/Feature_Icons/100x/21143877_ENERGY_CLASS_ICON_2010_{suffix}.webp"

    def _build_bsh_energy_label_pdf_url(self, brand: str, mpn: str) -> str:
        normalized_brand = normalize_for_match(brand)
        normalized_mpn = normalize_whitespace(mpn)
        if not normalized_mpn:
            return ""
        if normalized_brand == normalize_for_match("Bosch"):
            return f"https://media3.bsh-group.com/Documents/energylabel/el-GR/{normalized_mpn}.pdf"
        if normalized_brand == normalize_for_match("Neff"):
            return f"https://media3.neff-international.com/Documents/energylabel/el-GR/{normalized_mpn}.pdf"
        return ""

    def _bsh_energy_class_icon_suffix(self, energy_class: str) -> str:
        normalized = normalize_whitespace(energy_class).upper().replace(" ", "")
        if not normalized:
            return ""
        return normalized.replace("+", "_PLUS").replace("-", "_MINUS")

    def _extract_merchant_titles(self, soup: BeautifulSoup) -> list[str]:
        titles = [normalize_whitespace(node.get("title") or safe_text(node)) for node in soup.select("#prices .product-name[title], .selected-product-cards .product-name[title]")]
        return self._dedupe_preserve_order([title for title in titles if title])

    def _best_model_token(self, texts: list[str], brand: str) -> str:
        brand_norm = normalize_for_match(brand)
        best = ""
        best_score = 0
        for text in texts:
            for raw in normalize_whitespace(text).split():
                token = raw.strip(" -–/|,.;:()[]{}")
                upper = token.upper()
                if not token or normalize_for_match(token) == brand_norm or not MODEL_TOKEN_RE.match(upper):
                    continue
                score = 10 + sum(bool(re.search(pattern, upper)) for pattern in [r"[A-Z]", r"\d"])
                score += len(upper)
                if score > best_score:
                    best = upper
                    best_score = score
        return best

    def _build_canonical_sections(
        self,
        family: str | None,
        brand: str,
        mpn: str,
        title: str,
        hero_summary: str,
        raw_sections: list[SpecSection],
        raw_pairs: list[tuple[str, str, str]],
        summary_pairs: list[tuple[str, str, str]],
        merchant_titles: list[str],
    ) -> list[SpecSection]:
        if family not in SKROUTZ_FAMILIES:
            return self._build_generic_sections(raw_sections, summary_pairs)
        lookup = self._build_label_lookup(raw_pairs, summary_pairs)
        full_text = normalize_whitespace(" ".join([title, hero_summary, *merchant_titles, *lookup.values()]))
        family_config = SKROUTZ_FAMILIES[family]
        if family_config.get("spec_mode") == "raw":
            return self._build_generic_sections(raw_sections, summary_pairs)
        if family == "soundbar":
            return self._soundbar_sections(raw_pairs, merchant_titles)
        if family == "coffee_filter":
            section_values = self._coffee_values(lookup, full_text, merchant_titles)
        elif family == "kettle":
            section_values = self._kettle_values(lookup, title, full_text, merchant_titles)
        else:
            section_values = self._tabletop_hob_values(lookup, brand, mpn, title, full_text)

        out: list[SpecSection] = []
        for section_title, labels in SKROUTZ_FAMILIES[family]["sections"]:
            items = [SpecItem(label=label, value=section_values.get(label, "-")) for label in labels]
            out.append(SpecSection(section=section_title, items=items))
        return out

    def _build_generic_sections(self, raw_sections: list[SpecSection], summary_pairs: list[tuple[str, str, str]]) -> list[SpecSection]:
        if raw_sections:
            return raw_sections
        items = [SpecItem(label=label, value=value) for _, label, value in summary_pairs if label and value]
        return [SpecSection(section="Χαρακτηριστικά", items=items)] if items else []

    def _build_label_lookup(self, raw_pairs: list[tuple[str, str, str]], summary_pairs: list[tuple[str, str, str]]) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for _, label, value in [*raw_pairs, *summary_pairs]:
            normalized_label = normalize_for_match(label)
            normalized_value = normalize_whitespace(value)
            if normalized_label and normalized_value and normalized_label not in lookup:
                lookup[normalized_label] = normalized_value
        return lookup

    def _coffee_values(self, lookup: dict[str, str], full_text: str, merchant_titles: list[str]) -> dict[str, str]:
        normalized_text = normalize_for_match(full_text)
        dimensions = self._extract_dimensions_text(full_text, expected_parts=3)
        return {
            "Χωρητικότητα σε Φλυτζάνια": self._extract_cups(full_text) or self._normalize_cups(lookup.get(normalize_for_match("Χωρητικότητα Φλυτζάνια"))) or "-",
            "Υλικό Κανάτας": self._clean_placeholder(lookup.get(normalize_for_match("Υλικό Κανάτας")) or lookup.get(normalize_for_match("Κανάτα"))),
            "Ισχύς σε Watts": self._number_only(lookup.get(normalize_for_match("Ισχύς"))),
            "Χωρητικότητα Δοχείου Νερού σε Λίτρα": self._extract_capacity_from_titles(merchant_titles) or self._number_only(lookup.get(normalize_for_match("Χωρητικότητα lt"))),
            "Ένδειξη Στάθμης Νερού": self._bool_from_text(normalized_text, ["σταθμη", "νερου"]),
            "Αποσπώμενο Δοχείο Νερού": self._boolean_or_placeholder(lookup.get(normalize_for_match("Αποσπώμενο Δοχείο Νερού"))),
            "Θερμαινόμενη Βάση": self._boolean_or_placeholder(lookup.get(normalize_for_match("Θερμαινόμενη Βάση"))),
            "Ενδεικτική Λυχνία Λειτουργίας": self._boolean_or_placeholder(lookup.get(normalize_for_match("Ενδεικτική Λυχνία Λειτουργίας"))),
            "Ηχητικό Σήμα Ειδοποίησης": self._boolean_or_placeholder(lookup.get(normalize_for_match("Ηχητικό Σήμα Ειδοποίησης"))),
            "Αποθήκευση Καλωδίου": self._boolean_or_placeholder(lookup.get(normalize_for_match("Αποθήκευση Καλωδίου"))),
            "Διακοπή Σταξίματος": self._bool_from_text(normalized_text, ["σταξ"]),
            "Λειτουργία Aroma": self._boolean_or_placeholder(lookup.get(normalize_for_match("Λειτουργία Aroma"))),
            "Αυτόματη Διακοπή Λειτουργίας": self._bool_from_text(normalized_text, ["αυτοματ"]),
            "Χρονοδιακόπτης Λειτουργίας": self._boolean_or_placeholder(lookup.get(normalize_for_match("Χρονοδιακόπτης Λειτουργίας"))),
            "Χρώμα": self._clean_placeholder(lookup.get(normalize_for_match("Χρώμα"))),
            "Βάρος Συσκευής σε Κιλά": self._extract_weight(full_text),
            "Διαστάσεις Συσκευής σε Εκατοστά. (Υ χ Π χ Β": dimensions or "-",
            "Εγγύηση Κατασκευαστή": self._extract_warranty(full_text),
        }

    def _kettle_values(self, lookup: dict[str, str], title: str, full_text: str, merchant_titles: list[str]) -> dict[str, str]:
        normalized_text = normalize_for_match(full_text)
        dimensions = self._extract_dimensions_text(" ".join(merchant_titles + [full_text]), expected_parts=3)
        return {
            "Χωρητικότητα σε Λίτρα": self._number_only(lookup.get(normalize_for_match("Χωρητικότητα"))),
            "Ισχύς σε Watts": self._number_only(lookup.get(normalize_for_match("Ισχύς"))),
            "Αποσπώμενη Βάση": self._boolean_or_placeholder(lookup.get(normalize_for_match("Αποσπώμενη Βάση"))),
            "Βάση 360 Μοιρών": self._bool_from_text(normalized_text, ["360"]),
            "Φίλτρο Νερού": self._clean_placeholder(lookup.get(normalize_for_match("Φίλτρο Νερού")) or lookup.get(normalize_for_match("Είδος Φίλτρου"))),
            "Άνοιγμα του Καπακιού με το Πάτημα ενός Κουμπιού": self._bool_from_text(normalized_text, ["καπακ", "κουμπ"]),
            "Καλυμμένη Αντίσταση": self._boolean_or_placeholder(lookup.get(normalize_for_match("Καλυμμένη Αντίσταση"))),
            "Υλικό Κατασκευής": self._clean_placeholder(lookup.get(normalize_for_match("Υλικό Κανάτας"))),
            "Αποθήκευση Καλωδίου": self._bool_from_text(normalized_text, ["καλωδι"]),
            "Ένδειξη Στάθμης Νερού": self._bool_from_text(normalized_text, ["σταθμη"]),
            "Ένδειξη Λειτουργίας": self._bool_from_text(normalized_text, ["λυχνι"]),
            "Ηχητικό Σήμα Ειδοποίησης": self._boolean_or_placeholder(lookup.get(normalize_for_match("Ηχητικό Σήμα Ειδοποίησης"))),
            "Επιλογές Θερμοκρασίας Βρασμού": self._boolean_or_placeholder(lookup.get(normalize_for_match("Επιλογή Θερμοκρασίας"))),
            "Λειτουργία Διατήρησης Θερμοκρασίας": self._boolean_or_placeholder(lookup.get(normalize_for_match("Διατήρηση Θερμοκρασίας"))),
            "Αυτόματος Τερματισμός Λειτουργίας": self._bool_from_text(normalized_text, ["αυτοματ"]),
            "Προστασία από Βρασμό Χωρίς Νερό": self._boolean_or_placeholder(lookup.get(normalize_for_match("Προστασία από Βρασμό Χωρίς Νερό"))),
            "Χρώμα": self._clean_placeholder(lookup.get(normalize_for_match("Χρώμα"))),
            "Βάρος Συσκευής σε Κιλά": self._extract_weight(full_text),
            "Διαστάσεις Συσκευής σε Εκατοστά. (Υ χ Π χ Β": dimensions or "-",
            "Εγγύηση Κατασκευαστή": self._extract_warranty(full_text),
            "_title_color_suffix": self._title_color_suffix(title, lookup.get(normalize_for_match("Χρώμα"))),
        }

    def _tabletop_hob_values(self, lookup: dict[str, str], brand: str, mpn: str, title: str, full_text: str) -> dict[str, str]:
        normalized_title = normalize_for_match(title)
        width, depth = self._extract_dimensions_2(full_text)
        surface = self._clean_placeholder(lookup.get(normalize_for_match("Τύπος Εστίας")))
        if surface == "-" and "εμαγι" in normalized_title:
            surface = "Εμαγιέ"
        count = self._number_only(lookup.get(normalize_for_match("Εστίες")))
        return {
            "Κατασκευαστής": brand or "-",
            "Μοντέλο": mpn or "-",
            "Εστία": self._render_hob_type(count),
            "Πλάτος": f"{width} cm" if width else "-",
            "Βάθος": f"{depth} cm" if depth else "-",
            "_Ισχύς": self._number_only(lookup.get(normalize_for_match("Ισχύς"))),
            "_Τύπος Εστίας": surface,
            "_Εστίες": count or "-",
            "_Χρώμα": self._clean_placeholder(lookup.get(normalize_for_match("Χρώμα"))),
            "_Είδος Διακόπτη": self._clean_placeholder(lookup.get(normalize_for_match("Είδος Διακόπτη"))),
        }

    def _build_key_specs(
        self,
        family: str | None,
        sections: list[SpecSection],
        raw_sections: list[SpecSection],
        raw_pairs: list[tuple[str, str, str]],
        summary_pairs: list[tuple[str, str, str]],
    ) -> list[SpecItem]:
        if not sections:
            return []
        if not family or SKROUTZ_FAMILIES.get(family, {}).get("spec_mode") == "raw":
            return self._build_generic_key_specs(raw_sections or sections, summary_pairs)
        lookup = {item.label: item.value or "-" for section in sections for item in section.items}
        supplemental_lookup = self._build_label_lookup(raw_pairs, summary_pairs)
        selected_labels = {
            "soundbar": ["Κανάλια", "Πρότυπα Ήχου", "Συνδεσιμότητα", "Subwoofer", "Χρώμα", "Ισχύς"],
            "coffee_filter": ["Χωρητικότητα σε Φλυτζάνια", "Χωρητικότητα Δοχείου Νερού σε Λίτρα", "Ισχύς σε Watts", "Υλικό Κανάτας", "Χρώμα"],
            "kettle": ["Χωρητικότητα σε Λίτρα", "Ισχύς σε Watts", "Βάση 360 Μοιρών", "Υλικό Κατασκευής", "Χρώμα"],
            "tabletop_hob": ["Κατασκευαστής", "Μοντέλο", "Εστία", "Πλάτος", "Βάθος"],
        }[family]
        items = [SpecItem(label=label, value=lookup[label]) for label in selected_labels if lookup.get(label)]
        if family == "tabletop_hob":
            for label in ["Ισχύς", "Τύπος Εστίας", "Εστίες", "Χρώμα", "Είδος Διακόπτη"]:
                value = supplemental_lookup.get(normalize_for_match(label))
                if value:
                    items.append(SpecItem(label=label, value=value))
        return items

    def _build_generic_key_specs(self, sections: list[SpecSection], summary_pairs: list[tuple[str, str, str]]) -> list[SpecItem]:
        items: list[SpecItem] = []
        seen: set[str] = set()
        for section in sections:
            for item in section.items:
                label_norm = normalize_for_match(item.label)
                value = normalize_whitespace(item.value)
                if not label_norm or not value or label_norm in seen:
                    continue
                seen.add(label_norm)
                items.append(SpecItem(label=item.label, value=value))
                if len(items) >= 8:
                    return items
        for _, label, value in summary_pairs:
            label_norm = normalize_for_match(label)
            normalized_value = normalize_whitespace(value)
            if not label_norm or not normalized_value or label_norm in seen:
                continue
            seen.add(label_norm)
            items.append(SpecItem(label=label, value=normalized_value))
            if len(items) >= 8:
                break
        return items

    def _soundbar_sections(self, raw_pairs: list[tuple[str, str, str]], merchant_titles: list[str]) -> list[SpecSection]:
        grouped: dict[str, list[SpecItem]] = {}
        for section_title, label, value in raw_pairs:
            normalized_title = normalize_whitespace(section_title) or "Τεχνικά Χαρακτηριστικά"
            grouped.setdefault(normalized_title, []).append(SpecItem(label=label, value=value))
        derived_power = self._extract_soundbar_power(" ".join(merchant_titles))
        if derived_power:
            target_section = next(iter(grouped), "Χαρακτηριστικά")
            grouped.setdefault(target_section, []).append(SpecItem(label="Ισχύς", value=derived_power))
        return [SpecSection(section=title, items=items) for title, items in grouped.items()]

    def _extract_soundbar_power(self, text: str) -> str:
        matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*W\b", text or "", flags=re.IGNORECASE)
        if not matches:
            return ""
        numeric = max(float(value.replace(",", ".")) for value in matches)
        return f"{int(numeric)} W"

    def _extract_cups(self, text: str) -> str:
        match = CUPS_RE.search(text)
        return normalize_whitespace(match.group(1)).replace("-", " - ") if match else ""

    def _normalize_cups(self, value: str | None) -> str:
        normalized = normalize_whitespace(value)
        if not normalized:
            return ""
        match = CUPS_RE.search(normalized)
        if match:
            return normalize_whitespace(match.group(1)).replace("-", " - ")
        return self._number_only(normalized)

    def _extract_capacity_from_titles(self, merchant_titles: list[str]) -> str:
        for title in merchant_titles:
            match = CAPACITY_LT_RE.search(title)
            if match:
                return match.group(1).replace(".", ",")
        return ""

    def _extract_dimensions_text(self, text: str, expected_parts: int) -> str:
        for match in DIMENSIONS_RE.finditer(text):
            values = [part.replace(".", ",") for part in match.groups() if part]
            if len(values) == expected_parts:
                return " × ".join(values)
        return ""

    def _extract_dimensions_2(self, text: str) -> tuple[str, str]:
        for match in DIMENSIONS_RE.finditer(text):
            values = [part.replace(".", ",") for part in match.groups() if part]
            if len(values) >= 2:
                return values[0], values[1]
        return "", ""

    def _extract_weight(self, text: str) -> str:
        match = WEIGHT_RE.search(text)
        return match.group(1).replace(".", ",") if match else "-"

    def _extract_warranty(self, text: str) -> str:
        match = WARRANTY_RE.search(text)
        if not match:
            return "-"
        years = match.group(1)
        return f"{years} Χρόνια" if years != "1" else "1 Χρόνος"

    def _title_color_suffix(self, title: str, raw_color: str | None) -> str:
        color = self._clean_placeholder(raw_color)
        if color == "-":
            return ""
        if re.search(r"\bmat\b", title, flags=re.IGNORECASE):
            return f"{color} Ματ"
        return color

    def _number_only(self, value: str | None) -> str:
        if not value:
            return "-"
        match = NUMERIC_RE.search(value.replace("×", " "))
        return match.group(0).replace(".", ",") if match else normalize_whitespace(value)

    def _bool_from_text(self, normalized_text: str, tokens: list[str]) -> str:
        return "Ναι" if all(token in normalized_text for token in tokens) else "-"

    def _clean_placeholder(self, value: str | None) -> str:
        normalized = normalize_whitespace(value)
        return normalized if normalized else "-"

    def _boolean_or_placeholder(self, value: str | None) -> str:
        normalized = normalize_for_match(value)
        if normalized in {"ναι", "yes"}:
            return "Ναι"
        if normalized in {"οχι", "όχι", "no"}:
            return "Όχι"
        return normalize_whitespace(value) or "-"

    def _render_hob_type(self, count: str) -> str:
        if count == "2":
            return "Διπλή*"
        if count == "1":
            return "Μονή*"
        return count or "-"

    def _dedupe_preserve_order(self, values: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = normalize_whitespace(value)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out

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

    def _collect_critical_missing(self, source: SourceProductData, supported_page: bool) -> list[str]:
        critical: list[str] = []
        if not source.name:
            critical.append("name")
        if not source.brand:
            critical.append("brand")
        if not source.breadcrumbs:
            critical.append("breadcrumbs")
        if not source.gallery_images:
            critical.append("gallery_images")
        if not source.spec_sections:
            critical.append("spec_sections")
        if not supported_page:
            critical.append("supported_family")
        return sorted(set(critical))

    def _make_diagnostic(self, value: Any, selected_strategy: str, confidence: float, selector_trace: list[SelectorTraceEntry]) -> FieldDiagnostic:
        return FieldDiagnostic(confidence=round(confidence, 4), selected_strategy=selected_strategy, value_present=self._value_present(value), value_preview=self._preview_value(value), selector_trace=selector_trace)

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

    def _trace(self, strategy: str, selector: str, nodes: list[Tag], chosen: Tag | None) -> SelectorTraceEntry:
        return SelectorTraceEntry(strategy=strategy, selector=selector, match_count=len(nodes), success=chosen is not None, chosen_preview=safe_text(chosen)[:120] if chosen else "", note="")
