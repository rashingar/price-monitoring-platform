from pipeline.deterministic_fields import build_deterministic_product_fields
from pipeline.mapping import derive_seo_keyword
from pipeline.models import SourceProductData, SpecItem, SpecSection, TaxonomyResolution


def _make_ice_cream_taxonomy() -> TaxonomyResolution:
    return TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Μικροί Μάγειρες",
        sub_category="Παγωτομηχανές",
        gender="fem",
    )


def test_skroutz_ice_cream_maker_uses_singular_category_phrase() -> None:
    source = SourceProductData(
        source_name="skroutz",
        brand="Tefal",
        mpn="IG602A",
        name="Tefal Dolci Παγωτομηχανή 3x1.4lt Καφέ",
        key_specs=[
            SpecItem(label="Χωρητικότητα", value="1.4 lt"),
            SpecItem(label="Αριθμός Προγραμμάτων", value="10"),
            SpecItem(label="Αριθμός Δοχείων", value="3"),
            SpecItem(label="Χρώμα", value="Καφέ"),
        ],
    )

    fields = build_deterministic_product_fields(source, _make_ice_cream_taxonomy(), "344709", derive_seo_keyword)

    assert fields["category_phrase"] == "Παγωτομηχανή"
    assert fields["name"] == "Tefal IG602A – Παγωτομηχανή 1,4Lt 10 Προγραμμάτων 3 Δοχείων"
    assert fields["meta_title"] == "Tefal IG602A Παγωτομηχανή 1,4Lt 10 Προγραμμάτων | eTranoulis"
    assert fields["seo_keyword"] == "tefal-ig602a-pagotomichani-14lt-10-programmaton-3-docheion-kafe"


def test_manufacturer_tefal_ice_cream_maker_uses_family_deterministic_fields() -> None:
    source = SourceProductData(
        source_name="manufacturer_tefal",
        brand="Tefal",
        mpn="IG602A",
        name="Tefal Dolci Παγωτομηχανή IG602A",
        key_specs=[
            SpecItem(label="Χωρητικότητα", value="1.4 lt"),
            SpecItem(label="Αριθμός Προγραμμάτων", value="10"),
            SpecItem(label="Αριθμός Δοχείων", value="3"),
            SpecItem(label="Χρώμα", value="Καφέ"),
        ],
        spec_sections=[
            SpecSection(
                section="Παραγωγή & Δυνατότητες",
                items=[
                    SpecItem(label="Χωρητικότητα", value="1.4 lt"),
                    SpecItem(label="Αριθμός Προγραμμάτων", value="10"),
                    SpecItem(label="Αριθμός Δοχείων", value="3"),
                ],
            )
        ],
        manufacturer_spec_sections=[
            SpecSection(
                section="Χαρακτηριστικά Κατασκευαστή",
                items=[SpecItem(label="Τάση", value="220-240 V")],
            )
        ],
    )

    fields = build_deterministic_product_fields(source, _make_ice_cream_taxonomy(), "344709", derive_seo_keyword)

    assert fields["category_phrase"] == "Παγωτομηχανή"
    assert fields["name"] == "Tefal IG602A – Παγωτομηχανή 1,4Lt 10 Προγραμμάτων 3 Δοχείων"
    assert fields["meta_title"] == "Tefal IG602A Παγωτομηχανή 1,4Lt 10 Προγραμμάτων | eTranoulis"

