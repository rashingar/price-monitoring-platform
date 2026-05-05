from pipeline.parser_product_skroutz import SkroutzProductParser
from pipeline.taxonomy import TaxonomyResolver


def test_robot_vacuum_category_resolves_to_vacuuming_taxonomy() -> None:
    html = (
        "<!DOCTYPE html>"
        "<html lang=\"el\">"
        "<head>"
        "<meta charset=\"utf-8\" />"
        "<title>Rowenta S90+ Σκούπα Ρομπότ για Σκούπισμα &amp; Σφουγγάρισμα με Χαρτογράφηση και Wi‑Fi Λευκή</title>"
        "<link rel=\"canonical\" href=\"https://www.skroutz.gr/s/64954633/rowenta-s90-skoupa-rompot-gia-skoupisma-sfougarisma-me-chartografisi-kai-wi-fi-leyki.html\" />"
        "<script id=\"product-schema\" type=\"application/ld+json\">"
        "{\"@context\":\"https://schema.org\",\"@type\":\"Product\",\"name\":\"Rowenta S90+ Σκούπα Ρομπότ για Σκούπισμα & Σφουγγάρισμα με Χαρτογράφηση και Wi-Fi Λευκή\",\"brand\":{\"@type\":\"Brand\",\"name\":\"Rowenta\"},\"mpn\":\"S90+\",\"sku\":\"344708\",\"category\":\"Σκούπες Ρομπότ\",\"image\":[\"https://static.skroutz.gr/mock/344708/1.jpg\"],\"offers\":{\"@type\":\"Offer\",\"price\":\"199.00\",\"priceCurrency\":\"EUR\"}}"
        "</script>"
        "</head>"
        "<body>"
        "<div class=\"sku-title\">"
        "<a class=\"category-tag\" href=\"https://www.skroutz.gr/c/2401/Skoypa-Rompot.html\">Σκούπες Ρομπότ</a>"
        "<h1 class=\"page-title\">Rowenta S90+ Σκούπα Ρομπότ για Σκούπισμα &amp; Σφουγγάρισμα με Χαρτογράφηση και Wi-Fi Λευκή<small class=\"sku-code\">Κωδικός: 344708</small></h1>"
        "</div>"
        "<a class=\"brand-page-link\"><span>Rowenta</span></a>"
        "<div class=\"summary\"><div class=\"description long\"><div class=\"body-text\">Σκούπα ρομπότ με σκούπισμα και σφουγγάρισμα.</div></div></div>"
        "<div id=\"prices\"><div class=\"product-name\" title=\"Rowenta S90+\"></div></div>"
        "<div class=\"prices\"><div class=\"final-price\"><span class=\"integer-part\">199</span><span class=\"decimal-part\">00</span></div></div>"
        "<div id=\"specs\"><div class=\"spec-groups\"><div class=\"spec-details\"><h3>Χαρακτηριστικά</h3>"
        "<dl><dt>Κατασκευαστής</dt><dd>Rowenta</dd></dl>"
        "<dl><dt>Μοντέλο</dt><dd>S90+</dd></dl>"
        "</div></div></div>"
        "</body>"
        "</html>"
    )

    parser = SkroutzProductParser()
    parsed = parser.parse(html, "https://www.skroutz.gr/s/64954633/rowenta-s90-skoupa-rompot-gia-skoupisma-sfougarisma-me-chartografisi-kai-wi-fi-leyki.html")
    taxonomy, _ = TaxonomyResolver().resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url,
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )

    assert parsed.source.page_type == "product"
    assert parsed.source.skroutz_family == "robot_vacuum"
    assert taxonomy.parent_category == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert taxonomy.leaf_category == "Σκούπισμα"
    assert taxonomy.sub_category == "Σκούπες Ρομπότ"

