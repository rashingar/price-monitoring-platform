from __future__ import annotations

import inspect
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from bs4 import BeautifulSoup, Tag

from .models import SourceProductData, SpecItem, SpecSection, TaxonomyResolution
from .normalize import make_absolute_url, normalize_for_match, normalize_whitespace
from .repo_paths import MANUFACTURER_SOURCE_MAP_PATH
from .utils import dedupe_strings, ensure_directory, read_json, write_bytes, write_text

try:  # pragma: no cover - dependency availability is environment-dependent
    from pypdf import PdfReader
except Exception as exc:  # pragma: no cover - dependency availability is environment-dependent
    PdfReader = None
    PDF_IMPORT_ERROR = str(exc)
else:  # pragma: no cover - simple import success branch
    PDF_IMPORT_ERROR = ""


NEFF_SPECSHEET_URL = "https://media3.neff-international.com/Documents/specsheet/el-GR/{mpn}.pdf"
BOSCH_SPECSHEET_URL = "https://media3.bosch-home.com/Documents/specsheet/el-GR/{mpn}.pdf"
TEFAL_SHOP_BASE_URL = "https://shop.tefal.gr/"
TEFAL_SHOP_SEARCH_URL = (
    "https://shop.tefal.gr/search/suggest.json"
    "?q={query}&resources[type]=product&resources[limit]=10&section_id=predictive-search"
)
PDF_HEADINGS = {
    "Χαρακτηριστικά",
    "Τεχνικά στοιχεία",
    "Τεχνικά χαρακτηριστικά",
    "Γενικά χαρακτηριστικά",
    "Διαστάσεις",
    "Σχέδια διαστάσεων",
}
BOSCH_SECTION_TITLES = {
    "Τεχνικά στοιχεία",
    "Τεχνικά Χαρακτηριστικά",
    "Γενικά χαρακτηριστικά",
    "Στη συντήρηση",
    "Στην κατάψυξη",
    "Διαστάσεις Συσκευής",
}


@dataclass(slots=True)
class OfficialDocumentCandidate:
    provider_id: str
    document_type: str
    url: str
    name: str = "document"
    content_type_hint: str = ""
    priority: int = 100
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EnrichmentResult:
    manufacturer_spec_sections: list[SpecSection] = field(default_factory=list)
    manufacturer_source_text: str = ""
    hero_summary: str = ""
    presentation_source_html: str = ""
    presentation_source_text: str = ""
    warnings: list[str] = field(default_factory=list)


class OfficialDocAdapter:
    provider_id = ""

    def matches(self, source: SourceProductData) -> bool:
        raise NotImplementedError

    def discover(self, source: SourceProductData, taxonomy: TaxonomyResolution, fetcher=None) -> list[OfficialDocumentCandidate]:
        raise NotImplementedError

    def parse(self, candidate: OfficialDocumentCandidate, payload: bytes | str, source: SourceProductData, taxonomy: TaxonomyResolution) -> EnrichmentResult:
        raise NotImplementedError


class _StaticPdfAdapter(OfficialDocAdapter):
    url_template = ""
    parser = staticmethod(lambda _text: [])

    def matches(self, source: SourceProductData) -> bool:
        return bool(normalize_whitespace(source.mpn))

    def discover(self, source: SourceProductData, taxonomy: TaxonomyResolution, fetcher=None) -> list[OfficialDocumentCandidate]:
        mpn = normalize_whitespace(source.mpn)
        if not mpn or not self.url_template:
            return []
        return [
            OfficialDocumentCandidate(
                provider_id=self.provider_id,
                document_type="pdf",
                url=self.url_template.format(mpn=mpn),
                name="specsheet",
                content_type_hint="application/pdf",
                priority=10,
            )
        ]

    def parse(self, candidate: OfficialDocumentCandidate, payload: bytes | str, source: SourceProductData, taxonomy: TaxonomyResolution) -> EnrichmentResult:
        if PdfReader is None:
            raise RuntimeError(f"manufacturer_pdf_parser_unavailable:{PDF_IMPORT_ERROR}")
        if not isinstance(payload, (bytes, bytearray)):
            raise RuntimeError("manufacturer_pdf_payload_invalid")
        text = _extract_pdf_text(bytes(payload))
        sections = self.parser(text)
        return EnrichmentResult(
            manufacturer_spec_sections=sections,
            manufacturer_source_text=normalize_whitespace(text),
        )


