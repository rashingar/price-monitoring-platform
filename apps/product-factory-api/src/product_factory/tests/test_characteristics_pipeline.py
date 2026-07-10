from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from product_factory.characteristics_pipeline import (
    CharacteristicsTemplateRegistry,
    _labels_related,
    build_characteristics_for_product,
)
from product_factory.html_builders import _normalize_characteristics_label
from product_factory.mapping import build_row
from product_factory.models import (
    CLIInput,
    ParsedProduct,
    SchemaMatchResult,
    SourceProductData,
    SpecItem,
    SpecSection,
    TaxonomyResolution,
)
from product_factory.normalize import normalize_for_match
from product_factory.repo_paths import SCHEMA_LIBRARY_PATH
from product_factory.schema_matcher import SchemaMatcher
from product_factory.utils import read_json

_SCHEMA_LIBRARY = read_json(SCHEMA_LIBRARY_PATH)


def _schema_id_for_source_file(source_file: str) -> str:
    for schema in _SCHEMA_LIBRARY.get("schemas", []):
        if source_file in schema.get("source_files", []):
            schema_id = str(schema.get("schema_id", "")).strip()
            if schema_id:
                return schema_id
    raise AssertionError(f"Schema id not found for source file {source_file!r}.")


TV_TEMPLATE_SCHEMA_ID = _schema_id_for_source_file("tileoraseis.json")
HOOD_SCHEMA_ID = _schema_id_for_source_file("aporrofitires.json")
BUILT_IN_HOB_SCHEMA_ID = _schema_id_for_source_file("esties.json")
FRIDGE_FREEZER_SCHEMA_ID = _schema_id_for_source_file("psygeiokatapsyktes.json")
ICE_CREAM_MAKER_SCHEMA_ID = _schema_id_for_source_file("pagotomixanes.json")
WASHING_MACHINE_SCHEMA_ID = _schema_id_for_source_file("plyntiria_rouxwn.json")
SOUND_BAR_SCHEMA_ID = _schema_id_for_source_file("sound_bars.json")
AIR_CONDITIONER_SCHEMA_ID = _schema_id_for_source_file("toixoy.json")
PORTABLE_AIR_CONDITIONER_SCHEMA_ID = _schema_id_for_source_file("forita.json")


def test_normalize_characteristics_label_keeps_balanced_parentheses_unchanged() -> None:
    assert (
        _normalize_characteristics_label("Μέγιστη Ονομαστική Ισχύς (W)")
        == "Μέγιστη Ονομαστική Ισχύς (W)"
    )


def test_normalize_characteristics_label_repairs_single_unmatched_open_parenthesis() -> (
    None
):
    assert (
        _normalize_characteristics_label("Μέγιστη Ονομαστική Ισχύς (W")
        == "Μέγιστη Ονομαστική Ισχύς (W)"
    )


def test_normalize_characteristics_label_leaves_multiple_unmatched_open_parentheses_unchanged() -> (
    None
):
    assert (
        _normalize_characteristics_label("Διαστάσεις (Υ x Π x Β (cm")
        == "Διαστάσεις (Υ x Π x Β (cm"
    )


def test_power_watt_labels_resolve_when_source_uses_max_power_wording() -> None:
    assert _labels_related(
        normalize_for_match("ΞΞ­Ξ³ΞΉΟƒΟ„Ξ· Ξ™ΟƒΟ‡ΟΟ‚ (Watt)"),
        normalize_for_match("Ξ™ΟƒΟ‡ΟΟ‚ ΟƒΞµ Watts"),
    )


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Ισχύς", "Ισχυς"),
        ("Ισχύς", "Ισχύς σε Watts"),
        ("Ισχυς", "Ισχυς σε Watts"),
        ("Μέγιστη Ισχύς (Watt)", "Μεγιστη Ισχυς (Watt)"),
        ("Ξ™ΟƒΟ‡ΟΟ‚", "Ισχύς"),
        ("Ξ™ΟƒΟ‡ΟΟ‚ ΟƒΞµ Watts", "Ισχύς σε Watt"),
        ("ΞΞ­Ξ³ΞΉΟƒΟ„Ξ· Ξ™ΟƒΟ‡ΟΟ‚ (Watt)", "Ισχύς"),
    ],
)
def test_labels_related_uses_shared_power_watt_aliases(left: str, right: str) -> None:
    assert _labels_related(normalize_for_match(left), normalize_for_match(right))


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Ισχύς", "Διαστάσεις"),
        ("Ισχύς σε Watt", "Βάρος"),
        ("Ξ™ΟƒΟ‡ΟΟ‚", "Ισχύς Ψύξης"),
    ],
)
def test_labels_related_does_not_overmatch_power_aliases(left: str, right: str) -> None:
    assert not _labels_related(normalize_for_match(left), normalize_for_match(right))


def test_skroutz_fridge_freezer_characteristics_keep_electronet_shape() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Bosch",
        mpn="KGN36NLEA",
        name="Bosch Ψυγειοκαταψύκτης 305lt Total NoFrost Υ186xΠ60xΒ66εκ. Metal Look KGN36NLEA",
        key_specs=[
            SpecItem(label="Τύπος", value="Ψυγειοκαταψύκτης"),
            SpecItem(label="Συνολική Χωρητικότητα", value="305 lt"),
            SpecItem(label="Χωρητικότητα Κατάψυξης", value="89 lt"),
            SpecItem(label="Χωρητικότητα Συντήρησης", value="216 lt"),
            SpecItem(label="Σύστημα Ψύξης", value="Total NoFrost"),
            SpecItem(label="Χρώμα", value="Inox"),
        ],
        spec_sections=[
            SpecSection(
                section="Στην Συντήρηση",
                items=[
                    SpecItem(
                        label="Στην Συντήρηση",
                        value="4 ράφια (ρυθμιζόμενα), 1 συρτάρι, 4 ράφια στην πόρτα",
                    )
                ],
            ),
            SpecSection(
                section="Στην Κατάψυξη",
                items=[SpecItem(label="Στην Κατάψυξη", value="3 συρτάρια")],
            ),
            SpecSection(
                section="Νέα Ενεργειακή Ετικέτα",
                items=[
                    SpecItem(label="Ενεργειακή Κλάση", value="E"),
                    SpecItem(label="Επίπεδο Θορύβου", value="42 dB"),
                ],
            ),
            SpecSection(
                section="Δυνατότητες & Λειτουργίες",
                items=[
                    SpecItem(label="Αναστρέψιμη Πόρτα", value="Ναι"),
                    SpecItem(label="Έξοδος Κρύου Νερού", value="Όχι"),
                    SpecItem(label="Έξοδος για Παγάκια", value="Όχι"),
                    SpecItem(
                        label="Extra Δυνατότητες",
                        value="Ηχητική Ειδοποίηση Πόρτας, Γρήγορη Ψύξη-Κατάψυξη, Οθόνη Ενδείξεων",
                    ),
                ],
            ),
            SpecSection(
                section="Διαστάσεις",
                items=[
                    SpecItem(label="Ύψος", value="186 cm"),
                    SpecItem(label="Πλάτος", value="60 cm"),
                    SpecItem(label="Βάθος", value="66 cm"),
                ],
            ),
            SpecSection(
                section="Smart Ιδιότητες", items=[SpecItem(label="Wi-Fi", value="Όχι")]
            ),
            SpecSection(
                section="Εγγύηση",
                items=[
                    SpecItem(
                        label="Επιμέρους Εγγύηση Κατασκευαστή",
                        value="10 χρόνια στον Συμπιεστή",
                    )
                ],
            ),
        ],
        manufacturer_source_text=(
            "Εντοιχιζόμενη / Ελεύθερη: Ελεύθερη συσκευή Αριθμός συμπιεστών: 1 Αριθμός ανεξάρτητων συστημάτων ψύξης: 1 "
            "Αριθμός ρυθμιζόμενων ραφιών στη συντήρηση: 3 Μπουκαλοθήκη: Όχι Σύστημα No Frost: Ψυγείο και καταψύκτης "
            "Total No Frost Dynamic MultiAirFlow για ομοιόμορφη κατανομή της ψύξης Ηλεκτρονικό panel ελέγχου (LED) "
            "Δυνατότητα αλλαγής φοράς πόρτας 4 ράφια από γυαλί ασφαλείας MultiBox 4 ράφια θύρας Εσωτερικός φωτισμός LED "
            "SuperFreezing Ικανότητα Κατάψυξης σε 24 ώρες : 10 κιλό Αυτονομία σε περίπτωση διακοπής ρεύματος: 12 h ώρες "
            "Διαστάσεις συσκευής ΥxΠxΒ: 186x60x66 cm Καθαρό βάρος: 61.5 kg Κλιματική Κλάση SN-T"
        ),
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Ψυγεία & Καταψύκτες",
        sub_category="Ψυγειοκαταψύκτες",
    )

    html, diagnostics, warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=FRIDGE_FREEZER_SCHEMA_ID, score=0.95
        ),
    )

    soup = BeautifulSoup(html, "lxml")
    values = {
        (
            normalize_for_match(field["section"]),
            normalize_for_match(field["label"]),
        ): field["value"]
        for field in diagnostics["fields"]
    }

    assert diagnostics["template_source"] == "schema_library_with_custom_overrides"
    assert diagnostics["matched_schema_id"] == FRIDGE_FREEZER_SCHEMA_ID
    assert "psygeiokatapsyktes.json" in diagnostics["preferred_schema_source_files"]
    assert (
        f"characteristics_template_used:schema:{FRIDGE_FREEZER_SCHEMA_ID}" in warnings
    )
    assert (
        values[
            (
                normalize_for_match("Επισκόπηση Προϊόντος"),
                normalize_for_match("Τεχνολογία Ψύξης"),
            )
        ]
        == "Total NoFrost"
    )
    assert (
        values[
            (
                normalize_for_match("Επισκόπηση Προϊόντος"),
                normalize_for_match("Συνολική Καθαρή Χωρητικότητα"),
            )
        ]
        == "305 lt"
    )
    assert (
        values[
            (
                normalize_for_match("Επισκόπηση Προϊόντος"),
                normalize_for_match("Πολλαπλή Ροή Αέρα"),
            )
        ]
        == "Ναι"
    )
    assert (
        values[
            (
                normalize_for_match("Επισκόπηση Προϊόντος"),
                normalize_for_match("Σήμα Ειδοποίησης Ανοικτής Πόρτας"),
            )
        ]
        == "Ναι"
    )
    assert (
        values[
            (normalize_for_match("Συντήρηση"), normalize_for_match("Αριθμός Ραφιών"))
        ]
        == "4"
    )
    assert (
        values[
            (
                normalize_for_match("Συντήρηση"),
                normalize_for_match("Ρυθμιζόμενα Ράφια σε Ύψος"),
            )
        ]
        == "3"
    )
    assert (
        values[(normalize_for_match("Συντήρηση"), normalize_for_match("Υλικό Ραφιών"))]
        == "Γυαλί Ασφαλείας"
    )
    assert (
        values[
            (
                normalize_for_match("Κατάψυξη"),
                normalize_for_match("Λειτουργία Ταχείας Κατάψυξης"),
            )
        ]
        == "Ναι"
    )
    assert (
        values[
            (
                normalize_for_match("Γενικά χαρακτηριστικά"),
                normalize_for_match("Διαστάσεις Συσκευής σε Εκατοστά (Υ χ Π χ Β"),
            )
        ]
        == "186 x 60 x 66 cm"
    )
    assert (
        values[
            (
                normalize_for_match("Γενικά χαρακτηριστικά"),
                normalize_for_match("Εγγύηση Κατασκευαστή"),
            )
        ]
        == "10 χρόνια στον Συμπιεστή"
    )


