from __future__ import annotations

from product_factory.deterministic_fields import (
    _format_air_conditioner_ionizer,
    derive_name_differentiators,
)
from product_factory.models import SourceProductData, SpecItem, SpecSection, TaxonomyResolution
from product_factory.parser_product_gedsa import GedsaProductParser
from product_factory.source_detection import detect_source, validate_url_scope

GEDSA_URL = "https://www.gedsa.gr/dht26-12ivi-dht26-12ivo/"


def test_gedsa_url_is_supported_product_scope() -> None:
    assert detect_source(GEDSA_URL) == "gedsa"
    assert validate_url_scope(GEDSA_URL) == ("gedsa", True, "gedsa_product_path")


def test_gedsa_parser_extracts_gallery_specs_and_energy_label() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.gedsa.gr/dht26-12ivi-dht26-12ivo/">
        <meta property="og:title" content="DHT26-12IVi - DHT26-12IVo - Γ.Ε. ΔΗΜΗΤΡΙΟΥ Α.Ε.Ε">
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Article",
         "name":"DHT26-12IVi - DHT26-12IVo - Γ.Ε. ΔΗΜΗΤΡΙΟΥ Α.Ε.Ε",
         "description":"Η σειρά κλιματιστικών Dai-Ichi είναι εναρμονισμένη με την οδηγία Eco Design."}
        </script>
      </head>
      <body>
        <h2 class="elementor-heading-title">DHT26-12IVi / DHT26-12IVo</h2>
        <h2 class="elementor-heading-title">ΚΛΙΜΑΤΙΣΤΙΚΟ DAI-ICHI</h2>
        <div class="elementor-widget-gallery">
          <a href="https://www.gedsa.gr/wp-content/uploads/2024/10/DHT24_front_closed.png"></a>
          <a href="https://www.gedsa.gr/wp-content/uploads/2024/10/DHT24_front_open.png"></a>
          <a href="https://www.gedsa.gr/wp-content/uploads/2024/10/DHT24_left_closed.png"></a>
          <a href="https://www.gedsa.gr/wp-content/uploads/2024/10/DHT24_left_open.png"></a>
          <a href="https://www.gedsa.gr/wp-content/uploads/2024/10/DHT24_right_closed.png"></a>
          <a href="https://www.gedsa.gr/wp-content/uploads/2024/10/DHT24_right_open.png"></a>
        </div>
        <div class="e-con-inner">
          <div class="e-con-full">
            <h4>Απόδοση Ψύξης</h4>
            <h4>Απόδοση Ψύξης</h4>
            <h4>SEER</h4>
            <h4>Ενεργειακή Κλάση Ψύξης</h4>
            <h4>WI-FI</h4>
            <h4>ΛΕΙΤΟΥΡΓΙΑ INVERTER</h4>
          </div>
          <div class="e-con-full">
            <h4>3.400 W</h4>
            <h4>11.601 BTU</h4>
            <h4>6.1 W/W</h4>
            <h4>A++</h4>
            <h4>ΝΑΙ</h4>
            <h4>ΝΑΙ</h4>
          </div>
        </div>
        <div class="e-con-inner">
          <div class="e-con-full"><h4>Διαστάσεις Προϊόντος (Μ x Υ x Β) mm</h4></div>
          <div class="e-con-full"><h4>Εσωτερική</h4><h4>Εξωτερική</h4></div>
          <div class="e-con-full"><h4>777×250×201 mm</h4><h4>712×459×276 mm</h4></div>
        </div>
        <div class="elementor-image-box-wrapper">
          <h3 class="elementor-image-box-title">Wi-Fi</h3>
          <p class="elementor-image-box-description">Έλεγχος λειτουργίας από απόσταση.</p>
          <img src="/wp-content/uploads/2026/05/WiFi.png">
        </div>
        <div class="e-parent">
          <h3>Ενεργειακή Ετικέτα</h3>
          <a href="https://www.gedsa.gr/wp-content/uploads/2026/05/Energy-label_DHT26_12IVi_o.pdf"></a>
        </div>
        <div class="e-parent">
          <h3>Δελτίο Προϊόντος</h3>
          <a href="https://www.gedsa.gr/wp-content/uploads/2026/05/Product-fiche_DHT26_12IVi_o.pdf"></a>
        </div>
      </body>
    </html>
    """

    parsed = GedsaProductParser().parse(html, GEDSA_URL)
    source = parsed.source
    specs = {item.label: item.value for item in source.spec_sections[0].items}

    assert source.source_name == "gedsa"
    assert source.brand == "Dai-Ichi"
    assert source.mpn == "DHT26-12IVi/DHT26-12IVo"
    assert source.name == "Dai-Ichi DHT26-12IVi/DHT26-12IVo Κλιματιστικό Inverter 12000 BTU"
    assert source.breadcrumbs[-1] == "Τοίχου"
    assert len(source.gallery_images) == 6
    assert specs["Ψυκτική Απόδοση ( W )"] == "3.400 W"
    assert specs["Ψυκτική Απόδοση ( Btu/h )"] == "11.601 BTU"
    assert specs["Ονομαστική Απόδοση (Btu/h)"] == "12000 BTU"
    assert specs["Βαθμός Εποχιακής Απόδοσης Ψύξης - SEER"] == "6.1 W/W"
    assert specs["Ενεργειακή Κλάση Ψύξης"] == "A++"
    assert specs["Wifi"] == "Υποστηρίζεται"
    assert specs["Τεχνολογία Κλιματιστικού"] == "Inverter"
    assert specs["Πλάτος Εσωτερικής Μονάδας ( mm )"] == "777"
    assert specs["Ύψος Εξωτερικής Μονάδας ( mm )"] == "459"
    assert source.energy_label_asset_url.endswith("Energy-label_DHT26_12IVi_o.pdf")
    assert source.product_sheet_asset_url.endswith("Product-fiche_DHT26_12IVi_o.pdf")
    assert "Wi-Fi" in source.presentation_source_text


def test_gedsa_wifi_support_maps_to_named_title_differentiator() -> None:
    source = SourceProductData(
        source_name="gedsa",
        name="Dai-Ichi DHT26-12IVi/DHT26-12IVo Κλιματιστικό Inverter 12000 BTU",
        key_specs=[
            SpecItem("Wifi", "Υποστηρίζεται"),
            SpecItem("Ονομαστική Απόδοση (Btu/h)", "12000 BTU"),
            SpecItem("Ενεργειακή Κλάση Ψύξης", "A++"),
        ],
        spec_sections=[
            SpecSection(
                section="Τεχνικά Χαρακτηριστικά",
                items=[
                    SpecItem("Wifi", "Υποστηρίζεται"),
                    SpecItem("Ονομαστική Απόδοση (Btu/h)", "12000 BTU"),
                    SpecItem("Ενεργειακή Κλάση Ψύξης", "A++"),
                ],
            )
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΚΛΙΜΑΤΙΣΜΟΣ ΘΕΡΜΑΝΣΗ",
        leaf_category="Κλιματιστικά",
        sub_category="Τοίχου",
    )

    differentiators = derive_name_differentiators(
        source,
        "Κλιματιστικό",
        taxonomy,
        "Dai-Ichi",
        "DHT26-12IVi/DHT26-12IVo",
    )

    assert "Υποστηρίζεται" not in differentiators
    assert "Wi-Fi" in differentiators


def test_air_conditioner_ionizer_does_not_match_inverter_support() -> None:
    source = SourceProductData(
        source_name="gedsa",
        name="Dai-Ichi DHT26-12IVi/DHT26-12IVo Κλιματιστικό Inverter 12000 BTU",
    )
    spec_lookup = {
        "λειτουργια inverter": "Υποστηρίζεται",
        "wifi": "Υποστηρίζεται",
    }

    assert _format_air_conditioner_ionizer(spec_lookup, source) == ""
