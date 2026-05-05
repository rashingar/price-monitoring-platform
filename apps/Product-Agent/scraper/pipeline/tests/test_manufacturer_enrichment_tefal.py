from pipeline.manufacturer_enrichment import _parse_tefal_shop_product_html, _parse_tefal_shop_product_page
from pipeline.normalize import normalize_for_match


def test_parse_tefal_shop_product_html_extracts_spec_rows() -> None:
    html = """
    <div data-tab-content="about-the-product">
      <div class="u-flex u-justify-between u-items-center u-py-16 u-border-b u-border-light-grey u-gap-4">
        <span class="t-text-medium u-text-dark-grey u-w-1/2">Τύπος βούρτσας</span>
        <div class="t-text u-text-dark-grey u-text-right u-w-1/2">Βούρτσα Animal Turbo</div>
      </div>
      <div class="u-flex u-justify-between u-items-center u-py-16 u-border-b u-border-light-grey u-gap-4">
        <span class="t-text-medium u-text-dark-grey u-w-1/2">Χωρητικότητα δοχείου σκόνης</span>
        <div class="t-text u-text-dark-grey u-text-right u-w-1/2">0.26 L</div>
      </div>
    </div>
    """

    sections = _parse_tefal_shop_product_html(html)
    flattened = {
        normalize_for_match(item.label): item.value
        for section in sections
        for item in section.items
    }

    assert len(sections) == 1
    assert sections[0].section == "Χαρακτηριστικά Κατασκευαστή"
    assert flattened[normalize_for_match("Τύπος βούρτσας")] == "Βούρτσα Animal Turbo"
    assert flattened[normalize_for_match("Χωρητικότητα δοχείου σκόνης")] == "0.26 L"


def test_parse_tefal_shop_product_page_extracts_intro_and_presentation_sections() -> None:
    html = """
    <section id="shopify-section-template--1__product_title_description_abc">
      <div class="t-container">
        <h2 class="t-h2">Λαχταριστό σπιτικό παγωτό — 100% προσαρμοσμένο στις προτιμήσεις και τις ανάγκες σας!</h2>
        <div class="t-text">
          <p>Από πεντανόστιμο σορμπέ, λαχταριστό παγωτό και κρεμώδες τζελάτο μέχρι παγωμένο γιαούρτι, σμούθι, μιλκσέικ και άλλα.</p>
        </div>
      </div>
    </section>
    <section id="shopify-section-template--1__product_push_highlight_abc">
      <ul>
        <li class="push-card">
          <h3 id="card-title-1">Εξατομίκευση στο μέγιστο</h3>
          <div class="t-text">Αφήστε τη δημιουργικότητά σας ελεύθερη με ένα ειδικό πρόγραμμα για γαρνιτούρες.</div>
          <picture><img src="/cdn/card-1.jpg" /></picture>
        </li>
        <li class="push-card">
          <h3 id="card-title-2">Ο απόλυτος βοηθός καθαρισμού</h3>
          <div class="t-text">Το πρόγραμμα αυτόματου ξεπλύματος διευκολύνει το καθάρισμα.</div>
          <picture><img src="/cdn/card-2.jpg" /></picture>
        </li>
      </ul>
    </section>
    <section id="shopify-section-template--1__product_edito_blog_1_abc">
      <div class="strate-edito-blog__image"><img src="/cdn/blog-1.jpg" /></div>
      <div class="strate-edito-blog__text">
        <h3 class="t-h2">Πεντανόστιμο παγωτό με μία μόνο κίνηση</h3>
        <div class="t-text">
          <p>Η τεχνολογία 1-Step Perfector προσφέρει ομοιόμορφο και κρεμώδες αποτέλεσμα.</p>
        </div>
      </div>
    </section>
    <section id="shopify-section-template--1__product_edito_blog_2_abc">
      <div class="strate-edito-blog__image"><img src="/cdn/blog-2.jpg" /></div>
      <div class="strate-edito-blog__text">
        <h3 class="t-h2">Εμπνευστείτε</h3>
        <div class="t-text">
          <p>Ψηφιακό βιβλίο συνταγών με 50 ιδέες για να ξεκινήσετε.</p>
        </div>
      </div>
    </section>
    """

    result = _parse_tefal_shop_product_page(
        html,
        search_body_html="""
        <ul>
          <li>Παγωτομηχανή που διαθέτει 10 προγράμματα σε 1 για ατελείωτες παγωμένες λιχουδιές</li>
          <li>Ετοιμάστε έως 1,4 L παγωτού χρησιμοποιώντας τα 3 μπολ από tritan που περιλαμβάνονται</li>
        </ul>
        """,
    )

    assert "Λαχταριστό σπιτικό παγωτό" in result.hero_summary
    assert "10 προγράμματα" in result.hero_summary
    assert result.presentation_source_html
    assert normalize_for_match("Εξατομίκευση στο μέγιστο") in normalize_for_match(result.presentation_source_text)
    assert normalize_for_match("Πεντανόστιμο παγωτό με μία μόνο κίνηση") in normalize_for_match(result.presentation_source_text)
    assert result.presentation_source_html.count("<section>") == 4
    assert "https://shop.tefal.gr/cdn/card-1.jpg" in result.presentation_source_html
    assert "https://shop.tefal.gr/cdn/blog-2.jpg" in result.presentation_source_html