def test_skroutz_wall_air_conditioner_characteristics_keep_electronet_shape() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Toyotomi",
        mpn="OTN/OTG-09QINV",
        name="Toyotomi Ora Κλιματιστικό Inverter 9000 BTU A++/A+ με Ιονιστή και WiFi",
        hero_summary=(
            "Το Toyotomi Ora είναι κλιματιστικό Inverter με WiFi, Voice Control, Turbo Mode, Sleep & Silence Mode, "
            "i-Clean στους 56°C, λειτουργία Αφύγρανσης, Smart Defrost, Autorestart, Smooth Start, Hotel Menu και 8°C Heating."
        ),
        presentation_source_text="Η λειτουργία Follow Me προσαρμόζει τη θερμοκρασία στο σημείο που βρίσκεσαι.",
        key_specs=[
            SpecItem(label="Κωδικός Προϊόντος", value="OTN/OTG-09QINV"),
            SpecItem(label="Απόδοση (BTU)", value="9000 BTU"),
            SpecItem(label="Ισχύς Ψύξης", value="9000 BTU"),
            SpecItem(label="Ισχύς Θέρμανσης", value="9000 BTU"),
            SpecItem(label="WiFi", value="Ναι"),
            SpecItem(label="WiFi Ready", value="Όχι"),
            SpecItem(label="Φίλτρα Αέρα", value="Ναι"),
            SpecItem(label="Ιονιστής", value="Ναι"),
        ],
        spec_sections=[
            SpecSection(
                section="Γενικά",
                items=[SpecItem(label="Κωδικός Προϊόντος", value="OTN/OTG-09QINV")],
            ),
            SpecSection(
                section="Απόδοση",
                items=[
                    SpecItem(label="Απόδοση (BTU)", value="9000 BTU"),
                    SpecItem(label="Ισχύς Ψύξης", value="9000 BTU"),
                    SpecItem(label="Ισχύς Θέρμανσης", value="9000 BTU"),
                ],
            ),
            SpecSection(
                section="Δυνατότητες & Λειτουργίες",
                items=[
                    SpecItem(label="WiFi", value="Ναι"),
                    SpecItem(label="WiFi Ready", value="Όχι"),
                    SpecItem(label="Φίλτρα Αέρα", value="Ναι"),
                    SpecItem(label="Ιονιστής", value="Ναι"),
                    SpecItem(
                        label="Τύπος Φίλτρων",
                        value="Antivirus, Active Carbon, Προ φίλτρο Υψηλής Πυκνότητας",
                    ),
                    SpecItem(label="Οικολογικό Ψυκτικό Υγρό (R32)", value="Ναι"),
                    SpecItem(label="με Τεχνητή Νοημοσύνη", value="Όχι"),
                    SpecItem(label="Λειτουργία Follow Me", value="Ναι"),
                    SpecItem(label="Χρώμα", value="Λευκό"),
                ],
            ),
            SpecSection(
                section="Ενεργειακή Κλάση",
                items=[
                    SpecItem(label="Ψύξης", value="A++"),
                    SpecItem(label="Θέρμανσης (Μέση Ζώνη)", value="A+"),
                    SpecItem(label="Βαθμός Απόδοσης Ψύξης (SEER)", value="6,1 W/W"),
                    SpecItem(label="Βαθμός Απόδοσης Θέρμανσης (SCOP)", value="4 W/W"),
                    SpecItem(label="Κατανάλωση Ψύξης", value="150 kWh/y"),
                    SpecItem(label="Κατανάλωση Θέρμανσης", value="735 kWh/y"),
                    SpecItem(label="Θέρμανσης (Θερμή Ζώνη)", value="A+++"),
                    SpecItem(
                        label="Βαθμός Απόδοσης Θέρμανσης (SCOP) Θερμή Ζώνη",
                        value="5,1 W/W",
                    ),
                ],
            ),
            SpecSection(
                section="Ισχύς Θορύβου",
                items=[
                    SpecItem(label="Εσωτερικής Μονάδας", value="52 dB"),
                    SpecItem(label="Εξωτερικής Μονάδας", value="59 dB"),
                ],
            ),
            SpecSection(
                section="Φυσικές Διαστάσεις",
                items=[
                    SpecItem(label="Μήκος Εσωτερικής Μονάδας", value="70,8 cm"),
                    SpecItem(label="Ύψος Εσωτερικής Μονάδας", value="28,1 cm"),
                    SpecItem(label="Βάθος Εσωτερικής Μονάδας", value="19,2 cm"),
                    SpecItem(label="Μήκος Εξωτερικής Μονάδας", value="72,7 cm"),
                    SpecItem(label="Ύψος Εξωτερικής Μονάδας", value="45,6 cm"),
                    SpecItem(label="Βάθος Εξωτερικής Μονάδας", value="27,8 cm"),
                ],
            ),
            SpecSection(
                section="Εγγύηση",
                items=[
                    SpecItem(
                        label="Επιμέρους Εγγύηση Κατασκευαστή",
                        value="10 χρόνια σε όλα τα ηλεκτρικά και μηχανικά μέρη, 10 χρόνια στον Συμπιεστή",
                    )
                ],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf_category="Κλιματιστικά",
        sub_category="Τοίχου",
    )

    html, diagnostics, warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=AIR_CONDITIONER_SCHEMA_ID, score=0.95
        ),
    )

    soup = BeautifulSoup(html, "lxml")
    values = {
        (
            normalize_for_match(field["section"]),
            normalize_for_match(field["label"]),
        ): field["value"]
        for field in diagnostics["fields"]
    }
    extra_features = values[
        (
            normalize_for_match("Επιπλέον Χαρακτηριστικά"),
            normalize_for_match("Πρόσθετες Λειτουργίες Κλιματιστικού"),
        )
    ]

    assert diagnostics["template_source"] == "schema_library_with_custom_overrides"
    assert diagnostics["custom_template_id"] == "skroutz_wall_air_conditioner_v1"
    assert diagnostics["matched_schema_id"] == AIR_CONDITIONER_SCHEMA_ID
    assert diagnostics["preferred_schema_source_files"] == ["toixoy.json"]
    assert diagnostics["unresolved_count"] < 20
    assert (
        f"characteristics_template_used:schema:{AIR_CONDITIONER_SCHEMA_ID}" in warnings
    )
    assert normalize_for_match("Ψυκτική / Θερμική Απόδοση") in [
        normalize_for_match(node.get_text(" ", strip=True))
        for node in soup.select("thead strong")
    ]
    assert (
        values[
            (
                normalize_for_match("Ψυκτική / Θερμική Απόδοση"),
                normalize_for_match("Ονομαστική Απόδοση (Btu/h)"),
            )
        ]
        == "9000 BTU"
    )
    assert (
        values[
            (
                normalize_for_match("Ψυκτική / Θερμική Απόδοση"),
                normalize_for_match("Ψυκτική Απόδοση ( Btu/h )"),
            )
        ]
        == "9000 BTU"
    )
    assert (
        values[
            (
                normalize_for_match("Βαθμοί Εποχιακής Απόδοσης"),
                normalize_for_match("Βαθμός Εποχιακής Απόδοσης Ψύξης - SEER"),
            )
        ]
        == "6,1 W/W"
    )
    assert (
        values[
            (
                normalize_for_match("Βαθμοί Εποχιακής Απόδοσης"),
                normalize_for_match("Ενεργειακή Κλάση Ψύξης"),
            )
        ]
        == "A++"
    )
    assert (
        values[
            (
                normalize_for_match("Βαθμοί Εποχιακής Απόδοσης"),
                normalize_for_match("Ενεργειακή Κλάση Θέρμανσης Θερμότερης Εποχής"),
            )
        ]
        == "A+++"
    )
    assert (
        values[
            (
                normalize_for_match("Καταναλώσεις"),
                normalize_for_match(
                    "Ετήσια Κατανάλωση Θέρμανσης Μέσης Εποχής ( kWh / a )"
                ),
            )
        ]
        == "735 kWh/y"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Τεχνολογία Κλιματιστικού"),
            )
        ]
        == "Inverter"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Ψυκτικό Υγρό"),
            )
        ]
        == "R32"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Αφύγρανση"),
            )
        ]
        == "Ναι"
    )
    assert values[
        (normalize_for_match("Επιπλέον Χαρακτηριστικά"), normalize_for_match("Φίλτρα"))
    ] == ("Antivirus, Active Carbon, Προ φίλτρο Υψηλής Πυκνότητας")
    assert "WiFi" in extra_features
    assert "Follow Me" in extra_features
    assert "Voice Control" in extra_features
    assert "Self Clean 56°C" in extra_features
    assert (
        values[
            (
                normalize_for_match("Διαστάσεις και Βάρος"),
                normalize_for_match("Ύψος Εσωτερικής Μονάδας ( mm )"),
            )
        ]
        == "281"
    )
    assert (
        values[
            (
                normalize_for_match("Διαστάσεις και Βάρος"),
                normalize_for_match("Πλάτος Εσωτερικής Μονάδας ( mm )"),
            )
        ]
        == "708"
    )
    assert (
        values[
            (
                normalize_for_match("Διαστάσεις και Βάρος"),
                normalize_for_match("Βάθος Εξωτερικής Μονάδας ( mm )"),
            )
        ]
        == "278"
    )
    assert (
        values[
            (
                normalize_for_match("Γενικά Χαρακτηριστικά"),
                normalize_for_match("Εγγύηση Κατασκευαστή ( Εσωτερική μονάδα ) - Έτη"),
            )
        ]
        == "10"
    )
    assert (
        values[
            (
                normalize_for_match("Γενικά Χαρακτηριστικά"),
                normalize_for_match("Εγγύηση Κατασκευαστή ( Συμπιεστής ) - Έτη"),
            )
        ]
        == "10"
    )