class BoschSpecsheetAdapter(_StaticPdfAdapter):
    provider_id = "bosch"
    url_template = BOSCH_SPECSHEET_URL
    parser = staticmethod(lambda text: _parse_bosch_specsheet(text))

    def matches(self, source: SourceProductData) -> bool:
        return normalize_for_match(source.brand) == normalize_for_match("Bosch") and super().matches(source)


class NeffSpecsheetAdapter(_StaticPdfAdapter):
    provider_id = "neff"
    url_template = NEFF_SPECSHEET_URL
    parser = staticmethod(lambda text: _parse_neff_specsheet(text))

    def matches(self, source: SourceProductData) -> bool:
        return normalize_for_match(source.brand) == normalize_for_match("Neff") and super().matches(source)


class TefalShopAdapter(OfficialDocAdapter):
    provider_id = "tefal_shop"

    def matches(self, source: SourceProductData) -> bool:
        return normalize_for_match(source.brand) == normalize_for_match("Tefal") and bool(normalize_whitespace(source.mpn))

    def discover(self, source: SourceProductData, taxonomy: TaxonomyResolution, fetcher=None) -> list[OfficialDocumentCandidate]:
        del taxonomy
        if fetcher is None:
            raise RuntimeError("manufacturer_fetcher_required")

        mpn = normalize_whitespace(source.mpn)
        if not mpn:
            return []

        ranked: list[tuple[int, OfficialDocumentCandidate]] = []
        for product_url in _discover_tefal_shop_urls_from_sitemaps(source, fetcher):
            score = _score_tefal_shop_url(source, product_url)
            if score <= 0:
                continue
            ranked.append(
                (
                    score,
                    OfficialDocumentCandidate(
                        provider_id=self.provider_id,
                        document_type="html",
                        url=product_url,
                        name="product_page",
                        content_type_hint="text/html",
                        priority=max(1, 100 - score),
                    ),
                )
            )

        ranked.sort(key=lambda item: (-item[0], item[1].url))
        return [candidate for _, candidate in ranked[:3]]

    def parse(self, candidate: OfficialDocumentCandidate, payload: bytes | str, source: SourceProductData, taxonomy: TaxonomyResolution) -> EnrichmentResult:
        del source, taxonomy
        if not isinstance(payload, str):
            raise RuntimeError("manufacturer_html_payload_invalid")
        return _parse_tefal_shop_product_page(payload, search_body_html=str(candidate.metadata.get("search_body_html", "")))


class ManufacturerMappedHtmlAdapter(OfficialDocAdapter):
    provider_id = "mapped_html"

    def matches(self, source: SourceProductData) -> bool:
        return bool(self._matching_entries(source))

    def discover(self, source: SourceProductData, taxonomy: TaxonomyResolution, fetcher=None) -> list[OfficialDocumentCandidate]:
        del taxonomy, fetcher
        candidates: list[OfficialDocumentCandidate] = []
        for entry in self._matching_entries(source):
            candidates.append(
                OfficialDocumentCandidate(
                    provider_id=str(entry.get("provider_id", self.provider_id)).strip() or self.provider_id,
                    document_type="html",
                    url=str(entry.get("url", "")).strip(),
                    name=str(entry.get("name", "product_page")).strip() or "product_page",
                    content_type_hint=str(entry.get("content_type_hint", "text/html")).strip() or "text/html",
                    priority=int(entry.get("priority", 20) or 20),
                )
            )
        return candidates

    def parse(self, candidate: OfficialDocumentCandidate, payload: bytes | str, source: SourceProductData, taxonomy: TaxonomyResolution) -> EnrichmentResult:
        del candidate, source, taxonomy
        if not isinstance(payload, str):
            raise RuntimeError("manufacturer_html_payload_invalid")
        return _parse_tefal_shop_product_page(payload)

    def _matching_entries(self, source: SourceProductData) -> list[dict[str, Any]]:
        brand = normalize_for_match(source.brand)
        mpn = normalize_for_match(source.mpn)
        matches: list[dict[str, Any]] = []
        for entry in _load_mapped_product_pages():
            entry_brand = normalize_for_match(entry.get("brand", ""))
            entry_mpn = normalize_for_match(entry.get("mpn", ""))
            if entry_brand and entry_brand != brand:
                continue
            if entry_mpn and entry_mpn != mpn:
                continue
            if not normalize_whitespace(entry.get("url", "")):
                continue
            matches.append(entry)
        return matches


