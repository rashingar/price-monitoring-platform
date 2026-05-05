from pipeline.parser_product_manufacturer import ManufacturerProductParser
from pipeline.normalize import normalize_for_match


def test_manufacturer_product_parser_extracts_tefal_product_data() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://shop.tefal.gr/products/dolci-%CF%80%CE%B1%CE%B3%CF%89%CF%84%CE%BF%CE%BC%CE%B7%CF%87%CE%B1%CE%BD%CE%AE-ig602a">
        <meta property="og:title" content="Tefal Dolci Παγωτομηχανή IG602A">
        <meta property="og:price:amount" content="229.90">
        <script class="json-item" type="application/json">
          {"item_name":"Rowenta Access Steam Σίδερο Ατμού DW4301","item_brand":"ROWENTA","price":"69.90","url":"https://shop.tefal.gr/products/rowenta-dw4301"}
        </script>
        <script class="json-item" type="application/json">
          {"item_name":"Tefal Dolci Παγωτομηχανή IG602A","item_brand":"TEFAL","price":"229.90","url":"https://shop.tefal.gr/products/dolci-%CF%80%CE%B1%CE%B3%CF%89%CF%84%CE%BF%CE%BC%CE%B7%CF%87%CE%B1%CE%BD%CE%AE-ig602a"}
        </script>
      </head>
      <body>
        <clrz-slider-product>
          <div class="product-slider-main">
            <div class="swiper-slide"><img src="/cdn/main-1.jpg" /></div>
            <div class="swiper-slide"><img src="/cdn/main-2.jpg" /></div>
          </div>
        </clrz-slider-product>

        <h1>Tefal Dolci Παγωτομηχανή IG602A</h1>

        <section id="shopify-section-template--1__product_title_description_abc">
          <div class="t-container">
            <h2 class="t-h2">Λαχταριστό σπιτικό παγωτό</h2>
            <div class="t-text">
              <p>Παγωτομηχανή με 10 προγράμματα, χωρητικότητα 1,4 L και 3 μπολ για απολαυστικές συνταγές.</p>
              <ul>
                <li>Ιδανική και για vegan επιλογές.</li>
              </ul>
            </div>
          </div>
        </section>

        <section id="shopify-section-template--1__product_push_highlight_abc">
          <ul>
            <li class="push-card">
              <h3 id="card-title-1">Εξατομίκευση στο μέγιστο</h3>
              <div class="t-text">Προσθέστε γαρνιτούρες εύκολα σε κάθε συνταγή.</div>
              <picture><img src="/cdn/card-1.jpg" /></picture>
            </li>
          </ul>
        </section>

        <section id="shopify-section-template--1__product_edito_blog_1_abc">
          <div class="strate-edito-blog__image"><img src="/cdn/blog-1.jpg" /></div>
          <div class="strate-edito-blog__text">
            <h3 class="t-h2">Παγωτό με μία μόνο κίνηση</h3>
            <div class="t-text">
              <p>Η τεχνολογία 1-Step Perfector προσφέρει κρεμώδες αποτέλεσμα από την πρώτη χρήση.</p>
            </div>
          </div>
        </section>

        <div data-tab-content="about-the-product">
          <div class="u-flex u-justify-between u-items-center u-py-16 u-border-b u-border-light-grey u-gap-4">
            <span class="t-text-medium u-text-dark-grey u-w-1/2">Τάση</span>
            <div class="t-text u-text-dark-grey u-text-right u-w-1/2">220-240 V</div>
          </div>
          <div class="u-flex u-justify-between u-items-center u-py-16 u-border-b u-border-light-grey u-gap-4">
            <span class="t-text-medium u-text-dark-grey u-w-1/2">Συχνότητα</span>
            <div class="t-text u-text-dark-grey u-text-right u-w-1/2">50-60 Hz</div>
          </div>
        </div>
      </body>
    </html>
    """

    parsed = ManufacturerProductParser().parse(
        html,
        "https://shop.tefal.gr/products/dolci-%CF%80%CE%B1%CE%B3%CF%89%CF%84%CE%BF%CE%BC%CE%B7%CF%87%CE%B1%CE%BD%CE%AE-ig602a",
        source_name="manufacturer_tefal",
    )
    flattened = {
        normalize_for_match(item.label): item.value
        for section in [*parsed.source.spec_sections, *parsed.source.manufacturer_spec_sections]
        for item in section.items
    }

    assert parsed.source.source_name == "manufacturer_tefal"
    assert parsed.source.brand == "Tefal"
    assert parsed.source.mpn == "IG602A"
    assert parsed.source.product_code == "IG602A"
    assert parsed.source.price_value == 229.9
    assert parsed.source.breadcrumbs[-1] == "Παγωτομηχανές"
    assert parsed.source.taxonomy_rule_id == "manufacturer_tefal:ice_cream_maker"
    assert len(parsed.source.gallery_images) == 2
    assert flattened[normalize_for_match("Χωρητικότητα")] == "1,4 lt"
    assert flattened[normalize_for_match("Αριθμός Προγραμμάτων")] == "10"
    assert flattened[normalize_for_match("Αριθμός Δοχείων")] == "3"
    assert flattened[normalize_for_match("Διατροφικές Επιλογές")] == "Vegan"
    assert flattened[normalize_for_match("Τάση")] == "220-240 V"
    assert parsed.critical_missing == []