def test_skroutz_portable_air_conditioner_compact_specs_fill_template() -> None:
    source = SourceProductData(
        source_name="skroutz",
        name="Midea Φορητό Κλιματιστικό 12000 BTU Ψύξης/Θέρμανσης",
        key_specs=[
            SpecItem(label="Απόδοση Ψύξης", value="12000 BTU"),
            SpecItem(label="Ενεργειακή Κλάση Ψύξης", value="A"),
            SpecItem(label="Επίπεδο Θορύβου", value="64 dB"),
            SpecItem(label="WiFi", value="Ναι"),
        ],
        spec_sections=[
            SpecSection(
                section="Ψύξη & Θέρμανση (BTU)",
                items=[
                    SpecItem(label="Απόδοση Ψύξης", value="12000 BTU"),
                    SpecItem(label="Απόδοση Θέρμανσης", value="12000 BTU"),
                    SpecItem(label="Ενεργειακή Κλάση Ψύξης", value="A"),
                    SpecItem(label="Ενεργειακή Κλάση Θέρμανσης", value="A"),
                ],
            ),
            SpecSection(
                section="Λειτουργίες Άνεσης & Smart Features",
                items=[
                    SpecItem(label="WiFi", value="Ναι"),
                    SpecItem(label="Λειτουργία Follow Me", value="Ναι"),
                    SpecItem(label="Χρονοδιακόπτης", value="Ναι"),
                    SpecItem(label="Λειτουργία Αφύγρανσης", value="Όχι"),
                ],
            ),
            SpecSection(
                section="Επιπλέον & Εξοπλισμός",
                items=[
                    SpecItem(label="Ιονιστής", value="Ναι"),
                    SpecItem(label="Φίλτρα Καθαρισμού Αέρα", value="Όχι"),
                    SpecItem(label="Διαστάσεις (Π x Β x Υ)", value="39.7x46.7x76.5 cm"),
                ],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf_category="Κλιματιστικά",
        sub_category="Φορητά",
    )

    _html, diagnostics, warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=PORTABLE_AIR_CONDITIONER_SCHEMA_ID, score=0.95
        ),
    )

    values = {
        (
            normalize_for_match(field["section"]),
            normalize_for_match(field["label"]),
        ): field["value"]
        for field in diagnostics["fields"]
    }

    assert diagnostics["preferred_schema_source_files"] == ["forita.json"]
    assert diagnostics["unresolved_count"] < 27
    assert (
        f"characteristics_template_used:schema:{PORTABLE_AIR_CONDITIONER_SCHEMA_ID}"
        in warnings
    )
    assert (
        values[
            (
                normalize_for_match("Ψυκτική / Θερμική Απόδοση"),
                normalize_for_match("Ονομαστική Απόδοση (Btu/h)"),
            )
        ]
        == "12000 BTU"
    )
    assert (
        values[
            (
                normalize_for_match("Ψυκτική / Θερμική Απόδοση"),
                normalize_for_match("Θερμική Απόδοση ( Btu/h )"),
            )
        ]
        == "12000 BTU"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Ηχητική Ισχύς Εσωτερικής Μονάδας dB(A) - Hi"),
            )
        ]
        == "64 dB"
    )
    assert (
        values[
            (
                normalize_for_match("Διαστάσεις και Βάρος"),
                normalize_for_match("Ύψος Εσωτερικής Μονάδας ( mm )"),
            )
        ]
        == "765"
    )
    assert (
        values[
            (
                normalize_for_match("Διαστάσεις και Βάρος"),
                normalize_for_match("Πλάτος Εσωτερικής Μονάδας ( mm )"),
            )
        ]
        == "397"
    )
    assert (
        values[
            (
                normalize_for_match("Διαστάσεις και Βάρος"),
                normalize_for_match("Βάθος Εσωτερικής Μονάδας ( mm )"),
            )
        ]
        == "467"
    )


def test_bestprice_wall_air_conditioner_aliases_fill_electronet_template() -> None:
    source = SourceProductData(
        source_name="bestprice",
        url="https://www.bestprice.gr/item/2160501610/inventor-neo-plus-npvi-24wfi-npvo24-klimatistiko-inverter-24000-btu-a-plus-plus-a-plus-plus-plus-me-ionisti-kai-wi-fi.html",
        name="Inventor Neo Plus NPVI-24WFI/NPVO24 Κλιματιστικό Inverter 24000 BTU",
        brand="Inventor",
        spec_sections=[
            SpecSection(
                section="Χαρακτηριστικά",
                items=[
                    SpecItem(label="Κατασκευαστής", value="Inventor"),
                    SpecItem(label="Θερμική Απόδοση", value="24.000BTU"),
                    SpecItem(label="Ψυκτική Απόδοση", value="24.000BTU"),
                    SpecItem(label="Χώρος Κάλυψης (Κατά Προσέγγιση)", value="50τμ"),
                    SpecItem(label="Απόδοση BTU", value="24000 BTU"),
                    SpecItem(label="Βαθμός Θερμικής Απόδοσης (SCOP)", value="5,1W/W"),
                    SpecItem(label="Ενεργειακή Κλάση Ψύξης", value="A++"),
                    SpecItem(label="Ενεργειακή Κλάση Θέρμανσης", value="A+++"),
                    SpecItem(label="Βαθμός Απόδοσης SEER", value="6,4"),
                    SpecItem(label="Βάρος Εσωτερικής Μονάδας", value="13,6kg"),
                    SpecItem(label="Βάρος Εξωτερικής Μονάδας", value="43,9kg"),
                    SpecItem(label="Ύψος Εξωτερικής Μονάδα", value="673mm"),
                    SpecItem(label="Μήκος Εξωτερικής Μονάδα", value="955mm"),
                    SpecItem(label="Βάθος Εξωτερικής Μονάδα", value="342mm"),
                    SpecItem(label="Ύψος Εσωτερικής Μονάδας", value="336mm"),
                    SpecItem(label="Μήκος Εσωτερικής Μονάδας", value="1.083mm"),
                    SpecItem(label="Βάθος Εσωτερικής Μονάδας", value="244mm"),
                    SpecItem(label="Θόρυβος Εξωτερικής Μονάδας", value="62dB"),
                    SpecItem(label="Θόρυβος Εσωτερικής Μονάδας", value="47dB"),
                    SpecItem(label="Inverter", value="✓"),
                    SpecItem(label="Υγραντήρας", value="✕"),
                    SpecItem(label="Ιονιστής", value="✓"),
                    SpecItem(label="Αφύγρανση", value="✓"),
                    SpecItem(label="Wifi Ready", value="✓"),
                    SpecItem(label="Οικολογικό Ψυκτικό Υγρό R32", value="✓"),
                    SpecItem(label="Φίλτρα Καθαρισμού Αέρα", value="✓"),
                    SpecItem(label="Χρώμα", value="Άσπρο"),
                ],
            )
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf_category="Κλιματιστικά",
        sub_category="Τοίχου",
        taxonomy_path="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ > Κλιματιστικά > Τοίχου",
    )

    _html, diagnostics, warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=AIR_CONDITIONER_SCHEMA_ID, score=0.95
        ),
    )

    values = {
        (
            normalize_for_match(field["section"]),
            normalize_for_match(field["label"]),
        ): field["value"]
        for field in diagnostics["fields"]
    }

    assert diagnostics["template_source"] == "schema_library"
    assert (
        f"characteristics_template_used:schema:{AIR_CONDITIONER_SCHEMA_ID}" in warnings
    )
    assert (
        values[
            (
                normalize_for_match("Ψυκτική / Θερμική Απόδοση"),
                normalize_for_match("Ονομαστική Απόδοση (Btu/h)"),
            )
        ]
        == "24000 BTU"
    )
    assert (
        values[
            (
                normalize_for_match("Ψυκτική / Θερμική Απόδοση"),
                normalize_for_match("Ψυκτική Απόδοση ( Btu/h )"),
            )
        ]
        == "24.000BTU"
    )
    assert (
        values[
            (
                normalize_for_match("Ψυκτική / Θερμική Απόδοση"),
                normalize_for_match("Θερμική Απόδοση ( Btu/h )"),
            )
        ]
        == "24.000BTU"
    )
    assert (
        values[
            (
                normalize_for_match("Βαθμοί Εποχιακής Απόδοσης"),
                normalize_for_match("Βαθμός Εποχιακής Απόδοσης Ψύξης - SEER"),
            )
        ]
        == "6,4"
    )
    assert (
        values[
            (
                normalize_for_match("Βαθμοί Εποχιακής Απόδοσης"),
                normalize_for_match(
                    "Βαθμός Εποχιακής Απόδοσης Θέρμανσης Μέσης Εποχής - SCOP"
                ),
            )
        ]
        == "5,1W/W"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Τεχνολογία Κλιματιστικού"),
            )
        ]
        == "Inverter"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Ψυκτικό Υγρό"),
            )
        ]
        == "R32"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Ηχητική Ισχύς Εσωτερικής Μονάδας dB(A) - Hi"),
            )
        ]
        == "47dB"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Ηχητική Ισχύς Εξωτερικής Μονάδας dB(A) - Hi"),
            )
        ]
        == "62dB"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Αφύγρανση"),
            )
        ]
        == "Ναι"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Ιονιστής"),
            )
        ]
        == "Ναι"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Φίλτρα"),
            )
        ]
        == "Φίλτρα Καθαρισμού Αέρα"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Πρόσθετες Λειτουργίες Κλιματιστικού"),
            )
        ]
        == "WiFi"
    )
    assert (
        values[
            (
                normalize_for_match("Διαστάσεις και Βάρος"),
                normalize_for_match("Πλάτος Εσωτερικής Μονάδας ( mm )"),
            )
        ]
        == "1083"
    )
    assert (
        values[
            (
                normalize_for_match("Διαστάσεις και Βάρος"),
                normalize_for_match("Πλάτος Εξωτερικής Μονάδας ( mm )"),
            )
        ]
        == "955"
    )
    assert (
        values[
            (normalize_for_match("Γενικά Χαρακτηριστικά"), normalize_for_match("Χρώμα"))
        ]
        == "Άσπρο"
    )


