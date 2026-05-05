from pipeline.parser_product import ElectronetProductParser
from pipeline.schema_matcher import SchemaMatcher

HTML = """
<html>
  <head>
    <title>Σκούπα Stick Rowenta X-Force Flex 9.60 RH2099 Κόκκινο - Electronet.gr</title>
    <link rel="canonical" href="https://www.electronet.gr/exoplismos-spitioy/skoypisma/skoypes-stick/skoypa-stick-rowenta-x-force-flex-960-rh2099-kokkino" />
  </head>
  <body>
    <nav class="breadcrumb"><a>Αρχική</a><a>Εξοπλισμός Σπιτιού</a><a>Σκούπισμα</a><a>Σκούπες Stick</a></nav>
    <div id="cscp-sku">343700</div>
    <article class="product-page available" data-sku="343700">
      <div id="product-brand-logo"><a href="/brand/rowenta">Rowenta</a></div>
      <h1 class="product-title">Σκούπα Stick Rowenta X-Force Flex 9.60 RH2099 Κόκκινο</h1>
      <div id="product-price" data-price="249">
        <span class="price">249,00 €</span>
        <ul><li class="prod-tags-freeinstallments">12 άτοκες δόσεις</li></ul>
      </div>
      <div class="product-desc"><p>Απολαύστε ισχυρή απόδοση και άνεση στον καθαρισμό με τη Rowenta RH2099.</p></div>
      <div id="product-main-attributes">
        <div class="product-main-attribute"><span class="my-label">Τάση Volt</span><span class="my-value">18,5</span></div>
        <div class="product-main-attribute"><span class="my-label">Χρόνος Λειτουργίας σε Λεπτά</span><span class="my-value">45</span></div>
      </div>
      <div class="availability">
        <div><div class="cpa-label">Παράδοση</div><div>Διαθέσιμο για παράδοση στον χώρο σου</div></div>
        <div><div class="cpa-label">Παραλαβή</div><div>Επιλέξτε κατάστημα για να δείτε τη διαθεσιμότητα</div></div>
      </div>
      <img class="lightbox" src="/image/catalog/products/343700/main.jpg" alt="Σκούπα Stick Rowenta X-Force Flex 9.60 RH2099 Κόκκινο" />
      <img class="lightbox" src="/image/catalog/products/343700/2.jpg" alt="Σκούπα Stick Rowenta X-Force Flex 9.60 RH2099 Κόκκινο πλευρικά" />
      <h2>Παρουσίαση Προϊόντος</h2>
      <div class="ck-text inline"><h3>ΕΞΑΙΡΕΤΙΚΑ ΑΠΟΤΕΛΕΣΜΑΤΙΚΟ ΚΑΘΑΡΙΣΜΑ</h3><p>Εξαιρετικά αποτελεσματικό καθάρισμα σε όλα τα δάπεδα.</p></div>
      <div class="ck-text inline"><h3>ΔΙΠΛΑΣΙΑ ΑΥΤΟΝΟΜΙΑ</h3><p>Δύο αφαιρούμενες μπαταρίες για καθαρισμό χωρίς διακοπές.</p></div>
      <h2>Τεχνικά Χαρακτηριστικά</h2>
      <h3>Επισκόπηση Προϊόντος</h3>
      <table>
        <tr><th>Τύπος Μπαταρίας</th><td>Li-Ion</td></tr>
        <tr><th>Τάση Volt</th><td>18,5</td></tr>
      </table>
      <h3>Γενικά Χαρακτηριστικά</h3>
      <table>
        <tr><th>Χρώμα</th><td>Κόκκινο</td></tr>
      </table>
    </article>
  </body>
</html>
"""


def test_product_parser_extracts_visible_code_and_specs() -> None:
    matcher = SchemaMatcher()
    parser = ElectronetProductParser(known_section_titles=matcher.known_section_titles)
    parsed = parser.parse(HTML, "https://www.electronet.gr/exoplismos-spitioy/skoypisma/skoypes-stick/skoypa-stick-rowenta-x-force-flex-960-rh2099-kokkino")
    assert parsed.source.product_code == "343700"
    assert parsed.source.brand == "Rowenta"
    assert parsed.source.mpn == "RH2099"
    assert parsed.source.name.startswith("Σκούπα Stick Rowenta")
    assert parsed.source.price_value == 249.0
    assert parsed.source.breadcrumbs[-1] == "Σκούπες Stick"
    assert len(parsed.source.spec_sections) == 2
    assert parsed.source.spec_sections[0].items[0].label == "Τύπος Μπαταρίας"
    assert parsed.field_diagnostics["brand"].confidence > 0.0
    assert parsed.field_diagnostics["brand"].selector_trace
    assert parsed.field_diagnostics["spec_sections"].value_present is True
    assert parsed.field_diagnostics["spec_sections"].selector_trace


