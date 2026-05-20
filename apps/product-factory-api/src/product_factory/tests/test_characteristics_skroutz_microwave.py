from bs4 import BeautifulSoup

from product_factory.characteristics_pipeline import build_characteristics_for_product
from product_factory.models import (
    SchemaMatchResult,
    SourceProductData,
    SpecItem,
    SpecSection,
    TaxonomyResolution,
)
from product_factory.normalize import normalize_for_match
from product_factory.repo_paths import SCHEMA_LIBRARY_PATH
from product_factory.utils import read_json


def _schema_id_for_source_file(source_file: str) -> str:
    schema_library = read_json(SCHEMA_LIBRARY_PATH)
    for schema in schema_library.get("schemas", []):
        if source_file in schema.get("source_files", []):
            schema_id = str(schema.get("schema_id", "")).strip()
            if schema_id:
                return schema_id
    raise AssertionError(f"Schema id not found for source file {source_file!r}.")


def test_skroutz_microwave_characteristics_use_alias_enrichment() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Panasonic",
        mpn="NN-K36NBMEPG",
        name="Panasonic NN-K36NBMEPG Φούρνος Μικροκυμάτων με Grill 24lt Μαύρος",
        spec_sections=[
            SpecSection(
                section="Γενικά",
                items=[
                    SpecItem(label="Τοποθέτηση", value="Ελεύθερος"),
                    SpecItem(label="Ισχύς Μικροκυμάτων", value="900 W"),
                    SpecItem(label="Επίπεδα Ισχύος", value="5"),
                    SpecItem(label="Χωρητικότητα", value="24 lt"),
                    SpecItem(label="Retro", value="Όχι"),
                    SpecItem(label="Χρώμα", value="Μαύρο"),
                ],
            ),
            SpecSection(
                section="Δυνατότητες & Λειτουργίες",
                items=[
                    SpecItem(label="Inverter", value="Όχι"),
                    SpecItem(label="Τύπος Λειτουργίας", value="Ψηφιακός"),
                    SpecItem(label="Λειτουργία Grill", value="Ναι"),
                    SpecItem(label="Λειτουργία Αέρα", value="Όχι"),
                    SpecItem(label="Μαγείρεμα με Ατμό", value="Όχι"),
                    SpecItem(label="Λειτουργία Ξεπαγώματος", value="Ναι"),
                    SpecItem(label="Αυτόματα Προγράμματα", value="Ναι"),
                ],
            ),
            SpecSection(
                section="Εξωτερικές Διαστάσεις",
                items=[
                    SpecItem(label="Πλάτος", value="46,9 cm"),
                    SpecItem(label="Βάθος", value="38 cm"),
                    SpecItem(label="Ύψος", value="28 cm"),
                ],
            ),
        ],
        presentation_source_text=(
            "Με ισχύ μικροκυμάτων 900 Watt (5 επίπεδα ισχύος) και γκριλ χαλαζία 1000 watt. "
            "Εύκολη αναθέρμανση, μαγείρεμα και ψήσιμο στη σχάρα χάρη σε 11 αυτόματα προγράμματα. "
            "Η λειτουργία σάς επιτρέπει να ρυθμίζετε το χρόνο μαγειρέματος σε βήματα των 30 δευτερολέπτων με ένα γρήγορο κουμπί 30."
        ),
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Φούρνοι Μικροκυμάτων",
        sub_category="Με Grill",
    )

    html, diagnostics, _warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=_schema_id_for_source_file("foyrnoi_mikrokymaton.json"),
            score=0.9,
        ),
    )

    soup = BeautifulSoup(html, "lxml")
    values = {
        normalize_for_match(cells[0].get_text(" ", strip=True)): cells[1].get_text(
            " ", strip=True
        )
        for cells in (row.find_all("td") for row in soup.select("tbody tr"))
        if len(cells) == 2
    }

    assert diagnostics["template_source"] == "schema_library_with_custom_overrides"
    assert values[normalize_for_match("Τρόπος Τοποθέτησης")] == "Ελεύθερος"
    assert values[normalize_for_match("Χωρητικότητα Φούρνου σε Λίτρα")] == "24"
    assert values[normalize_for_match("Ισχύς Μικροκυμάτων (Watt)")] == "900 W"
    assert values[normalize_for_match("Επίπεδα Ισχύος Μικροκυμάτων")] == "5"
    assert values[normalize_for_match("Ισχύς Grill (Watt)")] == "1000 W"
    assert values[normalize_for_match("Χειριστήριο")] == "Ψηφιακός"
    assert values[normalize_for_match("Οθόνη Ενδείξεων")] == "Ναι"
    assert values[normalize_for_match("Λειτουργία Μικροκύματα + Grill")] == "Ναι"
    assert values[normalize_for_match("Aυτόματα Προγράμματα Μαγειρέματος")] == "Ναι"
    assert values[normalize_for_match("Αριθμός Αυτόματων Προγραμμάτων")] == "11"
    assert values[normalize_for_match("Πλήκτρο Αύξησης Χρόνου")] == "Ναι"


def test_skroutz_microwave_characteristics_use_description_label_pairs() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Brand",
        mpn="MW-1",
        name="Brand MW-1 Φούρνος Μικροκυμάτων",
        presentation_source_html="""
            <div class="sku-description">
              <ul>
                <li>Τοποθέτηση: Ελεύθερος.</li>
                <li>Ισχύς Μικροκυμάτων: 800W.</li>
                <li>Χρώμα: Λευκό.</li>
              </ul>
            </div>
        """,
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Φούρνοι Μικροκυμάτων",
        sub_category="Με Grill",
    )

    html, diagnostics, _warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=_schema_id_for_source_file("foyrnoi_mikrokymaton.json"),
            score=0.9,
        ),
    )

    soup = BeautifulSoup(html, "lxml")
    values = {
        normalize_for_match(cells[0].get_text(" ", strip=True)): cells[1].get_text(
            " ", strip=True
        )
        for cells in (row.find_all("td") for row in soup.select("tbody tr"))
        if len(cells) == 2
    }
    diagnostics_by_label = {
        normalize_for_match(field["label"]): field for field in diagnostics["fields"]
    }

    assert values[normalize_for_match("Τρόπος Τοποθέτησης")] == "Ελεύθερος"
    assert values[normalize_for_match("Ισχύς Μικροκυμάτων (Watt)")] == "800W"
    assert values[normalize_for_match("Χρώμα")] == "Λευκό"
    assert diagnostics_by_label[normalize_for_match("Ισχύς Μικροκυμάτων (Watt)")][
        "resolved_from"
    ].startswith("description_alias:")
