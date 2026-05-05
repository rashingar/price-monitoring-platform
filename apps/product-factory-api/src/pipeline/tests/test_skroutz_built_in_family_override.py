import json

from pipeline.parser_product_skroutz import SkroutzProductParser
from pipeline.taxonomy import TaxonomyResolver


def build_minimal_taxonomy_html(row: dict[str, str]) -> str:
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
        f"{json.dumps({'@context': 'https://schema.org', '@type': 'Product', 'name': title, 'brand': {'@type': 'Brand', 'name': manufacturer}, 'mpn': model, 'sku': model, 'category': category_text, 'image': [f'https://static.skroutz.gr/mock/{model}/1.jpg', f'https://static.skroutz.gr/mock/{model}/2.jpg'], 'offers': {'@type': 'Offer', 'price': '199.00', 'priceCurrency': 'EUR'}}, ensure_ascii=False)}"
        "</script>"
        "</head>"
        "<body>"
        "<div class=\"sku-title\">"
        f"<a class=\"category-tag\" href=\"{category_href}\">{category_text}</a>"
        f"<h1 class=\"page-title\">{title}<small class=\"sku-code\">Κωδικός: {model}</small></h1>"
        "</div>"
        f"<a class=\"brand-page-link\"><span>{manufacturer}</span></a>"
        f"<div class=\"summary\"><div class=\"description long\"><div class=\"body-text\">{title}</div></div></div>"
        f"<div id=\"prices\"><div class=\"product-name\" title=\"{title}\"></div></div>"
        "<div class=\"prices\"><div class=\"final-price\"><span class=\"integer-part\">199</span><span class=\"decimal-part\">00</span></div></div>"
        "<div id=\"specs\"><div class=\"spec-groups\">"
        "<div class=\"spec-details\"><h3>Χαρακτηριστικά</h3>"
        f"<dl><dt>Κατασκευαστής</dt><dd>{manufacturer or 'Άγνωστο'}</dd></dl>"
        f"<dl><dt>Μοντέλο</dt><dd>{model}</dd></dl>"
        "</div>"
        "</div></div>"
        "</body>"
        "</html>"
    )


def test_built_in_oven_slug_overrides_generic_cooker_category() -> None:
    parser = SkroutzProductParser()
    resolver = TaxonomyResolver()
    row = {
        "name": "LG WS7D7631WB Φούρνος άνω Πάγκου 76lt Π59.2εκ. Μαύρος",
        "category_tag_text": "Κουζίνες & Φούρνοι",
        "category_tag_href": "https://www.skroutz.gr/c/26/kouzines.html",
        "manufacturer": "LG",
        "skroutz_product_url": "https://www.skroutz.gr/s/57391521/LG-WS7D7631WB-Fournos-ano-Pagou-76lt-P59-2ek-Mayros.html",
        "model": "WS7D7631WB",
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
    assert parsed.source.skroutz_family == "built_in_appliance"
    assert taxonomy.parent_category == "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ"
    assert taxonomy.leaf_category == "Εντοιχιζόμενες Συσκευές"
    assert taxonomy.sub_category == "Φούρνοι"
