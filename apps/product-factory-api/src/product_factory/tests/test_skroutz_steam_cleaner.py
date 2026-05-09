from product_factory.parser_product_skroutz import SkroutzProductParser
from product_factory.taxonomy import TaxonomyResolver


def test_steam_cleaner_category_resolves_to_vacuuming_taxonomy() -> None:
    html = (
        "<!DOCTYPE html>"
        '<html lang="el">'
        "<head>"
        '<meta charset="utf-8" />'
        "<title>Ariete XVapor Comfort 00P414520AR0 Ατμοκαθαριστής Πίεσης 5bar με Ρόδες</title>"
        '<link rel="canonical" href="https://www.skroutz.gr/s/11189756/Ariete-XVapor-Comfort-00P414520AR0-Atmokatharistis-Piesis-5bar-me-Rodes.html" />'
        '<script id="product-schema" type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Product","name":"Ariete XVapor Comfort 00P414520AR0 Ατμοκαθαριστής Πίεσης 5bar με Ρόδες","brand":{"@type":"Brand","name":"Ariete"},"mpn":"00P414520AR0","sku":"11189756","category":"Ατμοκαθαριστές","image":["https://static.skroutz.gr/mock/344658/1.jpg"],"offers":{"@type":"Offer","price":"129.00","priceCurrency":"EUR"}}'
        "</script>"
        "</head>"
        "<body>"
        '<div class="sku-title">'
        '<a class="category-tag" href="https://www.skroutz.gr/c/1234/Atmokatharistes.html">Ατμοκαθαριστές</a>'
        '<h1 class="page-title">Ariete XVapor Comfort 00P414520AR0 Ατμοκαθαριστής Πίεσης 5bar με Ρόδες<small class="sku-code">Κωδικός: 11189756</small></h1>'
        "</div>"
        '<a class="brand-page-link"><span>Ariete</span></a>'
        '<div class="summary"><div class="description long"><div class="body-text">Ατμοκαθαριστής πίεσης για καθαρισμό με ατμό.</div></div></div>'
        '<div id="prices"><div class="product-name" title="Ariete XVapor Comfort"></div></div>'
        '<div class="prices"><div class="final-price"><span class="integer-part">129</span><span class="decimal-part">00</span></div></div>'
        '<div id="specs"><div class="spec-groups"><div class="spec-details"><h3>Γενικά</h3>'
        "<dl><dt>Ισχύς</dt><dd>1500 W</dd></dl>"
        "<dl><dt>Πίεση Ατμού</dt><dd>5 bar</dd></dl>"
        "<dl><dt>Χωρητικότητα Δοχείου Νερού</dt><dd>1.6 lt</dd></dl>"
        "</div></div></div>"
        "</body>"
        "</html>"
    )

    parser = SkroutzProductParser()
    parsed = parser.parse(
        html,
        "https://www.skroutz.gr/s/11189756/Ariete-XVapor-Comfort-00P414520AR0-Atmokatharistis-Piesis-5bar-me-Rodes.html",
    )
    taxonomy, _ = TaxonomyResolver().resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.page_type == "product"
    assert parsed.source.skroutz_family == "steam_cleaner"
    assert taxonomy.parent_category == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert taxonomy.leaf_category == "Σκούπισμα"
    assert taxonomy.sub_category == "Ατμοκαθαριστές"
