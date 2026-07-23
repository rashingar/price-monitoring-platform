import csv
import json
from pathlib import Path

import pytest

from product_factory.parser_product_skroutz import SkroutzProductParser
from product_factory.skroutz_taxonomy import classify_skroutz_taxonomy
from product_factory.taxonomy import TaxonomyResolver


@pytest.fixture(autouse=True)
def disable_eprel_energy_label_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "product_factory.parser_product_skroutz.resolve_eprel_energy_label_asset_url",
        lambda **_kwargs: "",
    )


def read_taxonomy_rows(regression_fixture: Path) -> list[dict[str, str]]:
    with regression_fixture.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_minimal_taxonomy_html(row: dict[str, str]) -> str:
    title = row["name"]
    category_text = row["category_tag_text"]
    category_href = row["category_tag_href"]
    manufacturer = row["manufacturer"]
    url = row["skroutz_product_url"]
    model = row["model"]
    return (
        "<!DOCTYPE html>"
        '<html lang="el">'
        "<head>"
        '<meta charset="utf-8" />'
        f"<title>{title}</title>"
        f'<link rel="canonical" href="{url}" />'
        '<script id="product-schema" type="application/ld+json">'
        f"{json.dumps({'@context': 'https://schema.org', '@type': 'Product', 'name': title, 'brand': {'@type': 'Brand', 'name': manufacturer}, 'mpn': model, 'sku': model, 'category': category_text, 'image': [f'https://static.skroutz.gr/mock/{model}/1.jpg', f'https://static.skroutz.gr/mock/{model}/2.jpg'], 'offers': {'@type': 'Offer', 'price': '199.00', 'priceCurrency': 'EUR'}}, ensure_ascii=False)}"
        "</script>"
        "</head>"
        "<body>"
        '<div class="sku-title">'
        f'<a class="category-tag" href="{category_href}">{category_text}</a>'
        f'<h1 class="page-title">{title}<small class="sku-code">Κωδικός: {model}</small></h1>'
        "</div>"
        f'<a class="brand-page-link"><span>{manufacturer}</span></a>'
        f'<div class="summary"><div class="description long"><div class="body-text">{title}</div></div></div>'
        f'<div id="prices"><div class="product-name" title="{title}"></div></div>'
        '<div class="prices"><div class="final-price"><span class="integer-part">199</span><span class="decimal-part">00</span></div></div>'
        '<div id="specs"><div class="spec-groups">'
        '<div class="spec-details"><h3>Χαρακτηριστικά</h3>'
        f"<dl><dt>Κατασκευαστής</dt><dd>{manufacturer or 'Άγνωστο'}</dd></dl>"
        f"<dl><dt>Μοντέλο</dt><dd>{model}</dd></dl>"
        "</div>"
        "</div></div>"
        "</body>"
        "</html>"
    )


def test_taxonomy_regression_fixture_resolves_expected_categories(
    skroutz_fixtures_root: Path,
) -> None:
    parser = SkroutzProductParser()
    resolver = TaxonomyResolver()
    rows = read_taxonomy_rows(
        skroutz_fixtures_root / "taxonomy_cases" / "skroutz_taxonomy_regression.csv"
    )
    skipped = [
        (row["model"], row["skip_reason"]) for row in rows if row.get("skip_reason")
    ]

    assert skipped == [
        ("231412", "mapping_conflict_live_page_45cm_freestanding_not_tabletop")
    ]
    assert len(rows) == 164
    assert all(
        row["expected_sub_category"] != "4K UHD"
        for row in rows
        if row["expected_leaf_category"] == "Τηλεοράσεις"
    )

    for row in rows:
        if row.get("skip_reason"):
            continue
        parsed = parser.parse(
            build_minimal_taxonomy_html(row), row["skroutz_product_url"]
        )
        taxonomy, _ = resolver.resolve(
            parsed.source.breadcrumbs,
            parsed.source.canonical_url,
            parsed.source.name,
            parsed.source.key_specs,
            parsed.source.spec_sections,
        )

        assert parsed.source.page_type == "product"
        assert parsed.source.skroutz_family == row["family_key"]
        assert parsed.source.category_tag_text == row["category_tag_text"]
        assert parsed.source.category_tag_href == row["category_tag_href"]
        assert taxonomy.parent_category == row["expected_parent_category"]
        assert taxonomy.leaf_category == row["expected_leaf_category"]
        assert (taxonomy.sub_category or "") == row["expected_sub_category"]
        assert parsed.source.taxonomy_source_category == row["expected_source_category"]
        assert parsed.source.taxonomy_match_type == row["expected_match_type"]