def test_kotsovolos_wall_air_conditioner_aliases_fill_electronet_template() -> None:
    source = SourceProductData(
        source_name="kotsovolos",
        url="https://www.kotsovolos.gr/air-condition-heaters/air-condition/7000-to-15000-btu/245318-a-c-in18btu-inventor-ar5vi-18wfi-aria",
        name="Inventor AR5VI-18WFI Aria 18.000 BTU/h Κλιματιστικό Inverter",
        brand="Inventor",
        spec_sections=[
            SpecSection(
                section="Χαρακτηριστικά",
                items=[
                    SpecItem(label="Ονομαστική απόδοση (Btu/h)", value="18.000"),
                    SpecItem(label="Ψυκτική (Btu/h)", value="18000 (11.570-20.130)"),
                    SpecItem(label="Συνδεσιμότητα (WiFi)", value="WiFi"),
                    SpecItem(label="Ιονιστής", value="Διαθέτει"),
                    SpecItem(label="Ψυκτική Ισχύς (kW)", value="5.3"),
                    SpecItem(label="Ενεργειακή Κλάση Ψύξης", value="Α++"),
                    SpecItem(label="Θερμική Απόδοση (BΤU/h)", value="19000"),
                    SpecItem(
                        label="Ενεργειακή Κλάση Θέρμανσης (Θερμής Ζώνης)",
                        value="A+++",
                    ),
                    SpecItem(label="Βαθμός ενεργειακής απόδοσης (SEER)", value="7.0"),
                    SpecItem(label="Βαθμός θερμικής απόδοσης (SCOP)", value="5.1"),
                    SpecItem(
                        label="Κατανάλωση Ενέργειας σε kWh ετησίως (ψύξη)",
                        value="265",
                    ),
                    SpecItem(
                        label="Κατανάλωση Ενέργειας σε kWh ετησίως (θέρμανση)",
                        value="1308",
                    ),
                    SpecItem(label="Θερμική Ισχύς (kW)", value="4.5"),
                    SpecItem(
                        label="Ηχητική Ισχύς Εσωτερικής Μονάδας (dB)",
                        value="57",
                    ),
                    SpecItem(
                        label="Ηχητική Ισχύς Εξωτερικής Μονάδας (dB)",
                        value="65",
                    ),
                    SpecItem(label="Επιπλέον", value="All DC Inverter, R32 Ψυκτικό Μέσο"),
                    SpecItem(label="Τύπος Φίλτρου", value="Φιλτράρισμα πέντε σταδίων"),
                    SpecItem(
                        label="Διαστάσεις Εσωτερικής Μονάδας (ΥxΠxΒ mm)",
                        value="319 x 965 x 215",
                    ),
                    SpecItem(
                        label="Διαστάσεις Εξωτερικής Μονάδας (ΥxΠxΒ mm)",
                        value="554 x 805 x 330",
                    ),
                    SpecItem(label="Συνδεσιμότητα", value="Wi-Fi Standard"),
                ],
            )
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf_category="Κλιματιστικά",
        sub_category="Τοίχου",
        taxonomy_path="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ > Κλιματιστικά > Τοίχου",
    )

    _html, diagnostics, _warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=AIR_CONDITIONER_SCHEMA_ID, score=0.95
        ),
    )

    values = {
        (
            normalize_for_match(field["section"]),
            normalize_for_match(field["label"]),
        ): field["value"]
        for field in diagnostics["fields"]
    }

    assert (
        values[
            (
                normalize_for_match("Ψυκτική / Θερμική Απόδοση"),
                normalize_for_match("Ψυκτική Απόδοση ( Btu/h )"),
            )
        ]
        == "18000 (11.570-20.130)"
    )
    assert (
        values[
            (
                normalize_for_match("Φορτίο Σχεδιασμού"),
                normalize_for_match("Φορτίου Σχεδιασμού Ψύξης ( kW/h )"),
            )
        ]
        == "5.3"
    )
    assert (
        values[
            (
                normalize_for_match("Καταναλώσεις"),
                normalize_for_match("Ετήσια Κατανάλωση Ψύξης ( kWh / a )"),
            )
        ]
        == "265"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Ιονιστής"),
            )
        ]
        == "Ναι"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Ψυκτικό Υγρό"),
            )
        ]
        == "R32"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Πρόσθετες Λειτουργίες Κλιματιστικού"),
            )
        ]
        == "WiFi"
    )
    assert (
        values[
            (
                normalize_for_match("Διαστάσεις και Βάρος"),
                normalize_for_match("Ύψος Εσωτερικής Μονάδας ( mm )"),
            )
        ]
        == "319"
    )
    assert (
        values[
            (
                normalize_for_match("Διαστάσεις και Βάρος"),
                normalize_for_match("Πλάτος Εξωτερικής Μονάδας ( mm )"),
            )
        ]
        == "805"
    )


def test_bestprice_wall_air_conditioner_summary_fills_feature_fallbacks() -> None:
    source = SourceProductData(
        source_name="bestprice",
        name="Inventor Neo Plus Κλιματιστικό Inverter με Ιονιστή και Wi-Fi",
        hero_summary="Διαθέτει ιονιστή για καθαρότερο αέρα και λειτουργία Wi-Fi.",
        spec_sections=[],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf_category="Κλιματιστικά",
        sub_category="Τοίχου",
    )

    _html, diagnostics, _warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=AIR_CONDITIONER_SCHEMA_ID, score=0.95
        ),
    )

    values = {
        (
            normalize_for_match(field["section"]),
            normalize_for_match(field["label"]),
        ): field["value"]
        for field in diagnostics["fields"]
    }

    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Τεχνολογία Κλιματιστικού"),
            )
        ]
        == "Inverter"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Ιονιστής"),
            )
        ]
        == "Ναι"
    )
    assert (
        values[
            (
                normalize_for_match("Επιπλέον Χαρακτηριστικά"),
                normalize_for_match("Πρόσθετες Λειτουργίες Κλιματιστικού"),
            )
        ]
        == "WiFi"
    )


def test_electronet_without_specs_uses_blank_template_for_specific_category_from_url() -> (
    None
):
    source = SourceProductData(
        source_name="electronet",
        url="https://www.electronet.gr/klimatismos-thermansi/klimatistika/klimatistika-toihoy/ac-midea-rf-new-ms12fu-12hrdn1-qrd0gw",
        canonical_url="https://www.electronet.gr/klimatismos-thermansi/klimatistika/klimatistika-toihoy/ac-midea-rf-new-ms12fu-12hrdn1-qrd0gw",
        brand="Midea",
        mpn="MS12FU-12HRDN1-QRD0GW",
        name="A/C Midea RF New MS12FU-12HRDN1-QRD0GW 12000Btu",
        hero_summary="Κλιματιστικό τοίχου inverter Midea RF New 12000Btu ενεργειακής κλάσης A++.",
        spec_sections=[],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf_category="Κλιματιστικά",
        taxonomy_path="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ > Κλιματιστικά > -",
    )

    html, diagnostics, warnings = build_characteristics_for_product(source, taxonomy)

    values = [field["value"] for field in diagnostics["fields"]]
    assert html
    assert diagnostics["template_source"] == "electronet_blank_schema"
    assert diagnostics["matched_schema_id"] == AIR_CONDITIONER_SCHEMA_ID
    assert diagnostics["preferred_schema_source_files"] == ["toixoy.json"]
    assert diagnostics["unresolved_count"] == len(values)
    assert set(values) == {"-"}
    assert (
        f"characteristics_template_used:electronet_blank:{AIR_CONDITIONER_SCHEMA_ID}"
        in warnings
    )


def test_labels_related_treats_dimension_separators_as_equivalent() -> None:
    assert _labels_related(
        normalize_for_match("Διαστάσεις Συσκευής σε Εκατοστά (Υ χ Π χ Β)"),
        normalize_for_match("Διαστάσεις Συσκευής σε Εκατοστά (Υ × Π × Β)"),
    )


def write_tv_raw_html(tmp_path: Path) -> Path:
    raw_html = """
    <html>
      <body>
        <div class="product-name" title='Hisense 55A6Q TV, 55" (139.7cm) 4K/UHD DLED Smart TV, HDR10+, Dolby Vision, Dolby Atmos, DTS Virtual:X, DVB-T2/C/S2, Wi-Fi, Bluetooth, LAN, 3x HDMI, 2x USB'></div>
        <div class="product-name" title='Hisense 55" A6Q, 4K Ultra HD 3840x2160, DLED, DFA, Precision Colour, HDR 10+, HLG, Dolby Vision, Smart TV, AnyView Cast, Gaming Mode, 1xHDMI2 eArc, 3xHDMI, 2xUSB, LAN, CI+, DVB-T2/C/S2, Black'></div>
        <p class="usp-description">Έχεις τουλάχιστον 2 χρόνια εγγύηση.</p>
        <dl><dt>Λογισμικό</dt><dd>Vidaa</dd></dl>
      </body>
    </html>
    """
    path = tmp_path / "143051-tv.html"
    path.write_text(raw_html, encoding="utf-8")
    return path


def make_tv_source(tmp_path: Path) -> SourceProductData:
    raw_html_path = write_tv_raw_html(tmp_path)
    return SourceProductData(
        source_name="skroutz",
        page_type="product",
        url="https://www.skroutz.gr/s/61351575/hisense-smart-tileorasi-55-4k-uhd-led-a6q-hdr-2025-55a6q.html",
        canonical_url="https://www.skroutz.gr/s/61351575/hisense-smart-tileorasi-55-4k-uhd-led-a6q-hdr-2025-55a6q.html",
        name='Hisense Smart Τηλεόραση 55" 4K UHD LED A6Q HDR (2025) 55A6Q',
        hero_summary=(
            "Το AI 4K Upscaler της Hisense αναβαθμίζει το περιεχόμενο σε 4K. "
            "Το Game Mode PLUS και το Game Bar βελτιώνουν το gaming, ενώ οι τεχνολογίες VRR και ALLM "
            "μειώνουν την καθυστέρηση. Η Hisense TV αποδίδει Dolby Audio και DTS Virtual:X."
        ),
        presentation_source_text=(
            "Το AI 4K Upscaler αναβαθμίζει την εικόνα. "
            "Το Game Mode PLUS και το Game Bar προσθέτουν έλεγχο. "
            "Το Hisense Voice Remote διευκολύνει τη χρήση."
        ),
        raw_html_path=str(raw_html_path),
        taxonomy_tv_inches=55,
        key_specs=[
            SpecItem(label="Διαγώνιος", value='55 "'),
            SpecItem(label="Ευκρίνεια", value="4K Ultra HD"),
            SpecItem(label="Ρυθμός Ανανέωσης", value="50/60 Hz"),
            SpecItem(label="Τύπος Panel", value="Direct LED"),
            SpecItem(label="Τύποι HDR", value="HDR10, HDR10+, Dolby Vision, HLG"),
            SpecItem(label="Κανάλια", value="2.1"),
            SpecItem(label="Ισχύς", value="20 W"),
        ],
        spec_sections=[
            SpecSection(
                section="Εικόνα",
                items=[
                    SpecItem(label="Διαγώνιος", value='55 "'),
                    SpecItem(label="Ευκρίνεια", value="4K Ultra HD"),
                    SpecItem(label="Ρυθμός Ανανέωσης", value="50/60 Hz"),
                    SpecItem(label="Τύπος Panel", value="Direct LED"),
                    SpecItem(
                        label="Τύποι HDR", value="HDR10, HDR10+, Dolby Vision, HLG"
                    ),
                ],
            ),
            SpecSection(
                section="Ήχος",
                items=[
                    SpecItem(label="Κανάλια", value="2.1"),
                    SpecItem(label="Ισχύς", value="20 W"),
                    SpecItem(label="Πρότυπα Ήχου", value="DTS Virtual: X"),
                ],
            ),
            SpecSection(
                section="Δυνατότητες & Λειτουργίες",
                items=[SpecItem(label="Δέκτης", value="DVB-C, DVB-S2, DVB-T2")],
            ),
            SpecSection(
                section="Ενσύρματες Συνδέσεις",
                items=[
                    SpecItem(label="Πλήθος USB", value="2"),
                    SpecItem(label="Σύνολο Θυρών HDMI", value="3"),
                ],
            ),
            SpecSection(
                section="Γενικά",
                items=[
                    SpecItem(label="Βάρος", value="10,9 kg"),
                    SpecItem(label="VESA Mount", value="400 x 200 mm"),
                ],
            ),
            SpecSection(
                section="Ενεργειακή Ετικέτα",
                items=[SpecItem(label="Ενεργειακή Κλάση", value="E")],
            ),
            SpecSection(
                section="Διαστάσεις (με Βάση)",
                items=[
                    SpecItem(label="Πλάτος", value="1234 mm"),
                    SpecItem(label="Ύψος", value="751 mm"),
                    SpecItem(label="Πάχος", value="298 mm"),
                ],
            ),
        ],
    )


