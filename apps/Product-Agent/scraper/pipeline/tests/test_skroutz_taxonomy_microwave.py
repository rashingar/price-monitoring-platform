import json

from pipeline.parser_product_skroutz import SkroutzProductParser
from pipeline.taxonomy import TaxonomyResolver


def _build_minimal_taxonomy_html(row: dict[str, str]) -> str:
    title = row["name"]
    category_text = row["category_tag_text"]
    category_href = row["category_tag_href"]
    manufacturer = row["manufacturer"]
    url = row["skroutz_product_url"]
    model = row["model"]
    return (
        "<!DOCTYPE html>"
        "<html lang=\"el\">"
        "<head>"
        "<meta charset=\"utf-8\" />"
        f"<title>{title}</title>"
        f"<link rel=\"canonical\" href=\"{url}\" />"
        "<script id=\"product-schema\" type=\"application/ld+json\">"
        f"{json.dumps({'@context': 'https://schema.org', '@type': 'Product', 'name': title, 'brand': {'@type': 'Brand', 'name': manufacturer}, 'mpn': model, 'sku': model, 'category': category_text, 'image': [f'https://static.skroutz.gr/mock/{model}/1.jpg'], 'offers': {'@type': 'Offer', 'price': '199.00', 'priceCurrency': 'EUR'}}, ensure_ascii=False)}"
        "</script>"
        "</head>"
        "<body>"
        "<div class=\"sku-title\">"
        f"<a class=\"category-tag\" href=\"{category_href}\">{category_text}</a>"
        f"<h1 class=\"page-title\">{title}<small class=\"sku-code\">Κωδικός: {model}</small></h1>"
        "</div>"
        f"<a class=\"brand-page-link\"><span>{manufacturer}</span></a>"
        f"<div id=\"prices\"><div class=\"product-name\" title=\"{title}\"></div></div>"
        "</body>"
        "</html>"
    )


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

    parsed = parser.parse(_build_minimal_taxonomy_html(row), row["skroutz_product_url"])
    taxonomy, _ = resolver.resolve(parsed.source.breadcrumbs, parsed.source.canonical_url, parsed.source.name, parsed.source.key_specs, parsed.source.spec_sections)

    assert parsed.source.page_type == "product"
    assert parsed.source.skroutz_family == "microwave"
    assert taxonomy.parent_category == "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ"
    assert taxonomy.leaf_category == "Φούρνοι Μικροκυμάτων"
    assert taxonomy.sub_category == "Με Grill"
