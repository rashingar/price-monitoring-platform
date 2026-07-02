from product_factory.normalize import (
    candidate_label_keys,
    clean_breadcrumbs,
    label_alias_family_id,
    labels_equivalent,
    load_label_alias_registry,
    normalize_greek_label,
    normalize_label_key,
    normalize_whitespace,
    nullify_dash_values,
    repair_mojibake_text,
    strip_greek_accents,
    strip_nbsp,
)
from product_factory.utils import build_additional_image_value


def test_nbsp_and_whitespace_normalization() -> None:
    assert strip_nbsp("798,00\xa0€") == "798,00 €"
    assert (
        normalize_whitespace("  Σκούπα\u00a0\u00a0Stick   Rowenta ")
        == "Σκούπα Stick Rowenta"
    )


def test_dash_null_handling() -> None:
    assert nullify_dash_values("-") is None
    assert nullify_dash_values("  — ") is None
    assert nullify_dash_values("WiFi") == "WiFi"


def test_clean_breadcrumbs_and_additional_images() -> None:
    assert clean_breadcrumbs(
        ["Αρχική", "Οικιακές Συσκευές", "Οικιακές Συσκευές", "Πλυντήρια"]
    ) == [
        "Αρχική",
        "Οικιακές Συσκευές",
        "Πλυντήρια",
    ]
    assert build_additional_image_value("330825", 1) == ""
    assert build_additional_image_value("330825", 3) == (
        "catalog/01_main/330825/330825-2.jpg:::catalog/01_main/330825/330825-3.jpg"
    )


def test_valid_greek_display_text_remains_stable() -> None:
    assert normalize_greek_label("  Μέγιστη Ισχύς (Watt) ") == "Μέγιστη Ισχύς (Watt)"
    assert repair_mojibake_text("Διαστάσεις Συσκευής") == "Διαστάσεις Συσκευής"


def test_greek_label_keys_are_accent_insensitive() -> None:
    assert strip_greek_accents("Μέγιστη Ισχύς") == "Μεγιστη Ισχυς"
    assert normalize_label_key("Ισχύς") == normalize_label_key("Ισχυς")
    assert normalize_label_key("Μέγιστη Ισχύς") == normalize_label_key("Μεγιστη Ισχυς")


def test_mojibake_repair_handles_known_power_examples() -> None:
    assert repair_mojibake_text("Ξ™ΟƒΟ‡ΟΟ‚") == "Ισχύς"
    assert repair_mojibake_text("Ξ™ΟƒΟ‡ΟΟ‚ ΟƒΞµ Watt") == "Ισχύς σε Watt"
    assert (
        repair_mojibake_text("ΞΞ­Ξ³ΞΉΟƒΟ„Ξ· Ξ™ΟƒΟ‡ΟΟ‚ (Watt)")
        == "Μέγιστη Ισχύς (Watt)"
    )


def test_mojibake_repair_keeps_ascii_numeric_and_empty_values_stable() -> None:
    assert repair_mojibake_text("550 W") == "550 W"
    assert normalize_label_key(550) == "550"
    assert normalize_label_key(None) == ""
    assert normalize_label_key("") == ""


def test_label_alias_registry_loads_power_watt_family() -> None:
    registry = load_label_alias_registry()
    families = {family["family_id"]: family for family in registry["families"]}
    assert "power_watt" in families
    assert families["power_watt"]["canonical_label"] == "Ισχύς"


def test_power_watt_alias_family_covers_valid_accentless_and_mojibake_labels() -> None:
    labels = [
        "Ισχύς",
        "Ισχυς",
        "Ισχύς σε Watt",
        "Ισχυς σε Watt",
        "Ισχύς σε Watts",
        "Ισχυς σε Watts",
        "Μέγιστη Ισχύς (Watt)",
        "Μεγιστη Ισχυς (Watt)",
        "Ξ™ΟƒΟ‡ΟΟ‚",
        "Ξ™ΟƒΟ‡ΟΟ‚ ΟƒΞµ Watts",
        "ΞΞ­Ξ³ΞΉΟƒΟ„Ξ· Ξ™ΟƒΟ‡ΟΟ‚ (Watt)",
    ]
    assert {label_alias_family_id(label) for label in labels} == {"power_watt"}
    assert all("alias:power_watt" in candidate_label_keys(label) for label in labels)


def test_power_watt_aliases_are_equivalent_without_overmatching() -> None:
    assert labels_equivalent("Ισχύς", "Ισχυς σε Watts")
    assert labels_equivalent("Μέγιστη Ισχύς (Watt)", "Μεγιστη Ισχυς σε Watt")
    assert labels_equivalent("Συνολική Ισχύς Ηχείων(Watt)", "Συνολική Ισχύς Ηχείων")
    assert not labels_equivalent("Ισχύς", "Διαστάσεις")
    assert not labels_equivalent("Ισχύς σε Watt", "Βάρος")
    assert not labels_equivalent("Ισχύς", "Ισχύς Ψύξης")


def test_common_skroutz_description_aliases_map_to_alias_families() -> None:
    assert label_alias_family_id("Διαστάσεις") == "dimensions"
    assert label_alias_family_id("Βάρος") == "weight_kg"
    assert label_alias_family_id("Χρώμα") == "color"


def test_washing_machine_aliases_cover_source_specific_spin_labels() -> None:
    assert label_alias_family_id("Ταχύτητα στυψίματος") == "spin_speed"
    assert labels_equivalent("Μέγιστες Στροφές Στυψίματος", "Ταχύτητα στυψίματος")


def test_fan_blade_count_alias_family_covers_skroutz_wording() -> None:
    assert label_alias_family_id("Αριθμός Πτερυγίων") == "fan_blade_count"
    assert label_alias_family_id("Αριθμός Φτερωτών") == "fan_blade_count"
    assert labels_equivalent("Αριθμός Πτερυγίων", "Αριθμός Φτερωτών")
    assert "alias:fan_blade_count" in candidate_label_keys("Αριθμός Φτερωτών")


def test_unknown_labels_do_not_map_to_alias_family() -> None:
    assert label_alias_family_id("Διακόπτες") == ""
    assert label_alias_family_id("Υλικό Κατασκευής") == ""
    assert label_alias_family_id("Ισχύς Θορύβου") == ""


def test_valid_unrelated_greek_is_not_repaired_into_power_label() -> None:
    label = "Ικανότητα Ψύξης"
    assert repair_mojibake_text(label) == label
    assert label_alias_family_id(label) == ""


def test_punctuation_and_parenthetical_variants_normalize_consistently() -> None:
    assert normalize_label_key("Μέγιστη Ισχύς (Watt)") == normalize_label_key(
        "Μέγιστη Ισχύς Watt"
    )
    assert labels_equivalent(
        "Διαστάσεις Συσκευής σε Εκατοστά (Υ χ Π χ Β)",
        "Διαστάσεις Συσκευής σε Εκατοστά (Υ × Π × Β)",
    )
