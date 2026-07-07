from __future__ import annotations

from product_factory.parser_product_plus4u import Plus4UProductParser
from product_factory.source_detection import detect_source, validate_url_scope

PLUS4U_URL = "https://www.plus4u.gr/showitem.php?ID=102085407"


def test_plus4u_url_is_supported_product_scope() -> None:
    assert detect_source(PLUS4U_URL) == "plus4u"
    assert validate_url_scope(PLUS4U_URL) == (
        "plus4u",
        True,
        "plus4u_product_path",
    )
    assert validate_url_scope(
        "https://www.plus4u.gr/kafetiera-nespresso-delonghi-en110.b-u/102085407-102085407/p"
    ) == ("plus4u", True, "plus4u_product_path")


def test_plus4u_parser_decodes_payload_specs_and_gallery() -> None:
    html = """
    <html>
      <head>
        <meta property="og:url" content="https://www.plus4u.gr/showitem.php?ID=102085407" />
      </head>
      <body>
        <script>
        var product=JsonFromPHP('{"table":"102","id":"102085407","kodikos":"102085407","title":"{!KAPA!}{!ALFA!}{!FI!}{!EPSILON!}{!TAF!}{!IOTA!}{!EPSILON!}{!RO!}{!ALFA!} NESPRESSO DELONGHI EN110.B U","item_link":"https:\\/\\/www.plus4u.gr\\/kafetiera-nespresso-delonghi-en110.b-u\\/102085407-102085407\\/p","price":"0","category":"{!KAPA!}{!ALFA!}{!FI!}{!EPSILON!}{!TAF!}{!IOTA!}{!EPSILON!}{!RO!}{!EPSILON!}{!SIGMA!} ESPRESSO","subcat":"{!GAMA!}{!IOTA!}{!ALFA!} {!ALFA!}{!LAMDA!}{!EPSILON!}{!SIGMA!}{!MI!}{!EPSILON!}{!NI!}{!OMIKRON!} {!KAPA!}{!ALFA!}{!FI!}{!EPSILON!}","developer":"DELONGHI","description":"<tab1>{!KAPA!}{!ALFA!}{!FI!}{!EPSILON!}{!TAF!}{!IOTA!}{!EPSILON!}{!RO!}{!ALFA!} NESPRESSO DELONGHI EN110.B U{!return!}{!new_line!}<li>{!PI!}{!iota_tonos!}{!epsilon!}{!sigma!}{!eta!} 19 bar<\\/tab1><tab2><dfBar>{!PI!}{!iota_tonos!}{!epsilon!}{!sigma!}{!ita!} 19 bar<\\/dfBar><df{!IOTA!}{!sigma!}{!xi!}{!ipsilon_tonos!}{!sigma_teliko!} (Watt)>1260 Watt<\\/df{!IOTA!}{!sigma!}{!xi!}{!ipsilon_tonos!}{!sigma_teliko!} (Watt)><\\/tab2>","DescFields":{"Bar":"{!PI!}{!iota_tonos!}{!epsilon!}{!sigma!}{!ita!} 19 bar","{!IOTA!}{!sigma!}{!xi!}{!ipsilon_tonos!}{!sigma_teliko!} (Watt)":"1260 Watt"}}');
        var item_big_image='/images/102/BIG/102085407.jpg';
        </script>
      </body>
    </html>
    """

    parsed = Plus4UProductParser().parse(html, PLUS4U_URL)
    source = parsed.source
    specs = {item.label: item.value for item in source.spec_sections[0].items}

    assert source.source_name == "plus4u"
    assert source.name == "ΚΑΦΕΤΙΕΡΑ NESPRESSO DELONGHI EN110.B U"
    assert source.brand == "DELONGHI"
    assert source.product_code == "102085407"
    assert source.mpn == "EN110.B"
    assert "Espresso" in source.breadcrumbs
    assert specs["Πίεση Ατμού"] == "19 bar"
    assert "1260 Watt" in specs.values()
    assert source.gallery_images[0].url == "https://www.plus4u.gr/images/102/BIG/102085407.jpg"
