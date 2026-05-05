from pathlib import Path

from pipeline import manufacturer_enrichment as enrichment_module
from pipeline.manufacturer_enrichment import (
    EnrichmentResult,
    OfficialDocAdapter,
    OfficialDocumentCandidate,
    _parse_bosch_specsheet,
    _parse_neff_specsheet,
    enrich_source_from_manufacturer_docs,
)
from pipeline.models import SourceProductData, SpecItem, SpecSection, TaxonomyResolution
from pipeline.normalize import normalize_for_match


BOSCH_SPECSHEET_SAMPLE = """
Σειρά 2, Ελεύθερος ψυγειοκαταψύκτης, 186 x 60 cm, Metal Look, Total No Frost
KGN36NLEA
Τεχνικά στοιχεία
Ενεργειακή κλάση: E
Μέση ετήσια κατανάλωση ενέργειας σε κιλοβατώρες ετησίως (kWh/a): 239 kWh/annum
Άθροισμα όγκων διαμερισμάτων κατάψυξης: 89 l
Άθροισμα όγκων διαμερισμάτων ψύξης: 216 l
Εκπομπές αερόφερτου ακουστικού θορύβου: 42 dB(A) re 1pW
Εντοιχιζόμενη / Ελεύθερη: Ελεύθερη συσκευή
Ύψος: 1860 mm
Πλάτος: 600 mm
Βάθος: 660 mm
Καθαρό βάρος: 61.5 kg
Αριθμός συμπιεστών: 1
Αριθμός ανεξάρτητων συστημάτων ψύξης: 1
Αναστρέψιμη φορά πόρτας: Ναι
Αριθμός ρυθμιζόμενων ραφιών στη συντήρηση: 3
Μπουκαλοθήκη: Όχι
Σύστημα No Frost: Ψυγείο και καταψύκτη
Τύπος εγκατάστασης: Ελεύθερα
Τεχνικά Χαρακτηριστικά
- Κλιματική Κλάση SN-T
- Συνολική Χωρητικότητα: 305 l
- Καθαρή Χωρητικότητα Συντήρησης: 216 l
- Καθαρή Χωρητικότητα Κατάψυξης : 89 l
Γενικά χαρακτηριστικά
- Total No Frost
- Dynamic MultiAirFlow για ομοιόμορφη κατανομή της ψύξης
- Ηλεκτρονικό panel ελέγχου (LED)
- Δεξιά φορά πόρτας, Δυνατότητα αλλαγής φοράς πόρτας
Στη συντήρηση
- 4 ράφια από γυαλί ασφαλείας, ρυθμιζόμενα σε ύψος: 3 αν.γρ. από τα οποία ρυθμίζονται σε ύψος
- MultiBox: διάφανο συρτάρι με κυματοειδή πυθμένα
- 4 ράφια θύρας
- Εσωτερικός φωτισμός LED
Στην κατάψυξη
- SuperFreezing στην κατάψυξη με αυτόματη απενεργοποίηση
- Ικανότητα Κατάψυξης σε 24 ώρες : 10 κιλό
- Αυτονομία σε περίπτωση διακοπής ρεύματος: 12 h ώρες
Διαστάσεις Συσκευής
- Διαστάσεις συσκευής ΥxΠxΒ: 186x60x66 cm
"""


def test_parse_bosch_specsheet_extracts_structured_sections() -> None:
    sections = _parse_bosch_specsheet(BOSCH_SPECSHEET_SAMPLE)
    flattened = {
        normalize_for_match(item.label): item.value
        for section in sections
        for item in section.items
    }

    assert flattened[normalize_for_match("Ενεργειακή κλάση")] == "E"
    assert flattened[normalize_for_match("Σύστημα No Frost")] == "Ψυγείο και καταψύκτη"
    assert flattened[normalize_for_match("Συνολική Χωρητικότητα")] == "305 l"
    assert flattened[normalize_for_match("Καθαρή Χωρητικότητα Συντήρησης")] == "216 l"
    assert flattened[normalize_for_match("Καθαρή Χωρητικότητα Κατάψυξης")] == "89 l"
    assert flattened[normalize_for_match("Διαστάσεις συσκευής ΥxΠxΒ")] == "186x60x66 cm"