def test_taxonomy_classifies_inventor_vi32_model_urls_as_wall_air_conditioners() -> None:
    hint = classify_skroutz_taxonomy(
        category_tag_text="",
        category_tag_href="",
        title="Inventor Life Pro WiFi L4VI32-12WiFiR / L4VO32-12 - Skroutz.gr",
        url="https://www.skroutz.gr/s/12818615/Inventor-Life-Pro-WiFi-L4VI32-12WiFiR-L4VO32-12.html",
        brand="Inventor",
    )

    assert hint is not None
    assert not hint.ambiguous
    assert hint.matched_rule_id == "air_conditioner:wall"


def test_tve_fan_model_is_not_misclassified_as_a_television() -> None:
    parser = SkroutzProductParser()
    resolver = TaxonomyResolver()
    row = {
        "name": "Trotec TVE 25 S Ανεμιστήρας Ορθοστάτης 40W",
        "category_tag_text": "Ανεμιστήρες",
        "category_tag_href": "https://www.skroutz.gr/c/427/anemisthres.html",
        "manufacturer": "Trotec",
        "skroutz_product_url": "https://www.skroutz.gr/s/19355213/Trotec-TVE-25-S-Anemistiras-Orthostatis-40W.html",
        "model": "TVE 25 S",
    }

    parsed = parser.parse(build_minimal_taxonomy_html(row), row["skroutz_product_url"])
    taxonomy, _ = resolver.resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.skroutz_family == "stand_fan"
    assert parsed.source.taxonomy_rule_id != "television:size_bucket"
    assert taxonomy.parent_category == "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ"
    assert taxonomy.leaf_category == "Ανεμιστήρες"
    assert taxonomy.sub_category == "Ορθοστάτης"


def test_generic_taxonomy_helper_does_not_treat_tve_as_tv() -> None:
    hint = classify_skroutz_taxonomy(
        category_tag_text="Ανεμιστήρες",
        category_tag_href="https://www.skroutz.gr/c/427/anemisthres.html",
        title="Trotec TVE 25 S Ανεμιστήρας",
        url="https://www.skroutz.gr/s/19355213/Trotec-TVE-25-S-Anemistiras.html",
        brand="Trotec",
    )

    assert hint is None


def test_representative_taxonomy_html_fixtures_cover_supported_skroutz_combos(
    skroutz_fixtures_root: Path,
) -> None:
    parser = SkroutzProductParser()
    resolver = TaxonomyResolver()
    taxonomy_cases_root = skroutz_fixtures_root / "taxonomy_cases"
    index = json.loads((taxonomy_cases_root / "index.json").read_text(encoding="utf-8"))

    assert len(index) == 29
    assert any(item["captured_live"] for item in index)
    assert any(not item["captured_live"] for item in index)

    for entry in index:
        meta = json.loads(
            (taxonomy_cases_root / entry["meta"]).read_text(encoding="utf-8")
        )
        html = (taxonomy_cases_root / entry["html"]).read_text(encoding="utf-8")
        parsed = parser.parse(html, meta["source_url"])
        taxonomy, _ = resolver.resolve(
            parsed.source.breadcrumbs,
            parsed.source.canonical_url,
            parsed.source.name,
            parsed.source.key_specs,
            parsed.source.spec_sections,
        )

        assert parsed.source.page_type == "product"
        assert parsed.source.skroutz_family == meta["family_key"]
        assert parsed.source.category_tag_text == meta["category_tag_text"]
        assert parsed.source.category_tag_href == meta["category_tag_href"]
        assert parsed.source.category_tag_slug == meta["normalized_category_slug"]
        assert parsed.source.presentation_source_text
        assert parsed.source.gallery_images
        assert parsed.source.spec_sections
        assert taxonomy.parent_category == meta["expected_parent_category"]
        assert taxonomy.leaf_category == meta["expected_leaf_category"]
        assert (taxonomy.sub_category or "") == meta["expected_sub_category"]
        assert (
            parsed.source.taxonomy_source_category == meta["expected_source_category"]
        )
        assert parsed.source.taxonomy_match_type == meta["expected_match_type"]


