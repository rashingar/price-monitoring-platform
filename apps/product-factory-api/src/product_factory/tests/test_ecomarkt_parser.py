from __future__ import annotations

from product_factory.parser_product_ecomarkt import EcomarktProductParser


ECOMARKT_HTML = """
<html>
<head>
  <link rel="canonical" href="https://www.ecomarkt.gr/brandt-bt3838q-plynthrio-royxwn-anw-fortwshs_el-gr" />
  <meta name="description" content="BRANDT BT38038Q Πλυντήριο ρούχων άνω φόρτωσης" />
</head>
<body>
  <ul class="breadcrumb">
    <li><a href="/">Αρχική</a></li>
    <li><a href="/large">Μεγάλες οικιακές συσκευές</a></li>
    <li><a href="/washing">Πλυντήρια ρούχων</a></li>
  </ul>
  <h1 class="product_title">BRANDT BT38038Q Πλυντήριο ρούχων άνω φόρτωσης 8kg 1300rpm A</h1>
  <div class="product_image_col">
    <img src="https://www.ecomarkt.gr/image/cache/catalog/products/1014048-image1-1200x1200.jpg" alt="main" />
    <img src="https://www.ecomarkt.gr/image/cache/catalog/products/1014048-image2-1200x1200.jpg" alt="second" />
    <img src="https://www.ecomarkt.gr/image/cache/catalog/products/1014048-image1-74x74.jpg" alt="thumb" />
  </div>
  <div id="product">
    <input name="product_id" type="hidden" value="5506290" />
    <span class="detail price-new">469,00€ <span class="detail price-old">499,00€</span></span>
  </div>
  <div id="tab-description">
    Χωρητικότητα τυμπάνου 8 kg<br>
    Στροφές 1300<br>
    Ενεργειακή κλάση Α<br>
    Οθόνη<br>
    Ψηφιακή<br>
    Kατανάλωση ενέργειας 47 kWh/100 κύκλους λειτουργίας (στο πρόγραμμα Eco)<br>
    Διαστάσεις (ΥxΠxΒ) 87.5 x 40 x 61 cm<br>
    Χρώμα Λευκό
  </div>
</body>
</html>
"""


def test_ecomarkt_parser_extracts_product_data_and_supplemental_specs() -> None:
    parsed = EcomarktProductParser().parse(
        ECOMARKT_HTML,
        "https://www.ecomarkt.gr/brandt-bt3838q-plynthrio-royxwn-anw-fortwshs_el-gr",
    )

    source = parsed.source

    assert source.source_name == "ecomarkt"
    assert source.name.startswith("BRANDT BT38038Q")
    assert source.brand == "Brandt"
    assert source.mpn == "BT38038Q"
    assert source.product_code == "5506290"
    assert source.price_value == 469
    assert source.breadcrumbs == [
        "Μεγάλες οικιακές συσκευές",
        "Πλυντήρια ρούχων",
    ]
    assert [image.url for image in source.gallery_images] == [
        "https://www.ecomarkt.gr/image/cache/catalog/products/1014048-image1-1200x1200.jpg",
        "https://www.ecomarkt.gr/image/cache/catalog/products/1014048-image2-1200x1200.jpg",
    ]

    specs = {
        item.label: item.value for section in source.spec_sections for item in section.items
    }
    assert specs["Χωρητικότητα τυμπάνου"] == "8 kg"
    assert specs["Οθόνη"] == "Ψηφιακή"
    assert specs["Χρώμα"] == "Λευκό"

    manufacturer_specs = {
        item.label: item.value
        for section in source.manufacturer_spec_sections
        for item in section.items
    }
    assert manufacturer_specs["EAN"] == "3660767992740"
    assert manufacturer_specs["Διάρκεια προγράμματος ECO 40-60"] == "218 min"
    assert manufacturer_specs["Κλείδωμα Ασφαλείας για Παιδιά"] == "Ναι"
    assert manufacturer_specs["Προγραμματισμός Έναρξης"] == "Έως 24 ώρες"
    assert manufacturer_specs["Επιπλέον Ξεβγάλματος"] == "Ναι"
    assert source.manufacturer_documents == [
        {
            "name": "Boulanger product sheet",
            "document_type": "pdf",
            "url": "https://boulanger.scene7.com/is/content/Boulanger/3660767992740_f_0",
        }
    ]