def get_official_doc_adapters() -> list[OfficialDocAdapter]:
    return [BoschSpecsheetAdapter(), NeffSpecsheetAdapter(), TefalShopAdapter(), ManufacturerMappedHtmlAdapter()]


def _adapter_accepts_fetcher_argument(adapter: OfficialDocAdapter) -> bool:
    try:
        signature = inspect.signature(adapter.discover)
    except (TypeError, ValueError):
        return True
    if "fetcher" in signature.parameters:
        return True
    return any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def enrich_source_from_manufacturer_docs(
    source: SourceProductData,
    taxonomy: TaxonomyResolution,
    fetcher,
    output_dir: str | Path,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "applied": False,
        "provider": "",
        "providers_considered": [],
        "matched_providers": [],
        "documents": [],
        "documents_discovered": 0,
        "documents_parsed": 0,
        "warnings": [],
        "section_count": 0,
        "field_count": 0,
        "hero_summary_applied": False,
        "presentation_applied": False,
        "presentation_block_count": 0,
        "fallback_reason": "",
    }
    source.manufacturer_spec_sections = []
    source.manufacturer_source_text = ""
    source.manufacturer_documents = []

    if normalize_for_match(source.source_name) != "skroutz":
        diagnostics["fallback_reason"] = "not_applicable_non_skroutz"
        return diagnostics

    adapters = get_official_doc_adapters()
    diagnostics["providers_considered"] = [adapter.provider_id for adapter in adapters]
    matched_adapters = [adapter for adapter in adapters if adapter.matches(source)]
    diagnostics["matched_providers"] = [adapter.provider_id for adapter in matched_adapters]
    diagnostics["provider"] = ",".join(diagnostics["matched_providers"])

    if not normalize_whitespace(source.mpn):
        diagnostics["fallback_reason"] = "missing_mpn"
        return diagnostics
    if not matched_adapters:
        diagnostics["fallback_reason"] = "no_matching_provider"
        return diagnostics

    provider_dir = ensure_directory(output_dir)
    merged_sections: list[SpecSection] = []
    merged_text_parts: list[str] = []
    successful_providers: list[str] = []
    enriched_hero_summary = ""
    enriched_presentation_html = ""
    enriched_presentation_text = ""
    enriched_presentation_blocks = 0

    for adapter in matched_adapters:
        try:
            if _adapter_accepts_fetcher_argument(adapter):
                discovered = adapter.discover(source, taxonomy, fetcher=fetcher)
            else:
                discovered = adapter.discover(source, taxonomy)
            candidates = sorted(
                discovered,
                key=lambda candidate: (candidate.priority, candidate.name, candidate.url),
            )
        except Exception as exc:
            diagnostics["warnings"].append(f"manufacturer_doc_discover_failed:{adapter.provider_id}:{exc}")
            continue
        diagnostics["documents_discovered"] += len(candidates)
        for index, candidate in enumerate(candidates, start=1):
            document_entry = _create_document_entry(candidate)
            diagnostics["documents"].append(document_entry)
            try:
                payload, content_type, final_url = _fetch_candidate(fetcher, candidate)
            except Exception as exc:
                document_entry["warnings"].append(f"fetch_failed:{exc}")
                diagnostics["warnings"].append(f"manufacturer_doc_fetch_failed:{candidate.name}")
                continue

            document_entry["available"] = True
            document_entry["content_type"] = content_type
            document_entry["final_url"] = final_url
            local_path = _write_document_payload(provider_dir, candidate, payload, index)
            document_entry["local_path"] = str(local_path)

            try:
                result = adapter.parse(candidate, payload, source, taxonomy)
            except Exception as exc:
                document_entry["warnings"].append(f"parse_failed:{exc}")
                diagnostics["warnings"].append(f"manufacturer_doc_parse_failed:{candidate.name}")
                continue

            text_payload = normalize_whitespace(result.manufacturer_source_text) or _fallback_document_text(candidate, payload)
            if text_payload:
                text_path = provider_dir / f"{local_path.stem}.txt"
                write_text(text_path, text_payload)
                document_entry["text_path"] = str(text_path)

            parsed_sections = _dedupe_sections(result.manufacturer_spec_sections)
            section_count = len(parsed_sections)
            field_count = sum(len(section.items) for section in parsed_sections)

            document_entry["parsed"] = field_count > 0
            document_entry["section_count"] = section_count
            document_entry["field_count"] = field_count
            document_entry["warnings"].extend(result.warnings)

            if not field_count:
                continue

            diagnostics["documents_parsed"] += 1
            successful_providers.append(adapter.provider_id)
            merged_sections = _merge_sections(merged_sections, parsed_sections)
            if text_payload:
                merged_text_parts.append(text_payload)
            hero_summary = normalize_whitespace(result.hero_summary)
            if hero_summary and len(hero_summary) > len(enriched_hero_summary):
                enriched_hero_summary = hero_summary
            presentation_blocks = _count_presentation_blocks(result.presentation_source_html, result.presentation_source_text)
            if presentation_blocks > enriched_presentation_blocks:
                enriched_presentation_blocks = presentation_blocks
                enriched_presentation_html = result.presentation_source_html
                enriched_presentation_text = result.presentation_source_text

    merged_text = normalize_whitespace(" ".join(part for part in merged_text_parts if part))
    source.manufacturer_spec_sections = merged_sections
    source.manufacturer_source_text = merged_text
    source.manufacturer_documents = diagnostics["documents"]
    if enriched_hero_summary:
        source.hero_summary = enriched_hero_summary
        diagnostics["hero_summary_applied"] = True
    if enriched_presentation_blocks:
        source.presentation_source_html = enriched_presentation_html
        source.presentation_source_text = enriched_presentation_text
        diagnostics["presentation_applied"] = True
        diagnostics["presentation_block_count"] = enriched_presentation_blocks

    diagnostics["provider"] = ",".join(dedupe_strings(successful_providers or diagnostics["matched_providers"]))
    diagnostics["section_count"] = len(merged_sections)
    diagnostics["field_count"] = sum(len(section.items) for section in merged_sections)
    diagnostics["applied"] = diagnostics["field_count"] > 0

    if not diagnostics["applied"] and not diagnostics["fallback_reason"]:
        if diagnostics["documents_discovered"] == 0:
            diagnostics["fallback_reason"] = "no_documents_discovered"
        elif diagnostics["documents_parsed"] == 0:
            diagnostics["fallback_reason"] = "no_documents_parsed"

    return diagnostics