def test_kitchen_hobs_category_resolves_to_built_in_hobs() -> None:
    parser = SkroutzProductParser()
    resolver = TaxonomyResolver()
    row = {
        "name": "Neff T16BT60N0 Κεραμική Εστία 60cm 4 Ζωνών TwistPad",
        "category_tag_text": "Εστίες Κουζίνας",
        "category_tag_href": "https://www.skroutz.gr/c/429/esties-kouzinas.html",
        "manufacturer": "Neff",
        "skroutz_product_url": "https://www.skroutz.gr/s/7927541/Neff-N-70-Keramiki-Estia-me-Plaisio-Aytonomi-me-Leitourgia-Kleidomatos-58-3x51-3ek-T16BT60N0.html",
        "model": "T16BT60N0",
    }

    parsed = parser.parse(build_minimal_taxonomy_html(row), row["skroutz_product_url"])
    taxonomy, _ = resolver.resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.skroutz_family == "built_in_appliance"
    assert taxonomy.parent_category == "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ"
    assert taxonomy.leaf_category == "Εντοιχιζόμενες Συσκευές"
    assert taxonomy.sub_category == "Εστίες"


def test_explicit_tabletop_hob_category_still_resolves_to_small_appliance_hobs() -> (
    None
):
    parser = SkroutzProductParser()
    resolver = TaxonomyResolver()
    row = {
        "name": "Fancy 0013 Επιτραπέζια Εστία Εμαγιέ Διπλή Λευκή",
        "category_tag_text": "Επιτραπέζιες Εστίες",
        "category_tag_href": "https://www.skroutz.gr/c/1699/epitrapezies_esties.html",
        "manufacturer": "Fancy",
        "skroutz_product_url": "https://www.skroutz.gr/s/21656760/Fancy-0013-Epitrapezia-Estia-Emagie-Dipli-Leyki-0013.html",
        "model": "0013",
    }

    parsed = parser.parse(build_minimal_taxonomy_html(row), row["skroutz_product_url"])
    taxonomy, _ = resolver.resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.skroutz_family == "tabletop_hob"
    assert taxonomy.parent_category == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert taxonomy.leaf_category == "Μικροί Μάγειρες"
    assert taxonomy.sub_category == "Εστίες"


def test_smartphone_category_resolves_to_android_taxonomy() -> None:
    parser = SkroutzProductParser()
    resolver = TaxonomyResolver()
    row = {
        "name": "Xiaomi Poco M8 5G Dual Sim 8/256GB Πράσινο",
        "category_tag_text": "Κινητά Τηλέφωνα",
        "category_tag_href": "https://www.skroutz.gr/c/40/kinhta-thlefwna.html",
        "manufacturer": "Xiaomi",
        "skroutz_product_url": "https://www.skroutz.gr/s/65005733/xiaomi-poco-m8-5g-dual-sim-8-256gb-prasino.html",
        "model": "M8",
    }

    parsed = parser.parse(build_minimal_taxonomy_html(row), row["skroutz_product_url"])
    taxonomy, _ = resolver.resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.page_type == "product"
    assert parsed.source.skroutz_family == "smartphone"
    assert taxonomy.parent_category == "ΤΗΛΕΦΩΝΙΑ"
    assert taxonomy.leaf_category == "Smartphones"
    assert taxonomy.sub_category == "Android"
    assert (
        parsed.source.taxonomy_source_category
        == "ΤΗΛΕΦΩΝΙΑ:::ΤΗΛΕΦΩΝΙΑ///Smartphones:::ΤΗΛΕΦΩΝΙΑ///Smartphones///Android"
    )
    assert parsed.source.taxonomy_match_type == "exact_category"
    assert parsed.source.taxonomy_rule_id == "smartphone:android"


def test_smartphone_category_resolves_to_ios_taxonomy_for_iphone() -> None:
    parser = SkroutzProductParser()
    resolver = TaxonomyResolver()
    row = {
        "name": "Apple iPhone 17 Pro Max 512GB Deep Blue",
        "category_tag_text": "Smartphones",
        "category_tag_href": "https://www.skroutz.gr/c/40/smartphones.html",
        "manufacturer": "Apple",
        "skroutz_product_url": "https://www.skroutz.gr/s/70000000/apple-iphone-17-pro-max-512gb-deep-blue.html",
        "model": "AIPHONE17PM",
    }

    parsed = parser.parse(build_minimal_taxonomy_html(row), row["skroutz_product_url"])
    taxonomy, _ = resolver.resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.page_type == "product"
    assert parsed.source.skroutz_family == "smartphone"
    assert taxonomy.parent_category == "ΤΗΛΕΦΩΝΙΑ"
    assert taxonomy.leaf_category == "Smartphones"
    assert taxonomy.sub_category == "iOS"
    assert (
        parsed.source.taxonomy_source_category
        == "ΤΗΛΕΦΩΝΙΑ:::ΤΗΛΕΦΩΝΙΑ///Smartphones:::ΤΗΛΕΦΩΝΙΑ///Smartphones///iOS"
    )
    assert parsed.source.taxonomy_match_type == "exact_category"
    assert parsed.source.taxonomy_rule_id == "smartphone:ios"