def make_tv_taxonomy() -> TaxonomyResolution:
    return TaxonomyResolution(
        parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        leaf_category="Τηλεοράσεις",
        sub_category="50'' & άνω",
        cta_url="https://www.etranoulis.gr/eikona-hxos/thleoraseis/50-anw",
    )


def test_build_row_uses_schema_first_tv_characteristics_template(
    tmp_path: Path,
) -> None:
    source = make_tv_source(tmp_path)
    cli = CLIInput(
        model="143051",
        url=source.url,
        photos=4,
        sections=6,
        skroutz_status=1,
        boxnow=0,
        price="329",
    )
    parsed = ParsedProduct(source=source)
    row, normalized, warnings = build_row(
        cli=cli,
        parsed=parsed,
        taxonomy=make_tv_taxonomy(),
        schema_match=SchemaMatchResult(
            matched_schema_id=TV_TEMPLATE_SCHEMA_ID, score=0.9
        ),
    )

    soup = BeautifulSoup(row["characteristics"], "lxml")
    section_titles = [
        normalize_for_match(node.get_text(" ", strip=True))
        for node in soup.select("thead strong")
    ]
    labels = [
        normalize_for_match(node.get_text(" ", strip=True))
        for node in soup.select("tbody tr td:first-child")
    ]
    values = [
        node.get_text(" ", strip=True) for node in soup.select("tbody tr td strong")
    ]
    normalized_values = [normalize_for_match(value) for value in values]
    diagnostics = normalized["characteristics_diagnostics"]

    assert normalize_for_match("Εικόνα - Ήχος") in section_titles
    assert normalize_for_match("Λειτουργίες") in section_titles
    assert normalize_for_match("Συνδέσεις") in section_titles
    assert normalize_for_match("Γενικά") in section_titles
    assert normalize_for_match("Τεχνολογία Οθόνης") in labels
    assert normalize_for_match("Διαγώνιος Οθόνης ( Ίντσες )") in labels
    assert "ULTRA HD ( 4K )" in values
    assert "DVB-T2/C/S2" in values
    assert "Ναι,3,eARC" in values
    assert "Ναι,2" in values
    assert normalize_for_match("200 × 400") in normalized_values
    assert "75.10 × 123.40 × 29.80" in values
    assert diagnostics["template_id"] == f"schema:{TV_TEMPLATE_SCHEMA_ID}"
    assert diagnostics["template_source"] == "schema_library_with_custom_overrides"
    assert diagnostics["custom_template_id"] == "skroutz_tv_v1"
    assert diagnostics["matched_schema_id"] == TV_TEMPLATE_SCHEMA_ID
    assert (
        diagnostics["selection_reason"]
        == "matched_schema_template_with_custom_overrides"
    )
    assert f"characteristics_template_used:schema:{TV_TEMPLATE_SCHEMA_ID}" in warnings


def test_bestprice_tv_characteristics_use_label_alias_families() -> None:
    source = SourceProductData(
        source_name="bestprice",
        page_type="product",
        url="https://www.bestprice.gr/item/2163977668/tcl-sqd-mini-led-65c8l-smart-tileorasi-65-4k-uhd-mini-led-hdr.html",
        canonical_url="https://www.bestprice.gr/item/2163977668/tcl-sqd-mini-led-65c8l-smart-tileorasi-65-4k-uhd-mini-led-hdr.html",
        name='TCL SQD-Mini LED 65C8L Smart Τηλεόραση 65" 4K UHD Mini LED HDR',
        brand="TCL",
        taxonomy_tv_inches=65,
        spec_sections=[
            SpecSection(
                section="Χαρακτηριστικά",
                items=[
                    SpecItem(label="Panel", value="Mini LED"),
                    SpecItem(label="Ανάλυση", value="4K Ultra HD"),
                    SpecItem(label="Μέγιστη Ανάλυση", value="3840 x 2160 (4K UHD)"),
                    SpecItem(
                        label="Διαστάσεις με βάση (ΠxΒxΥ)", value="1434 x 368 x 860"
                    ),
                    SpecItem(label="Βάρος", value="21,1kg"),
                    SpecItem(label="HDMI 2.1 Θύρες", value="4"),
                    SpecItem(label="USB Θύρες", value="1"),
                    SpecItem(
                        label="Ενσύρματες Συνδέσεις",
                        value="USB • CI Slot • Είσοδος RF • Ethernet • HDMI 2.1 • Digital Audio Optical",
                    ),
                    SpecItem(
                        label="Πρότυπα Ήχου",
                        value="Dolby Atmos • Dolby TrueHD • Dolby AC-4",
                    ),
                    SpecItem(label="Νέα Ενεργειακή Κλάση", value="D"),
                    SpecItem(label="VESA Mount", value="300x300"),
                    SpecItem(
                        label="Υποστηριζόμενα Πρότυπα",
                        value="DVB-T • DVB-T2 • DVB-S • DVB-S2 • DVB-C",
                    ),
                    SpecItem(label="Smart Assistant", value="Google Assistant"),
                    SpecItem(label="Smart Οικοσύστημα", value="Google Home"),
                    SpecItem(label="Ρυθμός Ανανέωσης", value="144Hz"),
                    SpecItem(label="Λογισμικό", value="Google TV"),
                    SpecItem(
                        label="Εγκατεστημένες Εφαρμογές", value="Netflix • YouTube"
                    ),
                    SpecItem(
                        label="HDR Type", value="HDR10 • HDR10+ • HLG • Dolby Vision"
                    ),
                    SpecItem(
                        label="Ασύρματες Συνδέσεις",
                        value="WiFi • Bluetooth • Miracast • AirPlay • Chromecast Built-In • Screen Mirroring",
                    ),
                ],
            )
        ],
    )

    row, normalized, warnings = build_row(
        cli=CLIInput(
            model="143667",
            url=source.url,
            photos=1,
            sections=0,
            skroutz_status=1,
            boxnow=0,
            price="0",
        ),
        parsed=ParsedProduct(source=source),
        taxonomy=make_tv_taxonomy(),
        schema_match=SchemaMatchResult(
            matched_schema_id=TV_TEMPLATE_SCHEMA_ID, score=0.9
        ),
    )

    soup = BeautifulSoup(row["characteristics"], "lxml")
    values_by_label = {
        normalize_for_match(cells[0].get_text(" ", strip=True)): cells[1].get_text(
            " ", strip=True
        )
        for cells in (
            [cell for cell in row_node.select("td")]
            for row_node in soup.select("tbody tr")
        )
        if len(cells) >= 2
    }

    assert values_by_label[normalize_for_match("Τεχνολογία Οθόνης")] == "Mini LED"
    assert values_by_label[normalize_for_match("Ανάλυση Οθόνης")] == "ULTRA HD ( 4K )"
    assert values_by_label[normalize_for_match("Αριθμός Pixels")] == "3840 × 2160"
    assert (
        values_by_label[normalize_for_match("HDR")]
        == "HDR10,HDR10+,Dolby Vision ™HDR,HLG"
    )
    assert values_by_label[normalize_for_match("Ενεργειακή Κλάση")] == "D"
    assert values_by_label[normalize_for_match("Δέκτης")] == "DVB-T2/C/S2"
    assert (
        values_by_label[normalize_for_match("Σύστημα Ήχου")]
        == "Dolby Atmos,Dolby TrueHD,Dolby AC-4"
    )
    assert values_by_label[normalize_for_match("Smart TV")] == "Υποστηρίζεται"
    assert values_by_label[normalize_for_match("Λειτουργικό Σύστημα")] == "Google TV"
    assert (
        values_by_label[normalize_for_match("Λειτουργίες Smart")] == "Netflix • YouTube"
    )
    assert values_by_label[normalize_for_match("HDMI")] == "Ναι,4"
    assert values_by_label[normalize_for_match("Bluetooth")] == "Bluetooth"
    assert values_by_label[normalize_for_match("USB")] == "Ναι,1"
    assert "CI" in values_by_label[normalize_for_match("Είσοδοι / 'Εξοδοι")]
    assert (
        values_by_label[normalize_for_match("Διάκενο Βάσης Τοίχου Vesa (mm)")]
        == "300 × 300"
    )
    assert (
        values_by_label[
            normalize_for_match("Διαστάσεις Συσκευής σε Εκατοστά με Βάση (Υ x Π x Β)")
        ]
        == "86.00 × 143.40 × 36.80"
    )
    assert normalized["characteristics_diagnostics"]["unresolved_count"] < 24
    assert "characteristics_template_unresolved_fields:24" not in warnings