def _create_document_entry(candidate: OfficialDocumentCandidate) -> dict[str, Any]:
    return {
        "name": candidate.name,
        "provider_id": candidate.provider_id,
        "document_type": candidate.document_type,
        "url": candidate.url,
        "final_url": candidate.url,
        "content_type_hint": candidate.content_type_hint,
        "local_path": "",
        "text_path": "",
        "content_type": "",
        "available": False,
        "parsed": False,
        "field_count": 0,
        "section_count": 0,
        "warnings": [],
    }


def _fetch_candidate(fetcher, candidate: OfficialDocumentCandidate) -> tuple[bytes | str, str, str]:
    document_type = normalize_for_match(candidate.document_type)
    if document_type == "pdf":
        payload, content_type = fetcher.fetch_binary(candidate.url)
        return payload, content_type, candidate.url
    if document_type == "html":
        fetch = fetcher.fetch_playwright(candidate.url)
        return fetch.html, "text/html", fetch.final_url
    raise RuntimeError(f"unsupported_document_type:{candidate.document_type}")


def _write_document_payload(output_dir: Path, candidate: OfficialDocumentCandidate, payload: bytes | str, index: int) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", candidate.name or f"document_{index}").strip("._") or f"document_{index}"
    if index > 1:
        safe_name = f"{safe_name}_{index}"
    suffix = ".pdf" if normalize_for_match(candidate.document_type) == "pdf" else ".html"
    local_path = output_dir / f"{safe_name}{suffix}"
    if isinstance(payload, (bytes, bytearray)):
        write_bytes(local_path, bytes(payload))
    else:
        write_text(local_path, str(payload))
    return local_path


def _fallback_document_text(candidate: OfficialDocumentCandidate, payload: bytes | str) -> str:
    if normalize_for_match(candidate.document_type) == "html" and isinstance(payload, str):
        return _extract_html_text(payload)
    return ""


def _load_mapped_product_pages() -> list[dict[str, Any]]:
    try:
        payload = read_json(MANUFACTURER_SOURCE_MAP_PATH)
    except FileNotFoundError:
        return []
    entries = payload.get("product_pages", [])
    return [entry for entry in entries if isinstance(entry, dict)]