def test_ice_cream_maker_category_resolves_to_small_appliance_taxonomy() -> None:
    parser = SkroutzProductParser()
    resolver = TaxonomyResolver()
    row = {
        "name": "Tefal Dolci Παγωτομηχανή 3x1.4lt Καφέ IG602A",
        "category_tag_text": "Παγωτομηχανές",
        "category_tag_href": "https://www.skroutz.gr/c/3014/pagotomichanes.html",
        "manufacturer": "Tefal",
        "skroutz_product_url": "https://www.skroutz.gr/s/66043021/tefal-dolci-pagotomichani-3x1-4lt-kafe.html",
        "model": "IG602A",
    }

    parsed = parser.parse(build_minimal_taxonomy_html(row), row["skroutz_product_url"])
    taxonomy, _ = resolver.resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.page_type == "product"
    assert parsed.source.skroutz_family == "ice_cream_maker"
    assert taxonomy.parent_category == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert taxonomy.leaf_category == "Μικροί Μάγειρες"
    assert taxonomy.sub_category == "Παγωτομηχανές"


def test_tower_fan_category_resolves_to_supported_fan_taxonomy() -> None:
    parser = SkroutzProductParser()
    resolver = TaxonomyResolver()
    row = {
        "name": "Rohnson R-8112 Ανεμιστήρας Πύργος 60W με Τηλεχειριστήριο Λευκός",
        "category_tag_text": "Ανεμιστήρες",
        "category_tag_href": "https://www.skroutz.gr/c/453/anemistires.html",
        "manufacturer": "Rohnson",
        "skroutz_product_url": "https://www.skroutz.gr/s/66937454/rohnson-r-8112-anemistiras-pyrgos-60w-me-tilecheiristirio-leykos.html",
        "model": "R-8112",
    }

    parsed = parser.parse(build_minimal_taxonomy_html(row), row["skroutz_product_url"])
    taxonomy, _ = resolver.resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.page_type == "product"
    assert parsed.source.skroutz_family == "tower_fan"
    assert taxonomy.parent_category == "ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ"
    assert taxonomy.leaf_category == "Ανεμιστήρες"
    assert taxonomy.sub_category is None


def test_microwave_category_resolves_to_microwave_leaf_taxonomy() -> None:
    parser = SkroutzProductParser()
    resolver = TaxonomyResolver()
    row = {
        "name": "Panasonic NN-K36NBMEPG Φούρνος Μικροκυμάτων με Grill 24lt Μαύρος",
        "category_tag_text": "Φούρνοι Μικροκυμάτων",
        "category_tag_href": "https://www.skroutz.gr/c/409/fournoi-mikrokymatwn.html",
        "manufacturer": "Panasonic",
        "skroutz_product_url": "https://www.skroutz.gr/s/45222101/Panasonic-NN-K36NBMEPG-Fournos-Mikrokymaton-me-Grill-24lt-Mayros.html",
        "model": "NN-K36NBMEPG",
    }

    parsed = parser.parse(build_minimal_taxonomy_html(row), row["skroutz_product_url"])
    taxonomy, _ = resolver.resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.page_type == "product"
    assert parsed.source.skroutz_family == "microwave"
    assert taxonomy.parent_category == "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ"
    assert taxonomy.leaf_category == "Φούρνοι Μικροκυμάτων"
    assert taxonomy.sub_category == "Με Grill"


def test_hair_straightener_category_resolves_to_personal_care_taxonomy() -> None:
    parser = SkroutzProductParser()
    resolver = TaxonomyResolver()
    row = {
        "name": "GA.MA GI3034 Πρέσα Μαλλιών με Κεραμικές Πλάκες 45W",
        "category_tag_text": "Πρέσες Μαλλιών",
        "category_tag_href": "https://www.skroutz.gr/c/1512/Preses-Mallion.html",
        "manufacturer": "GA.MA",
        "skroutz_product_url": "https://www.skroutz.gr/s/58285703/GA-MA-GI3034-Presa-Mallion-me-Keramikes-Plakes-45W.html",
        "model": "GI3034",
    }

    parsed = parser.parse(build_minimal_taxonomy_html(row), row["skroutz_product_url"])
    taxonomy, _ = resolver.resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.page_type == "product"
    assert parsed.source.skroutz_family == "hair_straightener"
    assert taxonomy.parent_category == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert taxonomy.leaf_category == "Προσωπική Φροντίδα"
    assert taxonomy.sub_category == "Βούρτσες-Ψαλίδια-ισιωτικά"