def test_product_parser_extracts_greek_letter_model_token_as_mpn() -> None:
    matcher = SchemaMatcher()
    parser = ElectronetProductParser(known_section_titles=matcher.known_section_titles)
    html = """
    <html>
      <body>
        <article class="product-page available" data-sku="339576">
          <div id="product-brand-logo"><a href="/brand/tefal">Tefal</a></div>
          <h1 class="product-title">Αποχυμωτής Tefal Frutelia + ΖΕ3701 Λευκό</h1>
          <div id="cscp-sku">339576</div>
          <div id="product-price"><span class="price">48,90 €</span></div>
          <div class="product-desc"><p>Ο αποχυμωτής Tefal Frutelia+ παράγει φρέσκους χυμούς.</p></div>
          <div id="product-details">
            <div class="prop-group-wrapper">
              <h3 class="prop-group-title">Επισκόπηση Προϊόντος</h3>
              <div class="property"><div>Ισχύς σε Watts</div><div>350</div></div>
            </div>
          </div>
          <img class="lightbox" src="/sites/default/files/styles/product_large/public/339576.jpg.webp" alt="Αποχυμωτής Tefal Frutelia + ΖΕ3701 Λευκό" />
        </article>
      </body>
    </html>
    """

    parsed = parser.parse(html, "https://www.electronet.gr/example")

    assert parsed.source.product_code == "339576"
    assert parsed.source.mpn == "ΖΕ3701"
    assert parsed.field_diagnostics["mpn"].selected_strategy == "title_after_brand"


def test_product_parser_extracts_spaced_model_sequence_as_mpn() -> None:
    matcher = SchemaMatcher()
    parser = ElectronetProductParser(known_section_titles=matcher.known_section_titles)
    html = """
    <html>
      <body>
        <article class="product-page available" data-sku="226826">
          <div id="product-brand-logo"><a href="/brand/miele">Miele</a></div>
          <h1 class="product-title">Εστία Κεραμική Miele KM 6520 FR</h1>
          <div id="cscp-sku">226826</div>
          <div id="product-price"><span class="price">749,00 €</span></div>
          <div class="product-desc"><p>Ηλεκτρική εστία με χειριστήρια επί της συσκευής.</p></div>
          <div id="product-details">
            <div class="prop-group-wrapper">
              <h3 class="prop-group-title">Επισκόπηση Προϊόντος</h3>
              <div class="property"><div>Τεχνολογία Πλατώ Εστιών</div><div>Αυτόνομο κεραμικό ηλεκτρικό</div></div>
            </div>
          </div>
          <img class="lightbox" src="/sites/default/files/styles/product_large/public/226826.jpg.webp" alt="Εστία Κεραμική Miele KM 6520 FR" />
        </article>
      </body>
    </html>
    """

    parsed = parser.parse(html, "https://www.electronet.gr/example")

    assert parsed.source.product_code == "226826"
    assert parsed.source.mpn == "KM 6520 FR"
    assert parsed.field_diagnostics["mpn"].selected_strategy == "title_after_brand"


def test_product_parser_preserves_video_block_in_presentation_source_html() -> None:
    matcher = SchemaMatcher()
    parser = ElectronetProductParser(known_section_titles=matcher.known_section_titles)
    html = """
    <html>
      <body>
        <article class="product-page available">
          <div id="product-presentation">
            <h2>Παρουσίαση Προϊόντος</h2>
            <div class="ck-text whole">
              <h2>Video Title</h2>
              <video autoplay="" loop="" muted="" playsinline="" style="width: 70%;"><source src="/media/demo.mp4" type="video/mp4" /></video>
            </div>
            <div class="ck-text inline"><h2>Section One</h2><p>Paragraph one.</p></div>
            <div class="ck-text inline"><h2>Section Two</h2><ul><li>Bullet one.</li></ul></div>
          </div>
          <div id="product-details"><div class="prop-group-wrapper"><h3>Επισκόπηση Προϊόντος</h3></div></div>
          <div id="product-brand-logo"><a href="/brand/rowenta">Rowenta</a></div>
          <h1 class="product-title">Rowenta Example RH2099</h1>
          <div id="cscp-sku">343700</div>
          <div id="product-price"><span class="price">249,00 €</span></div>
        </article>
      </body>
    </html>
    """

    parsed = parser.parse(html, "https://www.electronet.gr/example")

    assert '<video autoplay="" loop="" muted="" playsinline="" style="width: 70%;"><source src="/media/demo.mp4" type="video/mp4"/></video>' in parsed.source.presentation_source_html
    assert parsed.field_diagnostics["presentation_blocks"].value_present is True
    assert parsed.field_diagnostics["presentation_blocks"].value_preview == "2"


def test_product_parser_prefers_eprel_modal_assets_over_arrow_thumbnail() -> None:
    matcher = SchemaMatcher()
    parser = ElectronetProductParser(known_section_titles=matcher.known_section_titles)
    html = """
    <html>
      <body>
        <article class="product-page available">
          <div class="eprel-modal-links-wrapper">
            <a
              href="#"
              class="eprel-modal-trigger"
              data-label-url="/labels/electronicdisplays/Label_2204959.png"
              data-pdf-url="/fiches/electronicdisplays/Fiche_2204959_EL.pdf"
              data-open="energy-label-modal"
            >
              <img src="/modules/custom/custom_eprel/energy_arrows/G-Left-Red-WithAGScale.svg" alt="Energy Class G" />
            </a>
          </div>
          <div id="product-brand-logo"><a href="/brand/samsung">Samsung</a></div>
          <h1 class="product-title">TV Samsung QE50QN80F 50'' Smart 4K Mini LED AI</h1>
          <div id="cscp-sku">142687</div>
          <div id="product-price"><span class="price">699,00 €</span></div>
          <div id="product-details"><div class="prop-group-wrapper"><h3>Εικόνα - Ήχος</h3></div></div>
        </article>
      </body>
    </html>
    """

    parsed = parser.parse(html, "https://www.electronet.gr/example")

    assert parsed.source.energy_label_asset_url == "https://eprel.ec.europa.eu/labels/electronicdisplays/Label_2204959.png"
    assert parsed.source.product_sheet_asset_url == "https://eprel.ec.europa.eu/fiches/electronicdisplays/Fiche_2204959_EL.pdf"