def _merge_sections(existing: list[SpecSection], incoming: list[SpecSection]) -> list[SpecSection]:
    grouped: dict[str, list[SpecItem]] = {}
    ordered_titles: list[str] = []
    for section in [*existing, *incoming]:
        title = normalize_whitespace(section.section)
        if not title:
            continue
        key = normalize_for_match(title)
        if key not in grouped:
            grouped[key] = []
            ordered_titles.append(title)
        grouped[key].extend(section.items)
    return [SpecSection(section=title, items=_dedupe_items(grouped[normalize_for_match(title)])) for title in ordered_titles]


def _dedupe_sections(sections: list[SpecSection]) -> list[SpecSection]:
    return _merge_sections([], sections)


def _extract_pdf_text(payload: bytes) -> str:
    reader = PdfReader(io.BytesIO(payload))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_html_text(html: str) -> str:
    return normalize_whitespace(BeautifulSoup(html, "lxml").get_text(" ", strip=True))


def _parse_tefal_shop_product_html(html: str) -> list[SpecSection]:
    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one("[data-tab-content='about-the-product']")
    if container is None:
        return []

    items: list[SpecItem] = []
    for row in container.select("div.u-flex.u-justify-between.u-items-center.u-py-16.u-border-b"):
        label_node = row.select_one("span")
        value_node = row.select_one("div.t-text")
        label = normalize_whitespace(label_node.get_text(" ", strip=True) if label_node else "")
        value = normalize_whitespace(value_node.get_text(" ", strip=True) if value_node else "")
        if not label or not value:
            continue
        items.append(SpecItem(label=label, value=value))

    if not items:
        return []
    return [SpecSection(section="Χαρακτηριστικά Κατασκευαστή", items=_dedupe_items(items))]


def _parse_neff_specsheet(text: str) -> list[SpecSection]:
    lines = _normalize_pdf_lines(text)
    grouped: dict[str, list[SpecItem]] = {}
    current_section = "Κατασκευαστής"

    for line in lines:
        if line in PDF_HEADINGS:
            current_section = line
            continue
        label, value = _split_label_value(line)
        if not label or not value:
            continue
        grouped.setdefault(current_section, []).append(SpecItem(label=label, value=value))

    return [SpecSection(section=section, items=_dedupe_items(items)) for section, items in grouped.items() if items]


def _parse_bosch_specsheet(text: str) -> list[SpecSection]:
    lines = _normalize_bosch_pdf_lines(text)
    grouped: dict[str, list[SpecItem]] = {}
    current_section = "Κατασκευαστής"

    for line in lines:
        if line in BOSCH_SECTION_TITLES:
            current_section = line
            continue
        if line.startswith("- "):
            label, value = _split_label_value(line[2:].strip())
            if label and value:
                grouped.setdefault(current_section, []).append(SpecItem(label=label, value=value))
            else:
                grouped.setdefault(current_section, []).append(SpecItem(label="Ξ£Ξ·ΞΌΞµΞ―Ο‰ΟƒΞ·", value=line[2:].strip()))
            continue
        label, value = _split_label_value(line)
        if label and value:
            grouped.setdefault(current_section, []).append(SpecItem(label=label, value=value))

    return [SpecSection(section=section, items=_dedupe_items(items)) for section, items in grouped.items() if items]


def _normalize_bosch_pdf_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = normalize_whitespace(raw_line)
        line = re.sub(r"\.{2,}", " ", line)
        if not line or re.fullmatch(r"\d+\s*/", line):
            continue
        if line.startswith("Σειρά ") or line == "1 /" or line == "2 /" or line == "3 /":
            continue
        if line.startswith("Ο ψυγειοκαταψύκτης ") or line.startswith("• "):
            continue
        lines.append(line)
    return lines


def _normalize_pdf_lines(text: str) -> list[str]:
    raw_lines: list[str] = []
    for raw_line in text.splitlines():
        line = normalize_whitespace(raw_line.replace("\uf0b7", "•").replace("√", ""))
        line = re.sub(r"\.{2,}", " ", line)
        if not line or re.fullmatch(r"\d+\s*/", line):
            continue
        raw_lines.append(line)

    combined: list[str] = []
    for line in raw_lines:
        if line.startswith("• :") and combined:
            combined[-1] = normalize_whitespace(f"{combined[-1].rstrip(':')} {line[3:].lstrip(': ').strip()}")
            continue
        if combined and _should_join_pdf_line(combined[-1], line):
            combined[-1] = normalize_whitespace(f"{combined[-1]} {line}")
            continue
        combined.append(line)

    return [line for line in combined if not _ignore_pdf_line(line)]


