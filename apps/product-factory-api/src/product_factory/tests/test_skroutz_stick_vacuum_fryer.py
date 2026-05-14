from product_factory.parser_product_skroutz import SkroutzProductParser
from product_factory.taxonomy import TaxonomyResolver


def test_stick_vacuum_category_resolves_to_vacuuming_taxonomy() -> None:
    html = (
        "<!DOCTYPE html>"
        '<html lang="el">'
        "<head>"
        '<meta charset="utf-8" />'
        "<title>Rohnson Mamba Gold M29 Επαναφορτιζόμενη Σκούπα 2 σε 1 Stick Χειρός 25.2V Μωβ</title>"
        '<link rel="canonical" href="https://www.skroutz.gr/s/64811526/rohnson-mamba-gold-m29-epanafortizomeni-skoupa-2-se-1-stick-cheiros-25-2v-mov.html" />'
        '<script id="product-schema" type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Rohnson Mamba Gold M29 Επαναφορτιζόμενη Σκούπα 2 σε 1 Stick Χειρός 25.2V Μωβ","brand":{"@type":"Brand","name":"Rohnson"},"mpn":"M29","sku":"344354","category":"Σκούπες Stick","image":["https://static.skroutz.gr/mock/344354/1.jpg"],"offers":{"@type":"Offer","price":"129.00","priceCurrency":"EUR"}}'
        "</script>"
        "</head>"
        "<body>"
        '<div class="sku-title">'
        '<a class="category-tag" href="https://www.skroutz.gr/c/1234/Skoupes-Stick.html">Σκούπες Stick</a>'
        '<h1 class="page-title">Rohnson Mamba Gold M29 Επαναφορτιζόμενη Σκούπα 2 σε 1 Stick Χειρός 25.2V Μωβ<small class="sku-code">Κωδικός: 344354</small></h1>'
        "</div>"
        '<a class="brand-page-link"><span>Rohnson</span></a>'
        '<div class="summary"><div class="description long"><div class="body-text">Σκούπα stick 2 σε 1.</div></div></div>'
        '<div id="specs"><div class="spec-groups"><div class="spec-details"><h3>Χαρακτηριστικά</h3>'
        "<dl><dt>Τάση</dt><dd>25.2 V</dd></dl>"
        "<dl><dt>Αυτονομία</dt><dd>45 min</dd></dl>"
        "</div></div></div>"
        "</body>"
        "</html>"
    )

    parser = SkroutzProductParser()
    parsed = parser.parse(
        html,
        "https://www.skroutz.gr/s/64811526/rohnson-mamba-gold-m29-epanafortizomeni-skoupa-2-se-1-stick-cheiros-25-2v-mov.html",
    )
    taxonomy, _ = TaxonomyResolver().resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.page_type == "product"
    assert parsed.source.skroutz_family == "stick_vacuum"
    assert taxonomy.parent_category == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert taxonomy.leaf_category == "Σκούπισμα"
    assert taxonomy.sub_category == "Σκούπες Stick"


def test_fryer_category_resolves_to_small_cooks_taxonomy() -> None:
    html = (
        "<!DOCTYPE html>"
        '<html lang="el">'
        "<head>"
        '<meta charset="utf-8" />'
        "<title>Taurus Fry 3 Φριτέζα 3lt Ασημί</title>"
        '<link rel="canonical" href="https://www.skroutz.gr/s/21378597/Taurus-Fry-3-Friteza-3lt-Asimi.html" />'
        '<script id="product-schema" type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Taurus Fry 3 Φριτέζα 3lt Ασημί","brand":{"@type":"Brand","name":"Taurus"},"mpn":"Fry 3","sku":"340289","category":"Φριτέζες","image":["https://static.skroutz.gr/mock/340289/1.jpg"],"offers":{"@type":"Offer","price":"49.00","priceCurrency":"EUR"}}'
        "</script>"
        "</head>"
        "<body>"
        '<div class="sku-title">'
        '<a class="category-tag" href="https://www.skroutz.gr/c/456/Fritezes.html">Φριτέζες</a>'
        '<h1 class="page-title">Taurus Fry 3 Φριτέζα 3lt Ασημί<small class="sku-code">Κωδικός: 340289</small></h1>'
        "</div>"
        '<a class="brand-page-link"><span>Taurus</span></a>'
        '<div class="summary"><div class="description long"><div class="body-text">Φριτέζα 3 λίτρων.</div></div></div>'
        '<div id="specs"><div class="spec-groups"><div class="spec-details"><h3>Χαρακτηριστικά</h3>'
        "<dl><dt>Χωρητικότητα</dt><dd>3 lt</dd></dl>"
        "<dl><dt>Ισχύς</dt><dd>2000 W</dd></dl>"
        "</div></div></div>"
        "</body>"
        "</html>"
    )

    parser = SkroutzProductParser()
    parsed = parser.parse(
        html,
        "https://www.skroutz.gr/s/21378597/Taurus-Fry-3-Friteza-3lt-Asimi.html",
    )
    taxonomy, _ = TaxonomyResolver().resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.page_type == "product"
    assert parsed.source.skroutz_family == "fryer"
    assert taxonomy.parent_category == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert taxonomy.leaf_category == "Μικροί Μάγειρες"
    assert taxonomy.sub_category == "Φριτέζες"