def test_tv_characteristics_prefer_extracted_specs_over_skroutz_help_text(
    tmp_path: Path,
) -> None:
    raw_html = """
    <html><body>
      <p>Υπάρχουν διάφορα πρότυπα HDR, όπως HDR10, Dolby Vision, HLG και HDR10+.</p>
      <p>VRR Όχι VRR μία τηλεόραση με Variable Refresh Rate μπορεί να προσαρμόσει τον ρυθμό.</p>
    </body></html>
    """
    raw_html_path = tmp_path / "142659-tv.html"
    raw_html_path.write_text(raw_html, encoding="utf-8")
    source = SourceProductData(
        source_name="skroutz",
        name='TCL Smart Τηλεόραση 43" 4K UHD LED P6K HDR (2025) 43P6K',
        brand="TCL",
        mpn="43P6K",
        hero_summary="Το High Dynamic Range (HDR) παρέχει ζωντανά χρώματα.",
        raw_html_path=str(raw_html_path),
        taxonomy_tv_inches=43,
        key_specs=[
            SpecItem(label="Διαγώνιος", value='43 "'),
            SpecItem(label="Ευκρίνεια", value="4K Ultra HD"),
            SpecItem(label="Ρυθμός Ανανέωσης", value="50/60 Hz"),
            SpecItem(label="Τύπος Panel", value="Direct LED"),
            SpecItem(label="Τύποι HDR", value="HDR10, HLG, AI Picture"),
            SpecItem(label="Local Dimming", value="Όχι"),
        ],
        spec_sections=[
            SpecSection(
                section="Εικόνα",
                items=[
                    SpecItem(label="Διαγώνιος", value='43 "'),
                    SpecItem(label="Ευκρίνεια", value="4K Ultra HD"),
                    SpecItem(label="Ρυθμός Ανανέωσης", value="50/60 Hz"),
                    SpecItem(label="Τύπος Panel", value="Direct LED"),
                    SpecItem(label="Τύποι HDR", value="HDR10, HLG, AI Picture"),
                ],
            ),
            SpecSection(
                section="Ενεργειακή Ετικέτα",
                items=[SpecItem(label="Ενεργειακή Κλάση", value="F")],
            ),
            SpecSection(
                section="Smart Δυνατότητες",
                items=[
                    SpecItem(
                        label="Υποστηριζόμενες Εφαρμογές",
                        value="Netflix, Youtube, DisneyPlus, Apple TV, Cosmote TV, Prime Video, Eon, Ant1+, Ertflix, Spotify",
                    ),
                    SpecItem(label="Λογισμικό", value="Google TV"),
                ],
            ),
            SpecSection(
                section="Δυνατότητες & Λειτουργίες",
                items=[SpecItem(label="VRR", value="Όχι")],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        leaf_category="Τηλεοράσεις",
        sub_category="33''-50''",
        taxonomy_path="ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > 33''-50''",
    )

    row, _normalized, _warnings = build_row(
        cli=CLIInput(
            model="142659",
            url=source.url,
            photos=8,
            sections=7,
            skroutz_status=1,
            boxnow=0,
            price="299",
        ),
        parsed=ParsedProduct(source=source),
        taxonomy=taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=TV_TEMPLATE_SCHEMA_ID, score=0.9
        ),
    )

    soup = BeautifulSoup(row["characteristics"], "lxml")
    values_by_label = {
        normalize_for_match(cells[0].get_text(" ", strip=True)): cells[1].get_text(
            " ", strip=True
        )
        for cells in (
            [cell for cell in row_node.select("td")]
            for row_node in soup.select("tbody tr")
        )
        if len(cells) >= 2
    }

    assert values_by_label[normalize_for_match("HDR")] == "HDR10,HLG,AI Picture"
    assert values_by_label[normalize_for_match("Λειτουργίες Εικόνας")] == "-"
    assert values_by_label[normalize_for_match("Ενεργειακή Κλάση HDR")] == "-"
    assert values_by_label[normalize_for_match("Λειτουργικό Σύστημα")] == "Google TV"
    assert "Netflix" in values_by_label[normalize_for_match("Λειτουργίες Smart")]
    assert values_by_label[normalize_for_match("Είσοδοι / Έξοδοι")] == "-"


def test_characteristics_pipeline_falls_back_to_raw_sections_without_template() -> None:
    source = SourceProductData(
        source_name="electronet",
        name="Simple Product",
        spec_sections=[
            SpecSection(
                section="Γενικά", items=[SpecItem(label="Χρώμα", value="Λευκό")]
            )
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ", leaf_category="Κουζίνες"
    )

    html, diagnostics, warnings = build_characteristics_for_product(source, taxonomy)

    assert diagnostics["mode"] == "raw_spec_sections"
    assert diagnostics["template_id"] == ""
    assert warnings == []
    assert "<strong>Γενικά</strong>" in html
    assert "<td>Χρώμα</td>" in html


def test_characteristics_pipeline_uses_matched_schema_layout_for_generic_categories() -> (
    None
):
    source = SourceProductData(
        source_name="skroutz",
        name="Bosch Hood Example",
        spec_sections=[
            SpecSection(
                section="Επισκόπηση",
                items=[
                    SpecItem(label="Τρόπος Τοποθέτησης", value="Καμινάδα"),
                    SpecItem(label="Χειρισμός", value="Αφής"),
                    SpecItem(label="Μέγιστη Απόδοση Εξαγωγής Αέρα (m3/h)", value="650"),
                ],
            ),
            SpecSection(
                section="Ενεργειακά",
                items=[
                    SpecItem(label="Ενεργειακή Κλάση", value="A"),
                    SpecItem(label="Επίπεδο Θορύβου σε dB", value="62"),
                ],
            ),
            SpecSection(
                section="Γενικά",
                items=[
                    SpecItem(label="Χρώμα", value="Inox"),
                    SpecItem(label="Εγγύηση Κατασκευαστή", value="2 έτη"),
                ],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ", leaf_category="Απορροφητήρες"
    )

    html, diagnostics, warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(matched_schema_id=HOOD_SCHEMA_ID, score=0.91),
    )

    soup = BeautifulSoup(html, "lxml")
    section_titles = [
        normalize_for_match(node.get_text(" ", strip=True))
        for node in soup.select("thead strong")
    ]
    labels = [
        normalize_for_match(node.get_text(" ", strip=True))
        for node in soup.select("tbody tr td:first-child")
    ]
    values = [
        normalize_for_match(node.get_text(" ", strip=True))
        for node in soup.select("tbody tr td strong")
    ]

    assert diagnostics["mode"] == "template"
    assert diagnostics["template_id"] == f"schema:{HOOD_SCHEMA_ID}"
    assert diagnostics["template_source"] == "schema_library"
    assert diagnostics["custom_template_id"] == ""
    assert diagnostics["matched_schema_id"] == HOOD_SCHEMA_ID
    assert diagnostics["selection_reason"] == "matched_schema_template"
    assert f"characteristics_template_used:schema:{HOOD_SCHEMA_ID}" in warnings
    assert normalize_for_match("Επισκόπηση Προϊόντος") in section_titles
    assert normalize_for_match("Ενεργειακά Χαρακτηριστικά") in section_titles
    assert normalize_for_match("Γενικά Χαρακτηριστικά") in section_titles
    assert normalize_for_match("Επισκόπηση") not in section_titles
    assert normalize_for_match("Τρόπος Τοποθέτησης") in labels
    assert normalize_for_match("Ενεργειακή Κλάση") in labels
    assert normalize_for_match("Χρώμα") in labels
    assert normalize_for_match("Καμινάδα") in values
    assert normalize_for_match("a") in values
    assert normalize_for_match("inox") in values


def test_schema_matcher_prefers_template_source_files_for_tv_sections() -> None:
    sections = [
        SpecSection(
            section="Εικόνα",
            items=[
                SpecItem("Διαγώνιος", '55 "'),
                SpecItem("Ευκρίνεια", "4K Ultra HD"),
                SpecItem("Ρυθμός Ανανέωσης", "50/60 Hz"),
                SpecItem("Τύπος Panel", "Direct LED"),
                SpecItem("Τύποι HDR", "HDR10, HDR10+, Dolby Vision, HLG"),
                SpecItem("Local Dimming", "Όχι"),
            ],
        ),
        SpecSection(
            section="Ήχος",
            items=[
                SpecItem("Κανάλια", "2.1"),
                SpecItem("Ισχύς", "20 W"),
                SpecItem("Πρότυπα Ήχου", "DTS Virtual: X"),
            ],
        ),
        SpecSection(
            section="Δυνατότητες & Λειτουργίες",
            items=[
                SpecItem("Δέκτης", "DVB-C, DVB-S2, DVB-T2"),
                SpecItem("Media Player", "Ναι"),
                SpecItem("Εγγραφή PVR", "Όχι"),
                SpecItem("Hotel Mode", "Όχι"),
                SpecItem("Φωνητικές Εντολές", "Όχι"),
                SpecItem("HbbTV", "Όχι"),
                SpecItem("VRR", "Όχι"),
            ],
        ),
        SpecSection(
            section="Smart Δυνατότητες",
            items=[
                SpecItem(
                    "Υποστηριζόμενες Εφαρμογές",
                    "Netflix, Youtube, Prime Video, DisneyPlus, Eon",
                ),
                SpecItem("Λογισμικό", "Vidaa"),
            ],
        ),
        SpecSection(
            section="Ενσύρματες Συνδέσεις",
            items=[
                SpecItem("Ethernet", "Ναι"),
                SpecItem("Headphones", "Όχι"),
                SpecItem("Digital Audio Optical", "Ναι"),
                SpecItem("Πλήθος USB", "2"),
                SpecItem("Σύνολο Θυρών HDMI", "3"),
                SpecItem("Πλήθος HDMI 2.1", "-"),
            ],
        ),
        SpecSection(
            section="Ασύρματες Συνδέσεις",
            items=[
                SpecItem("Wi-Fi", "Ναι"),
                SpecItem("Bluetooth", "Όχι"),
                SpecItem("Miracast", "Όχι"),
                SpecItem("Chromecast Built-In", "Όχι"),
                SpecItem("Screen Mirroring", "Όχι"),
                SpecItem("AirPlay", "Ναι"),
            ],
        ),
        SpecSection(
            section="Γενικά",
            items=[
                SpecItem("Έτος Κυκλοφορίας", "2025"),
                SpecItem("Βάρος", "10,9 kg"),
                SpecItem("VESA Mount", "400 x 200 mm"),
            ],
        ),
        SpecSection(
            section="Ενεργειακή Ετικέτα", items=[SpecItem("Ενεργειακή Κλάση", "E")]
        ),
        SpecSection(
            section="Διαστάσεις (Χωρίς Βάση)",
            items=[
                SpecItem("Πλάτος", "1234 mm"),
                SpecItem("Ύψος", "716 mm"),
                SpecItem("Πάχος", "81 mm"),
            ],
        ),
        SpecSection(
            section="Διαστάσεις (με Βάση)",
            items=[
                SpecItem("Πλάτος", "1234 mm"),
                SpecItem("Ύψος", "751 mm"),
                SpecItem("Πάχος", "298 mm"),
            ],
        ),
    ]
    matcher = SchemaMatcher()

    default_result, _default_candidates = matcher.match(
        sections,
        taxonomy_sub_category="50'' & άνω",
        taxonomy_path="ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > 50'' & άνω",
        taxonomy_parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        taxonomy_leaf_category="Τηλεοράσεις",
    )
    preferred_result, preferred_candidates = matcher.match(
        sections,
        taxonomy_sub_category="50'' & άνω",
        preferred_source_files=["tileoraseis.json"],
        taxonomy_path="ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > 50'' & άνω",
        taxonomy_parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        taxonomy_leaf_category="Τηλεοράσεις",
    )

    assert default_result.matched_schema_id == TV_TEMPLATE_SCHEMA_ID
    assert preferred_result.matched_schema_id == TV_TEMPLATE_SCHEMA_ID
    assert preferred_candidates[0]["source_files"] == ["tileoraseis.json"]


def test_characteristics_registry_prefers_built_in_hob_schema_for_skroutz() -> None:
    registry = CharacteristicsTemplateRegistry()
    source = SourceProductData(source_name="skroutz", name="Neff Hob")
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Εντοιχιζόμενες Συσκευές",
        sub_category="Εστίες",
    )

    preferred_source_files = registry.preferred_schema_source_files(source, taxonomy)
    template = registry.select_template(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=BUILT_IN_HOB_SCHEMA_ID, score=0.9
        ),
    )

    assert preferred_source_files == ["esties.json"]
    assert template is not None
    assert template["matched_schema_id"] == BUILT_IN_HOB_SCHEMA_ID
    assert template["preferred_schema_source_files"] == ["esties.json"]
    assert template["template_source"] == "schema_library_with_custom_overrides"
    assert template["custom_template_id"] == "skroutz_built_in_hob_v1"


def test_characteristics_registry_prefers_air_conditioner_schema_for_skroutz() -> None:
    registry = CharacteristicsTemplateRegistry()
    source = SourceProductData(source_name="skroutz", name="Toyotomi Air Conditioner")
    taxonomy = TaxonomyResolution(
        parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf_category="Κλιματιστικά",
        sub_category="Τοίχου",
    )

    preferred_source_files = registry.preferred_schema_source_files(source, taxonomy)
    template = registry.select_template(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=AIR_CONDITIONER_SCHEMA_ID, score=0.9
        ),
    )

    assert preferred_source_files == ["toixoy.json"]
    assert template is not None
    assert template["matched_schema_id"] == AIR_CONDITIONER_SCHEMA_ID
    assert template["preferred_schema_source_files"] == ["toixoy.json"]
    assert template["template_source"] == "schema_library_with_custom_overrides"
    assert template["custom_template_id"] == "skroutz_wall_air_conditioner_v1"


