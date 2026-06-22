from product_factory.characteristics_pipeline import _aliases_for_template_field
from product_factory.category_filters import _candidate_source_labels


def test_cooker_schema_labels_include_equivalent_skroutz_aliases() -> None:
    expected = {
        "Τύπος Συσκευής": "Είδος",
        "Τύπος Εστίας": "Τύπος Εστιών",
        "Χωρητικότητα Φούρνου σε Λίτρα": "Χωρητικότητα Φούρνου",
        "Αριθμός Λειτουργιών Ψησίματος": "Τρόποι Ψησίματος",
        "Τρόποι Λειτουργίας Ψησίματος": "Τύποι Ψησίματος",
        "Οθόνη Ψηφιακών Ενδείξεων": "Ψηφιακή Οθόνη",
        "Χειρισμός": "Διακόπτες",
        "Καθαρισμός Φούρνου": "Σύστημα Καθαρισμού",
        "Εξοπλισμός": "Αξεσουάρ",
        "Κλείδωμα Ασφαλείας για Παιδιά": "Κλείδωμα",
        "Πλάτος Συσκευής σε Εκατοστά": "Πλάτος",
    }

    for label, alias in expected.items():
        aliases = _aliases_for_template_field(
            {"label": label, "aliases": [label], "section_title": ""},
            "Κουζίνες",
        )
        assert alias in aliases


def test_cooker_plate_material_filter_uses_skroutz_hob_type_alias() -> None:
    aliases = _candidate_source_labels(
        "Υλικό πλάκας",
        taxonomy_path="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Κουζίνες > Κουζίνες Κεραμικές",
    )

    assert "Τύπος Εστιών" in aliases