NEFF_SPECSHEET_SAMPLE = """
N 70, Ηλεκτρικές εστίες, 60 cm,
εντοιχιζόμενη με πλαίσιο
T16BT60N0
Χαρακτηριστικά
Τεχνικά στοιχεία
Τύπος εγκατάστασης: ................................. Εντοιχιζόμενη συσκευή
Συνολικός αριθμός ζωνών που μπορούν να χρησιμοποιηθούν
ταυτόχρονα: ................................................................................ 4
Διαστάσεις εντοιχισμού (υ x π x β): .... 48 x 560-560 x 490-500 mm
Καθαρό βάρος: ..................................................................... 8.0 kg
Βασικό υλικό επιφανειών: .........................................Υαλοκεραμική
Χρώμα πλαισίου: ..........................................................Aνοξείδωτο
Τεχνικά χαρακτηριστικά
• Είδος ηλεκτρονικού ελέγχου: TwistPad4: πλήρης έλεγχος της ισχύος
μέσω του αφαιρούμενου μαγνητικού διακόπτη.
• Μπροστά αριστερά: 145 mm, 1.2 ΚW
• Πίσω αριστερά: 210 mm, 120 mm, 0.75 ΚW
Γενικά χαρακτηριστικά
• Λειτουργία Restart: εάν η εστία απενεργοποιηθεί καταλάθος, μπορεί
να επαναφέρει όλες τις προηγούμενες ρυθμίσεις της.
• Συνολική ισχύς: 6.3 ΚW
"""


def test_parse_neff_specsheet_extracts_structured_sections() -> None:
    sections = _parse_neff_specsheet(NEFF_SPECSHEET_SAMPLE)
    flattened = {
        normalize_for_match(item.label): item.value
        for section in sections
        for item in section.items
    }

    assert flattened[normalize_for_match("Τύπος εγκατάστασης")] == "Εντοιχιζόμενη συσκευή"
    assert flattened[normalize_for_match("Συνολικός αριθμός ζωνών που μπορούν να χρησιμοποιηθούν ταυτόχρονα")] == "4"
    assert flattened[normalize_for_match("Καθαρό βάρος")] == "8.0 kg"
    assert flattened[normalize_for_match("Χρώμα πλαισίου")] == "Ανοξείδωτο"
    assert flattened[normalize_for_match("Είδος ηλεκτρονικού ελέγχου")].startswith("TwistPad4")
    assert flattened[normalize_for_match("Μπροστά αριστερά")] == "145 mm, 1.2 ΚW"
    assert flattened[normalize_for_match("Συνολική ισχύς")] == "6.3 ΚW"


class _DummyFetcher:
    def __init__(self, html: str = "<html></html>", binary: bytes = b"%PDF-1.4 test") -> None:
        self.html = html
        self.binary = binary

    def fetch_binary(self, _url: str) -> tuple[bytes, str]:
        return self.binary, "application/pdf"

    def fetch_playwright(self, url: str):
        return type("Fetch", (), {"html": self.html, "final_url": url})()


class _FakePdfAdapter(OfficialDocAdapter):
    provider_id = "fakepdf"

    def matches(self, source: SourceProductData) -> bool:
        return normalize_for_match(source.brand) == normalize_for_match("PdfBrand")

    def discover(self, source: SourceProductData, taxonomy: TaxonomyResolution) -> list[OfficialDocumentCandidate]:
        return [
            OfficialDocumentCandidate(
                provider_id=self.provider_id,
                document_type="pdf",
                url="https://example.com/specsheet.pdf",
                name="specsheet",
                content_type_hint="application/pdf",
                priority=10,
            )
        ]

    def parse(self, candidate: OfficialDocumentCandidate, payload: bytes | str, source: SourceProductData, taxonomy: TaxonomyResolution) -> EnrichmentResult:
        assert isinstance(payload, (bytes, bytearray))
        return EnrichmentResult(
            manufacturer_spec_sections=[
                SpecSection(section="Τεχνικά στοιχεία", items=[SpecItem(label="Ισχύς", value="2200 W")]),
            ],
            manufacturer_source_text="Ισχύς: 2200 W",
        )


class _FakeHtmlAdapter(OfficialDocAdapter):
    provider_id = "fakehtml"

    def matches(self, source: SourceProductData) -> bool:
        return normalize_for_match(source.brand) == normalize_for_match("HtmlBrand")

    def discover(self, source: SourceProductData, taxonomy: TaxonomyResolution) -> list[OfficialDocumentCandidate]:
        return [
            OfficialDocumentCandidate(
                provider_id=self.provider_id,
                document_type="html",
                url="https://example.com/specs",
                name="product_page",
                content_type_hint="text/html",
                priority=10,
            )
        ]

    def parse(self, candidate: OfficialDocumentCandidate, payload: bytes | str, source: SourceProductData, taxonomy: TaxonomyResolution) -> EnrichmentResult:
        assert isinstance(payload, str)
        assert "<dl>" in payload
        return EnrichmentResult(
            manufacturer_spec_sections=[
                SpecSection(section="Γενικά χαρακτηριστικά", items=[SpecItem(label="Χρώμα", value="Μαύρο")]),
            ],
            manufacturer_source_text="Χρώμα: Μαύρο",
        )


