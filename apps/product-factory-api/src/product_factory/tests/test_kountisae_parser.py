from __future__ import annotations

from product_factory.parser_product_kountisae import KountisAEProductParser
from product_factory.source_detection import detect_source, validate_url_scope

KOUNTISAE_URL = (
    "https://www.kountisae.gr/product/"
    "hisense-wf1i7022bwj-plyntirio-ebrosthias-fortosis-slim-7-kilon-1200-strofon-programma-atmou/"
)


def test_kountisae_url_is_supported_product_scope() -> None:
    assert detect_source(KOUNTISAE_URL) == "kountisae"
    assert validate_url_scope(KOUNTISAE_URL) == (
        "kountisae",
        True,
        "kountisae_product_path",
    )


def test_kountisae_parser_extracts_description_specs_and_gallery_order() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.kountisae.gr/product/hisense-wf1i7022bwj-plyntirio-ebrosthias-fortosis-slim-7-kilon-1200-strofon-programma-atmou/">
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Product","name":"HISENSE WF1I7022BWJ ΠΛΥΝΤΗΡΙΟ ΕΜΠΡΟΣΘΙΑΣ ΦΟΡΤΩΣΗΣ SLIM 7 ΚΙΛΩΝ 1200 ΣΤΡΟΦΩΝ ΠΡΟΓΡΑΜΜΑ ΑΤΜΟΥ","brand":{"@type":"Brand","name":"Hisense"},"offers":{"@type":"Offer","price":"299.00"}}
        </script>
      </head>
      <body>
        <nav class="woocommerce-breadcrumb">
          <a>Αρχική</a>
          <a>Λευκές Συσκευές</a>
          <a>Πλυντήρια Ρούχων</a>
        </nav>
        <h1 class="product_title">HISENSE WF1I7022BWJ ΠΛΥΝΤΗΡΙΟ ΕΜΠΡΟΣΘΙΑΣ ΦΟΡΤΩΣΗΣ SLIM 7 ΚΙΛΩΝ 1200 ΣΤΡΟΦΩΝ ΠΡΟΓΡΑΜΜΑ ΑΤΜΟΥ</h1>
        <figure class="woocommerce-product-gallery__wrapper">
          <img src="https://www.kountisae.gr/wp-content/uploads/2026/07/HISENSE-WF1I7022BWJ_5.jpg">
          <img src="https://www.kountisae.gr/wp-content/uploads/2026/07/HISENSE-WF1I7022BWJ_1.jpg">
          <img src="https://www.kountisae.gr/wp-content/uploads/2026/07/HISENSE-WF1I7022BWJ_2.jpg">
          <img src="https://www.kountisae.gr/wp-content/uploads/2026/07/HISENSE-WF1I7022BWJ_3.jpg">
          <img src="https://www.kountisae.gr/wp-content/uploads/2026/07/HISENSE-WF1I7022BWJ_4.jpg">
        </figure>
        <div id="tab-description">
          <p>Το Hisense WF1I7022BWJ είναι ένα σύγχρονο πλυντήριο ρούχων χωρητικότητας 7 kg με πρόγραμμα ατμού και ταχύτητα στυψίματος 1200 στροφών.</p>
          <h3>Βασικά Στοιχεία</h3>
          <p>Κατηγορία: Πλυντήριο ρούχων</p>
          <p>Εμπορικός κωδικός: WF1I7022BWJ</p>
          <p>Κωδικός EAN: 6901101837462</p>
          <p>Χρώμα: Λευκό</p>
          <h3>Απόδοση Πλύσης</h3>
          <p>Χωρητικότητα πλύσης: 7 kg</p>
          <p>Ταχύτητα στυψίματος: 1200 στροφές/λεπτό</p>
          <h3>Ενεργειακή Απόδοση</h3>
          <p>Ενεργειακή κλάση: A</p>
          <p>Επίπεδο θορύβου κατά το στύψιμο: 72 dB</p>
        </div>
      </body>
    </html>
    """

    parsed = KountisAEProductParser().parse(html, KOUNTISAE_URL)
    source = parsed.source
    specs = {
        item.label: item.value
        for section in source.spec_sections
        for item in section.items
    }

    assert source.source_name == "kountisae"
    assert source.brand == "Hisense"
    assert source.mpn == "WF1I7022BWJ"
    assert source.product_code == ""
    assert source.category_tag_text == "Πλυντήρια Ρούχων"
    assert source.taxonomy_rule_id == "kountisae:washing_machine"
    assert specs["Χωρητικότητα πλύσης"] == "7 kg"
    assert specs["Ταχύτητα στυψίματος"] == "1200 στροφές/λεπτό"
    assert specs["Τρόπος Φόρτωσης"] == "Εμπρόσθιας Φόρτωσης"
    assert specs["Ενεργειακή κλάση"] == "A"
    assert source.gallery_images[0].url.endswith("HISENSE-WF1I7022BWJ_5.jpg")
    assert source.gallery_images[1].url.endswith("HISENSE-WF1I7022BWJ_4.jpg")
    assert source.gallery_images[2].url.endswith("HISENSE-WF1I7022BWJ_1.jpg")
    assert parsed.critical_missing == []