def _should_join_pdf_line(previous: str, current: str) -> bool:
    if current in PDF_HEADINGS or previous in PDF_HEADINGS:
        return False
    if current.startswith("• "):
        return False
    if re.fullmatch(r"\d+\s*/", current):
        return False
    if ":" not in previous:
        return True
    return previous.endswith((",", "(", ":", "-", "και")) or previous.startswith("• ")


def _ignore_pdf_line(line: str) -> bool:
    normalized = normalize_for_match(line)
    if not normalized:
        return True
    if normalized in {normalize_for_match(heading) for heading in PDF_HEADINGS}:
        return False
    if normalized in {
        normalize_for_match("N 70, Ηλεκτρικές εστίες, 60 cm, εντοιχιζόμενη με πλαίσιο"),
        normalize_for_match("T16BT60N0"),
        normalize_for_match("Προαιρετικά εξαρτήματα"),
        normalize_for_match("Αυτόνομη ηλεκτρική εστία με TwistPadΒ®"),
    }:
        return True
    if normalized.startswith(normalize_for_match("Z1365WX0")) or normalized.startswith(normalize_for_match("Z943SE0")):
        return True
    return False


def _split_label_value(line: str) -> tuple[str, str]:
    value_line = line[2:].strip() if line.startswith("• ") else line
    if ":" not in value_line:
        return "", ""
    label, value = value_line.split(":", 1)
    label = normalize_whitespace(label)
    value = normalize_whitespace(value).replace("Aνοξείδωτο", "Ανοξείδωτο")
    if not label or not value:
        return "", ""
    return label, value