def test_characteristics_registry_prefers_soundbar_schema_for_skroutz() -> None:
    registry = CharacteristicsTemplateRegistry()
    source = SourceProductData(source_name="skroutz", name="TCL Soundbar")
    taxonomy = TaxonomyResolution(
        parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        leaf_category="Audio Systems",
        sub_category="Sound Bars",
    )

    preferred_source_files = registry.preferred_schema_source_files(source, taxonomy)
    template = registry.select_template(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=SOUND_BAR_SCHEMA_ID, score=0.9
        ),
    )

    assert preferred_source_files == ["sound_bars.json"]
    assert template is not None
    assert template["matched_schema_id"] == SOUND_BAR_SCHEMA_ID
    assert template["preferred_schema_source_files"] == ["sound_bars.json"]
    assert template["template_source"] == "schema_library_with_custom_overrides"
    assert template["custom_template_id"] == "skroutz_soundbar_v1"


def test_characteristics_registry_prefers_washing_machine_schema_for_skroutz() -> None:
    registry = CharacteristicsTemplateRegistry()
    source = SourceProductData(source_name="skroutz", name="Samsung Washing Machine")
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Πλυντήρια-Στεγνωτήρια",
        sub_category="Πλυντήρια Ρούχων",
    )

    preferred_source_files = registry.preferred_schema_source_files(source, taxonomy)
    template = registry.select_template(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=WASHING_MACHINE_SCHEMA_ID, score=0.9
        ),
    )

    assert preferred_source_files == ["plyntiria_rouxwn.json"]
    assert template is not None
    assert template["template_id"] == "skroutz_washing_machine_v1"
    assert template["matched_schema_id"] == WASHING_MACHINE_SCHEMA_ID
    assert template["template_source"] == "custom"


def test_characteristics_pipeline_uses_raw_sections_for_skroutz_washing_machines() -> (
    None
):
    source = SourceProductData(
        source_name="skroutz",
        brand="Samsung",
        mpn="WW90DB7U94GBU3",
        name="Samsung Πλυντήριο Ρούχων 9kg WW90DB7U94GBU3",
        spec_sections=[
            SpecSection(
                section="Χαρακτηριστικά",
                items=[
                    SpecItem(label="Χωρητικότητα", value="9 kg"),
                    SpecItem(label="Τύπος", value="Εμπρόσθιας Φόρτωσης"),
                    SpecItem(label="Στροφές", value="1400 /λεπτό"),
                    SpecItem(label="Χρώμα", value="Μαύρο"),
                ],
            ),
            SpecSection(
                section="Νέα Ενεργειακή Ετικέτα",
                items=[
                    SpecItem(label="Ενεργειακή Κλάση", value="A"),
                    SpecItem(label="Κατανάλωση Ενέργειας", value="40 kwh/100 κύκλους"),
                ],
            ),
            SpecSection(
                section="Smart Ιδιότητες",
                items=[
                    SpecItem(label="Λειτουργίες Smart", value="Ναι"),
                    SpecItem(label="Συνδεσιμότητα", value="Wi-Fi"),
                ],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Πλυντήρια-Στεγνωτήρια",
        sub_category="Πλυντήρια Ρούχων",
    )

    html, diagnostics, warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=WASHING_MACHINE_SCHEMA_ID, score=0.91
        ),
    )

    soup = BeautifulSoup(html, "lxml")
    section_titles = [
        normalize_for_match(node.get_text(" ", strip=True))
        for node in soup.select("thead strong")
    ]
    labels = [
        normalize_for_match(node.get_text(" ", strip=True))
        for node in soup.select("tbody tr td:first-child")
    ]
    values = [
        node.get_text(" ", strip=True) for node in soup.select("tbody tr td strong")
    ]

    assert diagnostics["mode"] == "raw_spec_sections"
    assert diagnostics["template_id"] == "skroutz_washing_machine_v1"
    assert diagnostics["selection_reason"] == "taxonomy_template_raw_spec_sections"
    assert diagnostics["preferred_schema_source_files"] == ["plyntiria_rouxwn.json"]
    assert warnings == []
    assert normalize_for_match("Χαρακτηριστικά") in section_titles
    assert normalize_for_match("Νέα Ενεργειακή Ετικέτα") in section_titles
    assert normalize_for_match("Smart Ιδιότητες") in section_titles
    assert normalize_for_match("Χωρητικότητα") in labels
    assert normalize_for_match("Συνδεσιμότητα") in labels
    assert "9 kg" in values
    assert "Wi-Fi" in values


def test_characteristics_pipeline_uses_raw_sections_for_skroutz_ice_cream_makers() -> (
    None
):
    source = SourceProductData(
        source_name="skroutz",
        brand="Tefal",
        mpn="IG602A",
        name="Tefal Dolci Παγωτομηχανή 3x1.4lt Καφέ",
        spec_sections=[
            SpecSection(
                section="Παραγωγή & Δυνατότητες",
                items=[
                    SpecItem(label="Χωρητικότητα", value="1.4 lt"),
                    SpecItem(label="Αριθμός Δοχείων", value="3"),
                    SpecItem(label="Αριθμός Προγραμμάτων", value="10"),
                ],
            ),
            SpecSection(
                section="Σχεδιασμός & Εμφάνιση",
                items=[SpecItem(label="Χρώμα", value="Καφέ")],
            ),
        ],
        manufacturer_spec_sections=[
            SpecSection(
                section="Χαρακτηριστικά Κατασκευαστή",
                items=[
                    SpecItem(label="Τάση", value="220-240 V"),
                    SpecItem(label="Συχνότητα", value="50-60 Hz"),
                ],
            )
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Μικροί Μάγειρες",
        sub_category="Παγωτομηχανές",
    )

    html, diagnostics, warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=ICE_CREAM_MAKER_SCHEMA_ID, score=0.91
        ),
    )

    soup = BeautifulSoup(html, "lxml")
    section_titles = [
        normalize_for_match(node.get_text(" ", strip=True))
        for node in soup.select("thead strong")
    ]
    labels = [
        normalize_for_match(node.get_text(" ", strip=True))
        for node in soup.select("tbody tr td:first-child")
    ]
    values = [
        node.get_text(" ", strip=True) for node in soup.select("tbody tr td strong")
    ]

    assert diagnostics["mode"] == "raw_spec_sections"
    assert diagnostics["template_id"] == "skroutz_ice_cream_maker_v1"
    assert diagnostics["selection_reason"] == "taxonomy_template_raw_spec_sections"
    assert diagnostics["preferred_schema_source_files"] == ["pagotomixanes.json"]
    assert warnings == []
    assert normalize_for_match("Χαρακτηριστικά Κατασκευαστή") in section_titles
    assert normalize_for_match("Παραγωγή & Δυνατότητες") in section_titles
    assert normalize_for_match("Τάση") in labels
    assert normalize_for_match("Αριθμός Προγραμμάτων") in labels
    assert "220-240 V" in values
    assert "10" in values


def test_characteristics_pipeline_uses_raw_sections_for_manufacturer_tefal_ice_cream_makers() -> (
    None
):
    source = SourceProductData(
        source_name="manufacturer_tefal",
        brand="Tefal",
        mpn="IG602A",
        name="Tefal Dolci Παγωτομηχανή IG602A",
        spec_sections=[
            SpecSection(
                section="Παραγωγή & Δυνατότητες",
                items=[
                    SpecItem(label="Χωρητικότητα", value="1.4 lt"),
                    SpecItem(label="Αριθμός Δοχείων", value="3"),
                    SpecItem(label="Αριθμός Προγραμμάτων", value="10"),
                ],
            )
        ],
        manufacturer_spec_sections=[
            SpecSection(
                section="Χαρακτηριστικά Κατασκευαστή",
                items=[
                    SpecItem(label="Τάση", value="220-240 V"),
                    SpecItem(label="Συχνότητα", value="50-60 Hz"),
                ],
            )
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Μικροί Μάγειρες",
        sub_category="Παγωτομηχανές",
    )

    html, diagnostics, warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=ICE_CREAM_MAKER_SCHEMA_ID, score=0.91
        ),
    )

    soup = BeautifulSoup(html, "lxml")
    section_titles = [
        normalize_for_match(node.get_text(" ", strip=True))
        for node in soup.select("thead strong")
    ]
    labels = [
        normalize_for_match(node.get_text(" ", strip=True))
        for node in soup.select("tbody tr td:first-child")
    ]
    values = [
        node.get_text(" ", strip=True) for node in soup.select("tbody tr td strong")
    ]

    assert diagnostics["mode"] == "raw_spec_sections"
    assert diagnostics["template_id"] == "manufacturer_tefal_ice_cream_maker_v1"
    assert diagnostics["selection_reason"] == "taxonomy_template_raw_spec_sections"
    assert diagnostics["preferred_schema_source_files"] == ["pagotomixanes.json"]
    assert warnings == []
    assert normalize_for_match("Χαρακτηριστικά Κατασκευαστή") in section_titles
    assert normalize_for_match("Παραγωγή & Δυνατότητες") in section_titles
    assert normalize_for_match("Τάση") in labels
    assert normalize_for_match("Αριθμός Προγραμμάτων") in labels
    assert "220-240 V" in values
    assert "10" in values


