import json

from product_factory.parser_product_skroutz import SkroutzProductParser
from product_factory.taxonomy import TaxonomyResolver


def _minimal_skroutz_product_html(row: dict[str, str]) -> str:
    title = row["name"]
    category_text = row["category_tag_text"]
    category_href = row["category_tag_href"]
    manufacturer = row["manufacturer"]
    url = row["skroutz_product_url"]
    model = row["model"]
    schema = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "brand": {"@type": "Brand", "name": manufacturer},
        "mpn": model,
        "sku": model,
        "category": category_text,
        "image": [f"https://static.skroutz.gr/mock/{model}/1.jpg"],
        "offers": {"@type": "Offer", "price": "59.00", "priceCurrency": "EUR"},
    }
    return (
        '<!DOCTYPE html><html lang="el"><head><meta charset="utf-8" />'
        f'<title>{title}</title><link rel="canonical" href="{url}" />'
        '<script id="product-schema" type="application/ld+json">'
        f"{json.dumps(schema, ensure_ascii=False)}"
        "</script></head><body>"
        '<div class="sku-title">'
        f'<a class="category-tag" href="{category_href}">{category_text}</a>'
        f'<h1 class="page-title">{title}<small class="sku-code">Κωδικός: {model}</small></h1>'
        "</div>"
        f'<a class="brand-page-link"><span>{manufacturer}</span></a>'
        '<div class="summary"><div class="description long"><div class="body-text">'
        "Σιδερώστρα για σύστημα σιδερώματος, σπαστή, γκρι, 124x40x95cm."
        "</div></div></div>"
        '<div id="prices"><div class="product-name"></div></div>'
        '<div class="prices"><div class="final-price"><span class="integer-part">59</span><span class="decimal-part">00</span></div></div>'
        '<div id="specs"><div class="spec-groups">'
        '<div class="spec-details"><h3>Χαρακτηριστικά</h3>'
        "<dl><dt>Τύπος Σιδερώστρας</dt><dd>Για Σύστημα Σιδερώματος</dd></dl>"
        "<dl><dt>Είδος</dt><dd>Σπαστή</dd></dl>"
        "<dl><dt>Μήκος Ανοιχτής</dt><dd>124 cm</dd></dl>"
        "</div></div></div>"
        "</body></html>"
    )


def test_ironing_board_category_resolves_to_ironing_board_taxonomy() -> None:
    row = {
        "name": "Afer Homie Pro Σιδερώστρα για Σύστημα Σιδερώματος Σπαστή Γκρι 124x40x95cm 2062",
        "category_tag_text": "Σιδερώστρες",
        "category_tag_href": "https://www.skroutz.gr/c/2504/Siderostres.html",
        "manufacturer": "Afer",
        "skroutz_product_url": "https://www.skroutz.gr/s/9351031/Afer-Homie-Pro-Siderostra-gia-Systima-Sideromatos-Spasti-Gri-124x40x95cm-2062.html",
        "model": "2062",
    }

    parsed = SkroutzProductParser().parse(
        _minimal_skroutz_product_html(row), row["skroutz_product_url"]
    )
    taxonomy, _ = TaxonomyResolver().resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.page_type == "product"
    assert parsed.source.skroutz_family == "ironing_board"
    assert taxonomy.parent_category == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert taxonomy.leaf_category == "Σιδέρωμα"
    assert taxonomy.sub_category == "Σιδερώστρες"
    assert (
        parsed.source.taxonomy_source_category
        == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ:::ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σιδέρωμα:::ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σιδέρωμα///Σιδερώστρες"
    )
    assert parsed.source.taxonomy_match_type == "exact_category"