def _dedupe_items(items: list[SpecItem]) -> list[SpecItem]:
    deduped: list[SpecItem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (normalize_for_match(item.label), normalize_for_match(item.value or ""))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _parse_tefal_shop_product_html(html: str) -> list[SpecSection]:
    soup = BeautifulSoup(html, "lxml")
    return _parse_tefal_shop_spec_sections(soup)


def _parse_tefal_shop_spec_sections(soup: BeautifulSoup) -> list[SpecSection]:
    container = soup.select_one("[data-tab-content='about-the-product']")
    if container is None:
        return []

    items: list[SpecItem] = []
    for row in container.select("div.u-flex.u-justify-between.u-items-center.u-py-16.u-border-b"):
        label_node = row.select_one("span")
        value_node = row.select_one("div.t-text")
        label = normalize_whitespace(label_node.get_text(" ", strip=True) if label_node else "")
        value = normalize_whitespace(value_node.get_text(" ", strip=True) if value_node else "")
        if not label or not value:
            continue
        items.append(SpecItem(label=label, value=value))

    if not items:
        return []
    return [SpecSection(section="Χαρακτηριστικά Κατασκευαστή", items=_dedupe_items(items))]


def _parse_tefal_shop_product_page(html: str, search_body_html: str = "") -> EnrichmentResult:
    soup = BeautifulSoup(html, "lxml")
    spec_sections = _parse_tefal_shop_spec_sections(soup)
    hero_summary = _extract_tefal_intro_summary(soup, search_body_html=search_body_html)
    presentation_blocks = _extract_tefal_presentation_blocks(soup)
    return EnrichmentResult(
        manufacturer_spec_sections=spec_sections,
        manufacturer_source_text=_build_tefal_manufacturer_text(hero_summary, presentation_blocks, spec_sections),
        hero_summary=hero_summary,
        presentation_source_html=_build_presentation_source_html(presentation_blocks),
        presentation_source_text=_build_presentation_source_text(presentation_blocks),
    )


def _score_tefal_shop_product(source: SourceProductData, product: dict[str, Any]) -> int:
    brand = normalize_for_match(source.brand)
    mpn = normalize_for_match(source.mpn)
    haystack = normalize_for_match(
        " ".join(
            [
                normalize_whitespace(product.get("title", "")),
                normalize_whitespace(product.get("vendor", "")),
                normalize_whitespace(product.get("handle", "")),
                normalize_whitespace(product.get("url", "")),
            ]
        )
    )
    score = 0
    if mpn and mpn in haystack:
        score += 8
    if brand and brand in haystack:
        score += 3
    source_tokens = [
        token
        for token in normalize_for_match(source.name).split()
        if token and token not in {brand, mpn}
    ]
    score += min(sum(1 for token in source_tokens if token in haystack), 3)
    return score


def _discover_tefal_shop_urls_from_sitemaps(source: SourceProductData, fetcher) -> list[str]:
    sitemap_index = fetcher.fetch_httpx("https://shop.tefal.gr/sitemap.xml").html
    sitemap_urls = [url for url in _extract_xml_locs(sitemap_index) if "sitemap_products" in url.lower()]
    if not sitemap_urls:
        return []

    discovered: list[str] = []
    seen: set[str] = set()
    for sitemap_url in sitemap_urls:
        sitemap_xml = fetcher.fetch_httpx(sitemap_url).html
        for product_url in _extract_xml_locs(sitemap_xml):
            normalized_url = normalize_whitespace(product_url)
            if not normalized_url or normalized_url in seen:
                continue
            seen.add(normalized_url)
            discovered.append(normalized_url)
    return discovered


def _extract_xml_locs(xml_text: str) -> list[str]:
    return [
        normalize_whitespace(match.replace("&amp;", "&"))
        for match in re.findall(r"<loc>(.*?)</loc>", xml_text or "", flags=re.IGNORECASE | re.DOTALL)
        if normalize_whitespace(match.replace("&amp;", "&"))
    ]


def _score_tefal_shop_url(source: SourceProductData, product_url: str) -> int:
    brand = normalize_for_match(source.brand)
    mpn = normalize_for_match(source.mpn)
    haystack = normalize_for_match(product_url)
    if not mpn or mpn not in haystack:
        return 0
    score = 8
    if brand and brand in haystack:
        score += 2
    source_tokens = [
        token
        for token in normalize_for_match(source.name).split()
        if token and token not in {brand, mpn}
    ]
    score += min(sum(1 for token in source_tokens if token in haystack), 3)
    return score


def _extract_tefal_intro_summary(soup: BeautifulSoup, search_body_html: str = "") -> str:
    intro_section = soup.select_one("section[id*='product_title_description']")
    intro_title = ""
    intro_body = ""
    if isinstance(intro_section, Tag):
        title_node = intro_section.select_one("h1, h2, h3, h4")
        intro_title = normalize_whitespace(title_node.get_text(" ", strip=True) if title_node else "")
        intro_body = _extract_text_from_tefal_copy(intro_section)
    sidebar_body = _extract_tefal_description_sidebar_text(soup)
    search_body_text = _extract_tefal_list_text(search_body_html)
    return normalize_whitespace(" ".join(part for part in [intro_title, intro_body, sidebar_body, search_body_text] if part))


def _extract_tefal_presentation_blocks(soup: BeautifulSoup) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for section in soup.select("section[id*='product_push_highlight'], section[id*='product_edito_blog_']"):
        section_id = normalize_whitespace(section.get("id", ""))
        if "product_push_highlight" in section_id:
            for card in section.select("li.push-card"):
                _register_tefal_block(blocks, seen, _build_tefal_card_block(card))
        else:
            _register_tefal_block(blocks, seen, _build_tefal_edito_block(section))
    return blocks


def _register_tefal_block(blocks: list[dict[str, str]], seen: set[tuple[str, str]], block: dict[str, str]) -> None:
    title = normalize_whitespace(block.get("title", ""))
    paragraph = normalize_whitespace(block.get("paragraph", ""))
    if not title or not paragraph:
        return
    key = (normalize_for_match(title), normalize_for_match(paragraph))
    if key in seen:
        return
    seen.add(key)
    blocks.append(
        {
            "title": title,
            "paragraph": paragraph,
            "image_url": normalize_whitespace(block.get("image_url", "")),
        }
    )


def _build_tefal_card_block(container: Tag) -> dict[str, str]:
    title_node = container.select_one("h2, h3, h4")
    copy_node = container.select_one(".t-text")
    return {
        "title": normalize_whitespace(title_node.get_text(" ", strip=True) if title_node else ""),
        "paragraph": normalize_whitespace(copy_node.get_text(" ", strip=True) if copy_node else ""),
        "image_url": _extract_tefal_image_url(container),
    }


def _build_tefal_edito_block(section: Tag) -> dict[str, str]:
    text_container = section.select_one(".strate-edito-blog__text") or section
    title_node = text_container.select_one("h2, h3, h4")
    return {
        "title": normalize_whitespace(title_node.get_text(" ", strip=True) if title_node else ""),
        "paragraph": _extract_text_from_tefal_copy(text_container),
        "image_url": _extract_tefal_image_url(section.select_one(".strate-edito-blog__image") or section),
    }


def _extract_text_from_tefal_copy(container: Tag) -> str:
    lines = [
        normalize_whitespace(node.get_text(" ", strip=True))
        for node in container.select(".t-text p, .t-text li")
        if normalize_whitespace(node.get_text(" ", strip=True))
    ]
    if lines:
        return normalize_whitespace(" ".join(lines))
    copy_node = container.select_one(".t-text")
    if isinstance(copy_node, Tag):
        return normalize_whitespace(copy_node.get_text(" ", strip=True))
    clone = BeautifulSoup(str(container), "lxml")
    root = clone.select_one("*")
    if not isinstance(root, Tag):
        return ""
    for heading in root.select("h1, h2, h3, h4"):
        heading.decompose()
    return normalize_whitespace(root.get_text(" ", strip=True))


def _extract_tefal_description_sidebar_text(soup: BeautifulSoup) -> str:
    sidebar = soup.select_one("#product-description")
    if not isinstance(sidebar, Tag):
        return ""
    lines = [
        normalize_whitespace(node.get_text(" ", strip=True))
        for node in sidebar.select("li")
        if normalize_whitespace(node.get_text(" ", strip=True))
    ]
    if lines:
        return normalize_whitespace(" ".join(lines))
    return normalize_whitespace(sidebar.get_text(" ", strip=True))


def _extract_tefal_list_text(html_fragment: str) -> str:
    if not normalize_whitespace(html_fragment):
        return ""
    soup = BeautifulSoup(html_fragment, "lxml")
    lines = [
        normalize_whitespace(node.get_text(" ", strip=True))
        for node in soup.select("li, p")
        if normalize_whitespace(node.get_text(" ", strip=True))
    ]
    return normalize_whitespace(" ".join(lines))


def _extract_tefal_image_url(container: Tag) -> str:
    if not isinstance(container, Tag):
        return ""
    for selector in ["img", "source"]:
        for node in container.select(selector):
            raw = ""
            if selector == "img":
                raw = (
                    node.get("src")
                    or node.get("data-src")
                    or node.get("data-original")
                    or node.get("data-lazy-src")
                    or ""
                )
            if not raw:
                raw = _pick_first_srcset_candidate(node.get("srcset", "") or node.get("data-srcset", ""))
            image_url = make_absolute_url(raw, TEFAL_SHOP_BASE_URL) if raw else ""
            if image_url:
                return image_url
    return ""


def _pick_first_srcset_candidate(srcset: str) -> str:
    normalized = normalize_whitespace(srcset)
    if not normalized:
        return ""
    first = normalized.split(",", 1)[0].strip()
    return first.split(" ", 1)[0].strip()


def _build_presentation_source_html(blocks: list[dict[str, str]]) -> str:
    if not blocks:
        return ""
    parts = ["<div class=\"manufacturer-presentation\">"]
    for block in blocks:
        parts.append("<section>")
        parts.append(f"<h2>{block['title']}</h2>")
        parts.append(f"<p>{block['paragraph']}</p>")
        if block.get("image_url"):
            parts.append(f"<img src=\"{block['image_url']}\" alt=\"{block['title']}\" />")
        parts.append("</section>")
    parts.append("</div>")
    return "".join(parts)


def _build_presentation_source_text(blocks: list[dict[str, str]]) -> str:
    return normalize_whitespace(
        " ".join(
            f"{block['title']} {block['paragraph']}"
            for block in blocks
            if block.get("title") and block.get("paragraph")
        )
    )


def _build_tefal_manufacturer_text(
    hero_summary: str,
    presentation_blocks: list[dict[str, str]],
    spec_sections: list[SpecSection],
) -> str:
    parts: list[str] = [normalize_whitespace(hero_summary)]
    for block in presentation_blocks:
        parts.append(normalize_whitespace(block.get("title", "")))
        parts.append(normalize_whitespace(block.get("paragraph", "")))
    for section in spec_sections:
        parts.append(normalize_whitespace(section.section))
        for item in section.items:
            parts.append(normalize_whitespace(f"{item.label}: {item.value}"))
    return normalize_whitespace(" ".join(part for part in parts if part))


def _count_presentation_blocks(source_html: str, source_text: str) -> int:
    if source_html:
        soup = BeautifulSoup(source_html, "lxml")
        count = len(
            [
                node
                for node in soup.select("section")
                if node.select_one("h1, h2, h3, h4") and node.select_one("p")
            ]
        )
        if count:
            return count
    if not source_text:
        return 0
    chunks = [chunk for chunk in re.split(r"\s{2,}", source_text) if normalize_whitespace(chunk)]
    return len(chunks)
