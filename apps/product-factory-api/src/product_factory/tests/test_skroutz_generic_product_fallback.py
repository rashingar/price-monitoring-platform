import json

from product_factory.parser_product_skroutz import SkroutzProductParser


def test_unknown_skroutz_product_category_remains_a_product_detail_page() -> None:
    url = "https://www.skroutz.gr/s/98765432/example-collectible.html"
    html = f"""
    <html><head>
      <link rel="canonical" href="{url}" />
      <script id="product-schema" type="application/ld+json">
        {json.dumps({"@type": "Product", "name": "Acme Collectible X-1", "sku": "98765432", "mpn": "X-1", "brand": {"name": "Acme"}})}
      </script>
    </head><body>
      <div class="sku-title">
        <a class="category-tag" href="https://www.skroutz.gr/c/99999/collectibles.html">Collectibles</a>
        <h1 class="page-title">Acme Collectible X-1</h1>
      </div>
      <div class="summary"><div class="description long"><div class="body-text">Verified product details.</div></div></div>
    </body></html>
    """

    parsed = SkroutzProductParser().parse(html, url)

    assert parsed.source.page_type == "product"
    assert parsed.source.category_tag_text == "Collectibles"
    assert "skroutz_generic_product_taxonomy_fallback" in parsed.warnings