def test_enrichment_framework_supports_pdf_candidates(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(enrichment_module, "get_official_doc_adapters", lambda: [_FakePdfAdapter()])
    source = SourceProductData(source_name="skroutz", brand="PdfBrand", mpn="PDF-1", name="PdfBrand PDF-1")
    taxonomy = TaxonomyResolution(parent_category="A", leaf_category="B", sub_category="C")

    diagnostics = enrich_source_from_manufacturer_docs(
        source=source,
        taxonomy=taxonomy,
        fetcher=_DummyFetcher(),
        output_dir=tmp_path,
    )

    assert diagnostics["applied"] is True
    assert diagnostics["provider"] == "fakepdf"
    assert diagnostics["documents_discovered"] == 1
    assert diagnostics["documents_parsed"] == 1
    assert diagnostics["field_count"] == 1
    assert diagnostics["fallback_reason"] == ""
    assert source.manufacturer_source_text == "Ισχύς: 2200 W"
    assert source.manufacturer_spec_sections[0].items[0].value == "2200 W"
    assert source.manufacturer_documents[0]["document_type"] == "pdf"
    assert Path(source.manufacturer_documents[0]["local_path"]).suffix == ".pdf"
    assert Path(source.manufacturer_documents[0]["text_path"]).suffix == ".txt"


def test_enrichment_framework_supports_html_candidates(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(enrichment_module, "get_official_doc_adapters", lambda: [_FakeHtmlAdapter()])
    source = SourceProductData(source_name="skroutz", brand="HtmlBrand", mpn="HTML-1", name="HtmlBrand HTML-1")
    taxonomy = TaxonomyResolution(parent_category="A", leaf_category="B", sub_category="C")
    html = "<html><body><dl><dt>Χρώμα</dt><dd>Μαύρο</dd></dl></body></html>"

    diagnostics = enrich_source_from_manufacturer_docs(
        source=source,
        taxonomy=taxonomy,
        fetcher=_DummyFetcher(html=html),
        output_dir=tmp_path,
    )

    assert diagnostics["applied"] is True
    assert diagnostics["provider"] == "fakehtml"
    assert diagnostics["documents_discovered"] == 1
    assert diagnostics["documents_parsed"] == 1
    assert diagnostics["field_count"] == 1
    assert source.manufacturer_source_text == "Χρώμα: Μαύρο"
    assert source.manufacturer_spec_sections[0].items[0].value == "Μαύρο"
    assert source.manufacturer_documents[0]["document_type"] == "html"
    assert Path(source.manufacturer_documents[0]["local_path"]).suffix == ".html"


def test_enrichment_framework_supports_adapters_without_fetcher_parameter(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(enrichment_module, "get_official_doc_adapters", lambda: [_FakeHtmlAdapter()])
    source = SourceProductData(source_name="skroutz", brand="HtmlBrand", mpn="HTML-1", name="HtmlBrand HTML-1")
    taxonomy = TaxonomyResolution(parent_category="A", leaf_category="B", sub_category="C")

    diagnostics = enrich_source_from_manufacturer_docs(
        source=source,
        taxonomy=taxonomy,
        fetcher=_DummyFetcher(html="<html><body><dl><dt>Χρώμα</dt><dd>Μαύρο</dd></dl></body></html>"),
        output_dir=tmp_path,
    )

    assert diagnostics["applied"] is True
    assert diagnostics["provider"] == "fakehtml"


def test_enrichment_framework_gracefully_falls_back_when_no_provider_matches(tmp_path: Path) -> None:
    source = SourceProductData(source_name="skroutz", brand="UnknownBrand", mpn="ABC123", name="UnknownBrand ABC123")
    taxonomy = TaxonomyResolution(parent_category="A", leaf_category="B", sub_category="C")

    diagnostics = enrich_source_from_manufacturer_docs(
        source=source,
        taxonomy=taxonomy,
        fetcher=_DummyFetcher(),
        output_dir=tmp_path,
    )

    assert diagnostics["applied"] is False
    assert diagnostics["fallback_reason"] == "no_matching_provider"
    assert diagnostics["documents_discovered"] == 0
    assert source.manufacturer_spec_sections == []
    assert source.manufacturer_source_text == ""