def test_built_in_hob_characteristics_use_source_and_manufacturer_evidence() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Neff",
        mpn="T16BT60N0",
        name="Neff T16BT60N0 Hob",
        spec_sections=[
            SpecSection(
                section="Γενικά",
                items=[
                    SpecItem(label="Τύπος", value="Κεραμική"),
                    SpecItem(label="Αριθμός Εστιών", value="4"),
                    SpecItem(label="Διακόπτες", value="Αφής"),
                    SpecItem(label="Χρώμα", value="Μαύρο"),
                ],
            ),
            SpecSection(
                section="Δυνατότητες & Λειτουργίες",
                items=[
                    SpecItem(label="Smart", value="Όχι"),
                    SpecItem(label="Λειτουργία Κλειδώματος", value="Ναι"),
                    SpecItem(label="Χρονοδιακόπτης", value="Ναι"),
                    SpecItem(label="Ένδειξη Υπολοίπου Θερμότητας", value="Ναι"),
                ],
            ),
            SpecSection(
                section="Διαστάσεις Συσκευής",
                items=[
                    SpecItem(label="Ύψος", value="4,8 cm"),
                    SpecItem(label="Πλάτος", value="58,3 cm"),
                    SpecItem(label="Βάθος", value="51,3 cm"),
                ],
            ),
            SpecSection(
                section="Διαστάσεις Εντοιχισμού",
                items=[
                    SpecItem(label="Πλάτος Εντοιχισμού", value="56 cm"),
                    SpecItem(label="Βάθος Εντοιχισμού", value="50 cm"),
                ],
            ),
        ],
        manufacturer_spec_sections=[
            SpecSection(
                section="Τεχνικά στοιχεία",
                items=[
                    SpecItem(label="Τύπος εγκατάστασης", value="Εντοιχιζόμενη συσκευή"),
                    SpecItem(label="Τύπος λειτουργίας", value="Ηλεκτρική"),
                    SpecItem(label="Βασικό υλικό επιφανειών", value="Υαλοκεραμική"),
                    SpecItem(
                        label="Συνολικός αριθμός ζωνών που μπορούν να χρησιμοποιηθούν ταυτόχρονα",
                        value="4",
                    ),
                    SpecItem(
                        label="Διαστάσεις εντοιχισμού (υ x π x β)",
                        value="48 x 560 x 490 - 500 mm",
                    ),
                    SpecItem(
                        label="Διαστάσεις συσκευής (ΥxΠxΒ mm)", value="48 x 583 x 513"
                    ),
                    SpecItem(label="Καθαρό βάρος", value="8.0 kg"),
                    SpecItem(label="Χρώμα πλαισίου", value="Ανοξείδωτο"),
                ],
            ),
            SpecSection(
                section="Γενικά χαρακτηριστικά",
                items=[
                    SpecItem(
                        label="Είδος ηλεκτρονικού ελέγχου",
                        value="TwistPad4: πλήρης έλεγχος της ισχύος",
                    ),
                    SpecItem(
                        label="Ψηφιακό χρονόμετρο",
                        value="ένδειξη του χρόνου που έχει περάσει",
                    ),
                    SpecItem(
                        label="Αυτόματη απενεργοποίηση ασφαλείας",
                        value="η εστία σταματά να θερμαίνεται",
                    ),
                    SpecItem(
                        label="Κλείδωμα ασφαλείας για τα παιδιά",
                        value="αποτροπή ενεργοποίησης",
                    ),
                    SpecItem(label="Συνολική ισχύς", value="6.3 ΚW"),
                ],
            ),
        ],
        manufacturer_source_text=(
            "TwistPad 17 βαθμίδες ισχύος Λειτουργία Restart Λειτουργία Alarm "
            "Λειτουργία διατήρησης θερμότητας Ψηφιακό χρονόμετρο "
            "Μπροστά αριστερά: 145 mm, 1.2 ΚW Πίσω αριστερά: 210 mm, 120 mm, 0.75 ΚW "
            "Μπροστά δεξιά: 180 mm, 80 mm, 0.4 ΚW Πίσω δεξιά: 145 mm, 1.2 ΚW"
        ),
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Εντοιχιζόμενες Συσκευές",
        sub_category="Εστίες",
    )

    html, diagnostics, _warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=BUILT_IN_HOB_SCHEMA_ID, score=0.9
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
    assert values[normalize_for_match("Τρόπος Τοποθέτησης")] == "Εντοιχιζόμενη συσκευή"
    assert values[normalize_for_match("Τεχνολογία Πλατώ Εστιών")] == "Υαλοκεραμική"
    assert values[normalize_for_match("Αριθμός Ζωνών")] == "4"
    assert values[normalize_for_match("Τύπος Χειριστηρίου")] == "TwistPad®"
    assert values[normalize_for_match("Ψηφιακές Ενδείξεις")] == "Ναι"
    assert values[normalize_for_match("Σύνδεση με Φυσικό Αέριο")] == "Όχι"
    assert values[normalize_for_match("Συνδεσιμότητα")] == "Όχι"
    assert (
        values[normalize_for_match("Άλλα Χαρακτηριστικά")]
        == "17 βαθμίδες ισχύος, λειτουργία Restart, λειτουργία Alarm, διατήρηση θερμότητας"
    )
    assert values[normalize_for_match("Ισχύς Εστίας Μπροστά Αριστερά (KW")] == "1.2 kW"
    assert values[normalize_for_match("Ισχύς Εστίας Πίσω Αριστερά (KW")] == "0.75 kW"
    assert values[normalize_for_match("Μέγιστη Ονομαστική Ισχύς (W")] == "6300 W"
    assert values[normalize_for_match("Χρώμα Πλαισίου")] == "Ανοξείδωτο"
    assert values[normalize_for_match("Βάρος Συσκευής σε Κιλά")] == "8.0"
    assert values[normalize_for_match("Ύψος Διάστασης Εντοιχισμού")] == "4.8 cm"
    assert (
        values[normalize_for_match("Βάθος Διάστασης Εντοιχισμού σε Εκατοστά")]
        == "49 - 50 cm"
    )


def test_built_in_hob_characteristics_prefer_manufacturer_values_on_conflict() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Neff",
        mpn="T16BT60N0",
        name="Neff T16BT60N0 Hob",
        spec_sections=[
            SpecSection(
                section="Γενικά",
                items=[
                    SpecItem(label="Τύπος", value="Κεραμική"),
                    SpecItem(label="Αριθμός Εστιών", value="2"),
                    SpecItem(label="Διακόπτες", value="Αφής"),
                ],
            ),
        ],
        manufacturer_spec_sections=[
            SpecSection(
                section="Τεχνικά στοιχεία",
                items=[
                    SpecItem(label="Τύπος εγκατάστασης", value="Εντοιχιζόμενη συσκευή"),
                    SpecItem(label="Τύπος λειτουργίας", value="Ηλεκτρική"),
                    SpecItem(label="Βασικό υλικό επιφανειών", value="Υαλοκεραμική"),
                    SpecItem(
                        label="Συνολικός αριθμός ζωνών που μπορούν να χρησιμοποιηθούν ταυτόχρονα",
                        value="4",
                    ),
                ],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Εντοιχιζόμενες Συσκευές",
        sub_category="Εστίες",
    )

    html, diagnostics, _warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=BUILT_IN_HOB_SCHEMA_ID, score=0.9
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
    assert values[normalize_for_match("Τρόπος Τοποθέτησης")] == "Εντοιχιζόμενη συσκευή"
    assert values[normalize_for_match("Τεχνολογία Πλατώ Εστιών")] == "Υαλοκεραμική"
    assert values[normalize_for_match("Αριθμός Ζωνών")] == "4"
    assert values[normalize_for_match("Αριθμός Ζωνών")] != "2"


def test_skroutz_hair_straightener_characteristics_use_alias_enrichment() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="GA.MA",
        mpn="GI3034",
        name="GA.MA GI3034 Πρέσα Μαλλιών με Κεραμικές Πλάκες 45W",
        spec_sections=[
            SpecSection(
                section="Βασικά Χαρακτηριστικά",
                items=[
                    SpecItem(label="Κεραμικές Πλάκες", value="Ναι"),
                    SpecItem(label="Ατμός", value="Όχι"),
                    SpecItem(label="Επαγγελματική", value="Ναι"),
                    SpecItem(label="Ισχύς", value="45 W"),
                    SpecItem(label="Μέγιστη Θερμοκρασία", value="230 °C"),
                    SpecItem(label="Mini", value="-"),
                ],
            ),
            SpecSection(
                section="Λεπτομέρειες",
                items=[
                    SpecItem(label="Φαρδιές Πλάκες", value="Ναι"),
                    SpecItem(label="Επίστρωση Τουρμαλίνης", value="Όχι"),
                    SpecItem(label="Ionic", value="Όχι"),
                    SpecItem(label="Επίστρωση Τιτανίου", value="Ναι"),
                    SpecItem(label="Χρώμα", value="Μαύρο"),
                    SpecItem(label="Επίστρωση Κερατίνης", value="-"),
                    SpecItem(
                        label="Ειδικά Χαρακτηριστικά", value="Περιστρεφόμενο Καλώδιο"
                    ),
                    SpecItem(label="Σειρά", value="-"),
                ],
            ),
        ],
        presentation_source_text="Περιστρεφόμενο καλώδιο",
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Προσωπική Φροντίδα",
        sub_category="Βούρτσες-Ψαλίδια-ισιωτικά",
    )

    html, diagnostics, _warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=_schema_id_for_source_file("isiotika_mallion.json"),
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
    assert values[normalize_for_match("Τεχνολογία Πλάκας")] == "Κεραμική, Τιτανίου"
    assert values[normalize_for_match("Μέγιστη Θερμοκρασία σε °C")] == "230 °C"
    assert values[normalize_for_match("Σύστημα Ιονισμού")] == "Όχι"
    assert values[normalize_for_match("Περιστρεφόμενο Καλώδιο")] == "Ναι"


def test_skroutz_hair_straightener_characteristics_use_description_enrichment() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Demeliss",
        mpn="3990",
        name="Demeliss One 3990 Πρέσα Μαλλιών 46W",
        spec_sections=[
            SpecSection(
                section="Βασικά Χαρακτηριστικά",
                items=[
                    SpecItem(label="Κεραμικές Πλάκες", value="Όχι"),
                    SpecItem(label="Ατμός", value="Όχι"),
                    SpecItem(label="Ισχύς", value="46 W"),
                    SpecItem(label="Μέγιστη Θερμοκρασία", value="200 °C"),
                ],
            ),
            SpecSection(
                section="Λεπτομέρειες",
                items=[
                    SpecItem(label="Ionic", value="Όχι"),
                    SpecItem(label="Επίστρωση Τιτανίου", value="Όχι"),
                    SpecItem(label="Χρώμα", value="Μαύρο"),
                ],
            ),
        ],
        presentation_source_text=(
            "Πλάκες με επίστρωση κράματος ορείχαλκου και τιτανίου χαλκού. "
            "Εξαιρετικά γρήγορη θέρμανση μέχρι τους 200οC σε μόλις 10 δευτερόλεπτα. "
            "Μήκος πλάκας: 102 mm. Πλάτος πλάκας: 32 mm. "
            "Αυτόματη απενεργοποίηση μετά από 60 min. "
            "Περιστρεφόμενο καλώδιο μήκους 2m. Βάρος: 270gr."
        ),
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Προσωπική Φροντίδα",
        sub_category="Βούρτσες-Ψαλίδια-ισιωτικά",
    )

    html, diagnostics, warnings = build_characteristics_for_product(
        source,
        taxonomy,
        schema_match=SchemaMatchResult(
            matched_schema_id=_schema_id_for_source_file("isiotika_mallion.json"),
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
    assert (
        values[normalize_for_match("Τεχνολογία Πλάκας")]
        == "Επίστρωση κράματος ορείχαλκου και τιτανίου χαλκού"
    )
    assert values[normalize_for_match("Αυτόματη Απενεργοποίηση")] == "60 min"
    assert values[normalize_for_match("Γρήγορη Προθέρμαση")] == "10 δευτερόλεπτα"
    assert values[normalize_for_match("Διάσταση Πλάκας σε Εκατοστά")] == "10.2 × 3.2"
    assert values[normalize_for_match("Βάρος Συσκευής σε Κιλά")] == "0.27"
    assert values[normalize_for_match("Μήκος Καλωδίου σε Μέτρα")] == "2"
    assert values[normalize_for_match("Περιστρεφόμενο Καλώδιο")] == "Ναι"
    assert "characteristics_template_unresolved_fields:7" in warnings
