from __future__ import annotations

from pathlib import Path

import pytest

from product_factory.models import (
    CLIInput,
    FetchResult,
    GalleryImage,
    ParsedProduct,
    SchemaMatchResult,
    SourceProductData,
    SpecItem,
    SpecSection,
    TaxonomyResolution,
)
from product_factory.html_builders import extract_presentation_blocks
from product_factory.prepare_provider_resolution import PrepareProviderResolutionResult
from product_factory.prepare_result_assembly import PrepareResultAssemblyResult
from product_factory.prepare_scrape_persistence import (
    PrepareScrapePersistenceInput,
    PrepareScrapePersistenceResult,
)
from product_factory.prepare_stage import execute_prepare_stage
from product_factory.prepare_taxonomy_enrichment import PrepareTaxonomyEnrichmentResult
from product_factory.source_capture_client import SourceCaptureSyncResult
from product_factory.source_acquisition_stage import execute_source_acquisition_stage
from product_factory.parser_product_bestprice import BestPriceProductParser
from product_factory.parser_product_dreamelectric import DreamelectricProductParser
from product_factory.parser_product_kotsovolos import KotsovolosProductParser
from product_factory.parser_product_marketquest import MarketQuestProductParser
from product_factory.providers import (
    BestPriceProvider,
    KotsovolosProvider,
    ProviderInputIdentity,
    ProviderRegistry,
    bootstrap_runtime_provider_registry,
    source_to_provider_id,
)
from product_factory.providers.models import (
    ProviderCapability,
    ProviderDefinition,
    ProviderKind,
    ProviderResult,
    ProviderSnapshot,
    ProviderSnapshotKind,
)
from product_factory.providers.manufacturer_tefal_provider import (
    ManufacturerTefalProvider,
)
from product_factory.providers.skroutz_provider import SkroutzProvider
from product_factory.providers.skroutz_fetcher import (
    SkroutzFetchResult,
    SkroutzFetchStatus,
)

SAMPLE_MODEL = "143109"
SAMPLE_URL = "https://www.skroutz.gr/s/61054853/lg-icheio-dxl7t-mayro.html"
BESTPRICE_MODEL = "143667"
BESTPRICE_URL = "https://www.bestprice.gr/item/2163977668/tcl-sqd-mini-led-65c8l-smart-tileorasi-65-4k-uhd-mini-led-hdr.html"
KOTSOVOLOS_MODEL = "412917"
KOTSOVOLOS_URL = "https://www.kotsovolos.gr/air-condition-heaters/air-condition/7000-to-15000-btu/245318-a-c-in18btu-inventor-ar5vi-18wfi-aria"
MANUFACTURER_MODEL = "344709"
MANUFACTURER_URL = "https://shop.tefal.gr/products/dolci-%CF%80%CE%B1%CE%B3%CF%89%CF%84%CE%BF%CE%BC%CE%B7%CF%87%CE%B1%CE%BD%CE%AE-ig602a"


def _build_manufacturer_enrichment_stub() -> dict[str, object]:
    return {
        "applied": False,
        "provider": "",
        "providers_considered": [],
        "matched_providers": [],
        "documents": [],
        "documents_discovered": 0,
        "documents_parsed": 0,
        "warnings": [],
        "section_count": 0,
        "field_count": 0,
        "hero_summary_applied": False,
        "presentation_applied": False,
        "presentation_block_count": 0,
        "fallback_reason": "test_stub",
    }


def _build_taxonomy_enrichment_result(
    taxonomy: TaxonomyResolution | None = None,
    *,
    taxonomy_candidates: list[dict[str, object]] | None = None,
    manufacturer_enrichment: dict[str, object] | None = None,
) -> PrepareTaxonomyEnrichmentResult:
    return PrepareTaxonomyEnrichmentResult(
        taxonomy=taxonomy
        or TaxonomyResolution(
            parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
            leaf_category="Συσκευές Κουζίνας",
            sub_category="Βραστήρες",
        ),
        taxonomy_candidates=taxonomy_candidates or [],
        manufacturer_enrichment=manufacturer_enrichment
        or _build_manufacturer_enrichment_stub(),
    )


class DummyResolver:
    def resolve(self, **_kwargs):
        return (
            TaxonomyResolution(
                parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
                leaf_category="Συσκευές Κουζίνας",
                sub_category="Βραστήρες",
            ),
            [],
        )


class DummyFetcher:
    def download_gallery_images(self, **_kwargs):
        return [], [], []

    def download_besco_images(self, **_kwargs):
        return [], [], []


def build_provider(skroutz_fixtures_root: Path) -> SkroutzProvider:
    return SkroutzProvider(
        fixture_html_by_url={
            SAMPLE_URL: skroutz_fixtures_root
            / "taxonomy_cases"
            / f"{SAMPLE_MODEL}.html"
        }
    )


def build_manufacturer_provider(
    manufacturer_tefal_provider_fixtures_root: Path,
) -> ManufacturerTefalProvider:
    return ManufacturerTefalProvider(
        fixture_html_by_url={
            MANUFACTURER_URL: manufacturer_tefal_provider_fixtures_root
            / MANUFACTURER_MODEL
            / "product.html"
        }
    )


def build_prepare_provider_resolution_result(
    *,
    source: str,
    url: str,
    parsed: ParsedProduct,
    fetch_method: str,
    fallback_used: bool = False,
) -> PrepareProviderResolutionResult:
    return PrepareProviderResolutionResult(
        source=source,
        provider_id=source,
        fetch=FetchResult(
            url=url,
            final_url=url,
            html="<html></html>",
            status_code=200,
            method=fetch_method,
            fallback_used=fallback_used,
        ),
        parsed=parsed,
    )


def test_execute_source_acquisition_stage_returns_provider_identity_and_snapshot_provenance(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / SAMPLE_MODEL
    parsed = ParsedProduct(
        source=SourceProductData(
            source_name="skroutz",
            page_type="product",
            url=SAMPLE_URL,
            canonical_url=SAMPLE_URL,
            product_code=SAMPLE_MODEL,
            brand="Estia",
            mpn="06-24567",
            name="Estia 06-24567",
            gallery_images=[
                GalleryImage(url="https://cdn.example/1.jpg", alt="main", position=1)
            ],
        )
    )
    gallery_downloads = [
        GalleryImage(
            url="https://cdn.example/1.jpg",
            alt="main",
            position=1,
            local_filename=f"{SAMPLE_MODEL}-1.jpg",
            local_path=str(model_dir / "gallery" / f"{SAMPLE_MODEL}-1.jpg"),
            downloaded=True,
        )
    ]

    class GalleryFetcher:
        def __init__(self) -> None:
            self.gallery_calls: list[dict[str, object]] = []

        def download_gallery_images(self, **kwargs):
            self.gallery_calls.append(kwargs)
            return (
                gallery_downloads,
                [],
                [str(model_dir / "gallery" / f"{SAMPLE_MODEL}-1.jpg")],
            )

    fetcher = GalleryFetcher()

    result = execute_source_acquisition_stage(
        model=SAMPLE_MODEL,
        url=SAMPLE_URL,
        photos=1,
        model_dir=model_dir,
        validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: build_prepare_provider_resolution_result(
            source="skroutz",
            url=cli_arg.url,
            parsed=parsed,
            fetch_method="fixture",
        ),
    )

    assert not hasattr(result, "cli")
    assert result.source == "skroutz"
    assert result.provider_id == "skroutz"
    assert result.downloaded_gallery == gallery_downloads
    assert result.parsed.source.gallery_images == gallery_downloads
    assert result.snapshot_provenance["detected_source"] == "skroutz"
    assert result.snapshot_provenance["provider_id"] == "skroutz"
    assert result.snapshot_provenance["fetch_method"] == "fixture"
    assert result.snapshot_provenance["gallery_requested_photos"] == 1
    assert result.snapshot_provenance["gallery_downloaded_count"] == 1
    assert len(fetcher.gallery_calls) == 1


def test_bootstrap_runtime_provider_registry_registers_active_providers() -> None:
    registry = bootstrap_runtime_provider_registry(
        fetcher=object(),
        electronet_parser=object(),
        skroutz_parser=object(),
        manufacturer_parser=object(),
    )

    assert registry.ids() == (
        "apothema",
        "bestprice",
        "dreamelectric",
        "electronet",
        "estia",
        "kotsovolos",
        "marketquest",
        "skroutz",
    )
    assert [definition.provider_id for definition in registry.definitions()] == [
        "apothema",
        "bestprice",
        "dreamelectric",
        "electronet",
        "estia",
        "kotsovolos",
        "marketquest",
        "skroutz",
    ]


def test_source_to_provider_id_maps_supported_sources() -> None:
    assert source_to_provider_id("apothema") == "apothema"
    assert source_to_provider_id("bestprice") == "bestprice"
    assert source_to_provider_id("dreamelectric") == "dreamelectric"
    assert source_to_provider_id("electronet") == "electronet"
    assert source_to_provider_id("estia") == "estia"
    assert source_to_provider_id("kotsovolos") == "kotsovolos"
    assert source_to_provider_id("marketquest") == "marketquest"
    assert source_to_provider_id("skroutz") == "skroutz"
    assert source_to_provider_id("manufacturer_tefal") is None
    assert source_to_provider_id("manufacturer_bosch") is None
    assert source_to_provider_id("unsupported_source") is None


def test_dreamelectric_parser_normalizes_specs_and_gallery() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.dreamelectric.gr/p,23766,example.html">
        <meta name="description" content="Pitsos Ioli Premium PSI12AW32 / PSO12AW32 κλιματιστικό 12000 BTU.">
      </head>
      <body>
        <nav class="breadcrumb">
          <a>Αρχική</a>
          <a>ΚΛΙΜΑΤΙΣΜΟΣ & ΘΕΡΜΑΝΣΗ</a>
          <a>Κλιματιστικά</a>
          <a>Οικιακά Κλιματιστικά (Split)</a>
        </nav>
        <div id="product-product">
          <div class="product-info">
            <div class="product-left">
              <div class="main-image">
                <img data-largeimg="/image/cache/catalog/PSI12AW32%201-1000x1000w.jpg" alt="Pitsos PSI12AW32">
              </div>
              <div class="additional-images">
                <img data-largeimg="/image/cache/catalog/PSI12AW32%202-1000x1000w.jpg" alt="Pitsos PSI12AW32">
                <img data-largeimg="/image/cache/catalog/PSI12AW32%203-1000x1000w.jpg" alt="Pitsos PSI12AW32">
                <img data-largeimg="/image/cache/catalog/PSI12AW32%204-1000x1000h.jpg" alt="Pitsos PSI12AW32">
              </div>
            </div>
            <div class="product-right">
              <h1>Pitsos Ioli Premium PSI12AW32 / PSO12AW32 Οικιακό Κλιματιστικό Split 12000 BTU</h1>
              <div class="product-price">390.00€</div>
              <span>Κωδικός: 624941</span>
              <a href="/brand/pitsos">Pitsos</a>
            </div>
          </div>
          <div class="block-attributes">
            <table>
              <tr><td>Τεχνικά Χαρακτηριστικά</td></tr>
              <tr><td>SCOP / Βαθμός Απόδοσης Θέρμανσης</td><td>5.1</td></tr>
              <tr><td>SEER / Βαθμός Απόδοσης Ψύξης</td><td>6.1</td></tr>
              <tr><td>Εγκατεστημένο Wi-Fi</td><td>√</td></tr>
              <tr><td>Ονομαστική Απόδοση (Btu/h)</td><td>12000</td></tr>
              <tr><td>Ψύξης Ενεργειακή Κλάση</td><td>A2</td></tr>
            </table>
          </div>
        </div>
      </body>
    </html>
    """

    parsed = DreamelectricProductParser().parse(
        html, "https://www.dreamelectric.gr/p,23766,example.html"
    )

    assert parsed.critical_missing == []
    assert parsed.source.product_code == "624941"
    assert parsed.source.brand == "Pitsos"
    assert parsed.source.mpn == "PSI12AW32"
    assert parsed.source.price_value == 390.0
    assert len(parsed.source.gallery_images) == 4
    labels = [item.label for item in parsed.source.spec_sections[0].items]
    assert "Ψύξης Ενεργειακή Κλάση" in labels
    assert "Ενεργειακή Κλάση Ψύξης" in labels


def test_bestprice_parser_normalizes_jsonld_product() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.bestprice.gr/item/2163977668/tcl-sqd-mini-led-65c8l-smart-tileorasi-65-4k-uhd-mini-led-hdr.html">
        <meta name="description" content="Περιγραφή προϊόντος">
        <meta property="og:image" content="https://cdn.example/product.jpg">
        <script type="application/ld+json">
          {"@context":"http://schema.org","@type":"BreadcrumbList","itemListElement":[
            {"@type":"ListItem","position":1,"item":{"@id":"/cat/6989/technology.html","name":"Τεχνολογία"}},
            {"@type":"ListItem","position":2,"item":{"@id":"/cat/3048/thleoraseis.html","name":"Τηλεοράσεις"}}
          ]}
        </script>
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"Product",
           "name":"TCL SQD-Mini LED 65C8L Smart Τηλεόραση 65\\\" 4K UHD Mini LED HDR (2026)",
           "image":["https://cdn.example/product.jpg"],
           "offers":{"@type":"AggregateOffer","lowPrice":"1799.00","priceCurrency":"EUR"},
           "sku":2163977668,
           "url":"https://www.bestprice.gr/item/2163977668/tcl-sqd-mini-led-65c8l-smart-tileorasi-65-4k-uhd-mini-led-hdr.html",
           "brand":{"@type":"Brand","name":"TCL"},
           "additionalProperty":[
             {"@type":"PropertyValue","name":"Μέγεθος Οθόνης","value":"65\\\""},
             {"@type":"PropertyValue","name":"Panel","value":"Mini LED"},
             {"@type":"PropertyValue","name":"Ανάλυση","value":"4K Ultra HD"}
           ]}
        </script>
      </head>
      <body>
        <h1 class="item-title">fallback</h1>
        <ul class="item-header__specs-list">
          <li><div>Αφύγρανση: Ναι</div></li>
        </ul>
        <section id="item-specs">
          <dl><dt>Wifi Ready</dt><dd>Ναι</dd></dl>
        </section>
        <div class="item-description">Αυτή η TCL έχει Mini LED.</div>
      </body>
    </html>
    """

    parsed = BestPriceProductParser().parse(html, BESTPRICE_URL)

    assert parsed.source.source_name == "bestprice"
    assert parsed.source.product_code == "2163977668"
    assert parsed.source.brand == "TCL"
    assert parsed.source.name.startswith("TCL SQD-Mini LED 65C8L")
    assert parsed.source.taxonomy_rule_id == "television:size_bucket"
    assert parsed.source.taxonomy_tv_inches == 65
    assert parsed.source.gallery_images[0].url == "https://cdn.example/product.jpg"
    assert [item.label for item in parsed.source.spec_sections[0].items[:2]] == [
        "Κατασκευαστής",
        "Μέγεθος Οθόνης",
    ]
    assert {item.label: item.value for item in parsed.source.spec_sections[0].items}[
        "Αφύγρανση"
    ] == "Ναι"
    assert {item.label: item.value for item in parsed.source.spec_sections[0].items}[
        "Wifi Ready"
    ] == "Ναι"
    assert parsed.critical_missing == []


def test_bestprice_parser_extracts_content_sections_and_visible_specs() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.bestprice.gr/item/2163977668/tcl-sqd-mini-led-65c8l-smart-tileorasi-65-4k-uhd-mini-led-hdr.html">
        <script type="application/ld+json">
          {"@context":"http://schema.org","@type":"BreadcrumbList","itemListElement":[
            {"@type":"ListItem","position":1,"item":{"@id":"/cat/3048/thleoraseis.html","name":"Τηλεοράσεις"}}
          ]}
        </script>
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"Product",
           "name":"TCL 65C8L Smart Τηλεόραση 65\\\" 4K UHD",
           "image":["https://cdn.example/product.jpg"],
           "brand":{"@type":"Brand","name":"TCL"},
           "additionalProperty":[{"@type":"PropertyValue","name":"Panel","value":"Mini LED"}]}
        </script>
      </head>
      <body>
        <div class="item-insights__summary">
          <p>Η TCL 65C8L συνδυάζει Mini LED εικόνα και Wi-Fi λειτουργίες.</p>
        </div>
        <section id="item-content">
          <div class="content-block">
            <div class="content-block__image">
              <img src="/P/bpimg/content1.webp" alt="Mini LED">
            </div>
            <div class="content-block__content">
              <h3 class="content-block__header">Mini LED εικόνα</h3>
              <div class="content-block__body">
                <p>Η τεχνολογία Mini LED προσφέρει υψηλή φωτεινότητα και καθαρή αντίθεση.</p>
              </div>
            </div>
          </div>
          <div class="content-block">
            <div class="content-block__content">
              <h3 class="content-block__header">Έξυπνες λειτουργίες</h3>
              <div class="content-block__body">
                <p>Η τηλεόραση υποστηρίζει Wi-Fi και εφαρμογές streaming.</p>
              </div>
            </div>
          </div>
        </section>
        <section id="item-specs">
          <dl><dt>Wifi</dt><dd>Ναι</dd></dl>
          <dl><dt>HDR</dt><dd>Dolby Vision</dd></dl>
        </section>
      </body>
    </html>
    """

    parsed = BestPriceProductParser().parse(html, BESTPRICE_URL)

    blocks = extract_presentation_blocks(
        parsed.source.presentation_source_html,
        parsed.source.presentation_source_text,
        base_url=parsed.source.canonical_url,
    )
    spec_values = {
        item.label: item.value
        for section in parsed.source.spec_sections
        for item in section.items
    }

    assert parsed.source.hero_summary.startswith("Η TCL 65C8L")
    assert [block["title"] for block in blocks] == [
        "Mini LED εικόνα",
        "Έξυπνες λειτουργίες",
    ]
    assert blocks[0]["image_url"] == "https://www.bestprice.gr/P/bpimg/content1.webp"
    assert "Wi-Fi και εφαρμογές streaming" in parsed.source.presentation_source_text
    assert spec_values["Wifi"] == "Ναι"
    assert spec_values["HDR"] == "Dolby Vision"


def test_bestprice_parser_reads_real_gallery_links_before_jsonld_image() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.bestprice.gr/item/2163977668/tcl-sqd-mini-led-65c8l-smart-tileorasi-65-4k-uhd-mini-led-hdr.html">
        <script type="application/ld+json">
          {"@context":"http://schema.org","@type":"BreadcrumbList","itemListElement":[
            {"@type":"ListItem","position":1,"item":{"@id":"/cat/3048/thleoraseis.html","name":"Τηλεοράσεις"}}
          ]}
        </script>
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"Product",
           "name":"TCL 65C8L Smart Τηλεόραση 65\\\" 4K UHD",
           "image":["https://cdn.example/product.jpg"],
           "brand":{"@type":"Brand","name":"TCL"},
           "additionalProperty":[{"@type":"PropertyValue","name":"Panel","value":"Mini LED"}]}
        </script>
      </head>
      <body><div class="item-description">Περιγραφή</div></body>
    </html>
    """

    html = html.replace(
        "</body>",
        """
        <div id="item-image-gallery">
          <ol>
            <li><a href="https://bbpcdn.pstatic.gr/bpimg37/aGsjb/1WmIpD/tcl-65c8l.webp"></a></li>
            <li><a href="https://bbpcdn.pstatic.gr/P/bp_img_sets/7phDOo/tcl-65c8l.webp"></a></li>
            <li><a href="https://bbpcdn.pstatic.gr/P/bp_img_sets/7phDOp/tcl-65c8l.webp"></a></li>
          </ol>
        </div>
        </body>
        """,
    )
    parsed = BestPriceProductParser().parse(html, BESTPRICE_URL)

    assert [image.position for image in parsed.source.gallery_images] == [1, 2, 3]
    assert [image.url for image in parsed.source.gallery_images] == [
        "https://bbpcdn.pstatic.gr/bpimg37/aGsjb/1WmIpD/tcl-65c8l.webp",
        "https://bbpcdn.pstatic.gr/P/bp_img_sets/7phDOo/tcl-65c8l.webp",
        "https://bbpcdn.pstatic.gr/P/bp_img_sets/7phDOp/tcl-65c8l.webp",
    ]


def test_bestprice_provider_normalize_returns_provider_result(tmp_path: Path) -> None:
    fixture = tmp_path / "bestprice.html"
    fixture.write_text(
        """
        <html>
          <head>
            <link rel="canonical" href="https://www.bestprice.gr/item/2163977668/tcl-sqd-mini-led-65c8l-smart-tileorasi-65-4k-uhd-mini-led-hdr.html">
            <script type="application/ld+json">
              {"@context":"http://schema.org","@type":"BreadcrumbList","itemListElement":[
                {"@type":"ListItem","position":1,"item":{"@id":"/cat/3048/thleoraseis.html","name":"Τηλεοράσεις"}}
              ]}
            </script>
            <script type="application/ld+json">
              {"@context":"https://schema.org","@type":"Product",
               "name":"TCL 65C8L Smart Τηλεόραση 65\\\" 4K UHD",
               "image":["https://cdn.example/product.jpg"],
               "brand":{"@type":"Brand","name":"TCL"},
               "additionalProperty":[{"@type":"PropertyValue","name":"Panel","value":"Mini LED"}]}
            </script>
          </head>
          <body><div class="item-description">Περιγραφή</div></body>
        </html>
        """,
        encoding="utf-8",
    )
    provider = BestPriceProvider(fixture_html_by_url={BESTPRICE_URL: fixture})
    identity = ProviderInputIdentity(model=BESTPRICE_MODEL, url=BESTPRICE_URL)

    snapshot = provider.fetch_snapshot(identity)
    result = provider.normalize(snapshot, identity)

    assert result.provider.provider_id == "bestprice"
    assert result.product.source_name == "bestprice"
    assert result.product.page_type == "product"
    assert result.metadata["fetch_method"] == "fixture"


def test_marketquest_parser_extracts_info_tab_specs_and_gallery() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.marketquest.gr/product/1336/bra-tigani-grill-signature-me-rabdwseis-apo-anoxeidwto.html">
        <title>Bra Τηγάνι Grill Signature με ραβδώσεις από ανοξείδωτο ατσάλι χωρίς αντικολλητική επίστρωση 28cm | Τηγάνια | Market Quest</title>
      </head>
      <body>
        <nav class="breadcrumb">
          <a href="/main.php">Αρχική</a>
          <a href="/category/1/oikiakes-syskeyes.html">Οικιακές συσκευές</a>
          <a href="/category/1_123/oikiakes-syskeyes-skeyi-kai-ergaleia-mageirikis.html">Σκεύη και Εργαλεία Μαγειρικής</a>
          <a href="/category/1_123_147/skeyi-kai-ergaleia-mageirikis-tigania.html">Τηγάνια</a>
        </nav>
        <div class="product-slick product_images">
          <a class="lightbox mainimg" href="images/products/2026/04/GRILL.png">
            <img src="images/products/2026/04/GRILL.png" alt="Bra Τηγάνι Grill Signature">
          </a>
        </div>
        <div class="product-right">
          <h2>Bra Τηγάνι Grill Signature με ραβδώσεις από ανοξείδωτο ατσάλι χωρίς αντικολλητική επίστρωση 28cm</h2>
          <h5>BRA</h5>
          <h5>Κωδικός marketquest: <span id="products_model" itemprop="model">6730101778</span><br>
          MPN: <span id="products_mpn" itemprop="mpn">A771301 SIGNATURE RIBBED GRILL 28cm</span></h5>
        </div>
        <div id="products_description">Το τηγάνι Signature Grill της Bra είναι κατασκευασμένο από ανοξείδωτο ατσάλι 18/10.</div>
        <div id="products_perigrafi-tabcontent">
          <ul>
            <li>Κατασκευή από ανοξείδωτο ατσάλι 18/10</li>
            <li>Ραβδωτή επιφάνεια ψησίματος χωρίς αντικολλητική επίστρωση</li>
            <li>Βάση Full Induction μεγάλης διαμέτρου</li>
            <li>Κατάλληλο για όλους τους τύπους εστιών, συμπεριλαμβανομένων των επαγωγικών</li>
            <li>Κατάλληλο για χρήση στον φούρνο έως 220°C</li>
            <li>Κατάλληλο για πλύσιμο στο πλυντήριο πιάτων</li>
          </ul>
        </div>
      </body>
    </html>
    """

    parsed = MarketQuestProductParser().parse(
        html,
        "https://www.marketquest.gr/product/1336/bra-tigani-grill-signature-me-rabdwseis-apo-anoxeidwto.html",
    )
    specs = {item.label: item.value for item in parsed.source.spec_sections[0].items}

    assert parsed.source.source_name == "marketquest"
    assert parsed.source.product_code == "6730101778"
    assert parsed.source.brand == "BRA"
    assert parsed.source.mpn == "A771301"
    assert parsed.source.breadcrumbs[-1] == "Τηγάνια"
    assert parsed.source.gallery_images[0].url == (
        "https://www.marketquest.gr/images/products/2026/04/GRILL.png"
    )
    assert specs["Διάμετρος Σκεύους σε Εκατοστά."] == "28cm"
    assert specs["Τύπος Σκεύους"] == "Τηγάνι Grill"
    assert specs["Υλικό Σκεύους"] == "Ανοξείδωτο Ατσάλι"
    assert specs["Εσωτερική Επίστρωση"] == "Χωρίς Αντικολλητική Επίστρωση"
    assert specs["Κατάλληλο για Φούρνο"] == "Έως 220°C"
    assert parsed.critical_missing == []


def test_kotsovolos_parser_normalizes_visible_product_characteristics() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.kotsovolos.gr/air-condition-heaters/air-condition/7000-to-15000-btu/245318-a-c-in18btu-inventor-ar5vi-18wfi-aria">
        <meta property="og:image" content="https://assets.kotsovolos.gr/product/245318-b.jpg">
      </head>
      <body>
        <h1>Inventor AR5VI-18WFI Aria 18.000 BTU/h Κλιματιστικό Inverter</h1>
        <div class="product-charactristics-row">Ονομαστική απόδοση (Btu/h)</div>
        <div class="product-charactristics-row">18.000</div>
        <div class="product-charactristics-row">Ψυκτική (Btu/h)</div>
        <div class="product-charactristics-row">18000 (11.570-20.130)</div>
        <div class="product-charactristics-row">Βαθμός ενεργειακής απόδοσης (SEER)</div>
        <div class="product-charactristics-row">7.0</div>
        <div class="product-charactristics-row">Βαθμός θερμικής απόδοσης (SCOP)</div>
        <div class="product-charactristics-row">5.1</div>
        <div class="product-charactristics-row">Συνδεσιμότητα</div>
        <div class="product-charactristics-row">Wi-Fi Standard</div>
      </body>
    </html>
    """

    parsed = KotsovolosProductParser().parse(html, KOTSOVOLOS_URL)

    assert parsed.source.source_name == "kotsovolos"
    assert parsed.source.product_code == "245318"
    assert parsed.source.brand == "Inventor"
    assert parsed.source.mpn == "AR5VI-18WFI"
    assert parsed.source.name.startswith("Inventor AR5VI-18WFI")
    assert parsed.source.gallery_images[0].url.endswith("245318-b.jpg")
    specs = {item.label: item.value for item in parsed.source.spec_sections[0].items}
    assert specs["Ονομαστική απόδοση (Btu/h)"] == "18.000"
    assert specs["Βαθμός ενεργειακής απόδοσης (SEER)"] == "7.0"
    assert specs["Συνδεσιμότητα"] == "Wi-Fi Standard"
    assert parsed.critical_missing == []


def test_kotsovolos_provider_normalize_returns_provider_result(tmp_path: Path) -> None:
    fixture = tmp_path / "kotsovolos.html"
    fixture.write_text(
        """
        <html>
          <head>
            <link rel="canonical" href="https://www.kotsovolos.gr/air-condition-heaters/air-condition/7000-to-15000-btu/245318-a-c-in18btu-inventor-ar5vi-18wfi-aria">
            <meta property="og:image" content="https://assets.kotsovolos.gr/product/245318-b.jpg">
          </head>
          <body>
            <h1>Inventor AR5VI-18WFI Aria 18.000 BTU/h Κλιματιστικό Inverter</h1>
            <div class="product-charactristics-row">Ψυκτική (Btu/h)</div>
            <div class="product-charactristics-row">18000 (11.570-20.130)</div>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    provider = KotsovolosProvider(fixture_html_by_url={KOTSOVOLOS_URL: fixture})
    identity = ProviderInputIdentity(model=KOTSOVOLOS_MODEL, url=KOTSOVOLOS_URL)

    snapshot = provider.fetch_snapshot(identity)
    result = provider.normalize(snapshot, identity)

    assert result.provider.provider_id == "kotsovolos"
    assert result.product.source_name == "kotsovolos"
    assert result.product.page_type == "product"
    assert result.metadata["fetch_method"] == "fixture"


def test_kotsovolos_parser_extracts_product_gallery_images_without_og_image() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.kotsovolos.gr/air-condition-heaters/air-condition/7000-to-15000-btu/245318-a-c-in18btu-inventor-ar5vi-18wfi-aria">
      </head>
      <body>
        <h1>Inventor AR5VI-18WFI Aria 18.000 BTU/h Κλιματιστικό Inverter</h1>
        <img src="https://assets.kotsovolos.gr/assets/images/videoPlacement.png">
        <img src="https://assets.kotsovolos.gr/product/245318-b.jpg">
        <img src="https://assets.kotsovolos.gr/product/245318-1-b.jpg">
        <img src="https://assets.kotsovolos.gr/product/245318-s.jpg">
        <img src="https://assets.kotsovolos.gr/product/111111-b.jpg">
        <span>Κλιματιστικό Aria AR5 με Ενεργειακή Κλάση Α+++, ιονιστή, φίλτρο αποστείρωσης hepa, φίλτρο τριπλής δράσης & λειτουργία follow me</span>
        <div class="product-charactristics-row">Ψυκτική (Btu/h)</div>
        <div class="product-charactristics-row">18000 (11.570-20.130)</div>
        <div class="product-charactristics-row">Θερμική Απόδοση (BΤU/h)</div>
        <div class="product-charactristics-row">19000</div>
        <div class="product-charactristics-row">Ενεργειακή Κλάση Ψύξης</div>
        <div class="product-charactristics-row">Α++</div>
        <div class="product-charactristics-row">Συνδεσιμότητα (WiFi)</div>
        <div class="product-charactristics-row">WiFi</div>
      </body>
    </html>
    """

    parsed = KotsovolosProductParser().parse(html, KOTSOVOLOS_URL)

    assert [image.url.rsplit("/", 1)[-1] for image in parsed.source.gallery_images] == [
        "245318-b.jpg",
        "245318-1-b.jpg",
    ]
    assert parsed.source.hero_summary.startswith("Κλιματιστικό Aria AR5")
    assert parsed.source.presentation_source_html.count("<section>") >= 3
    assert "Απόδοση 18.000 BTU/h" in parsed.source.presentation_source_html
    assert "https://assets.kotsovolos.gr/product/245318-1-b.jpg" in (
        parsed.source.presentation_source_html
    )


def test_skroutz_provider_fetch_snapshot_reads_fixture_html(
    skroutz_fixtures_root: Path,
) -> None:
    provider = build_provider(skroutz_fixtures_root)
    identity = ProviderInputIdentity(model=SAMPLE_MODEL, url=SAMPLE_URL)

    snapshot = provider.fetch_snapshot(identity)

    assert provider.supports_identity(identity) is True
    assert snapshot.snapshot_kind == ProviderSnapshotKind.HTML
    assert snapshot.requested_url == SAMPLE_URL
    assert snapshot.final_url == SAMPLE_URL
    assert snapshot.status_code == 200
    assert snapshot.metadata["fetch_method"] == "fixture"
    assert str(snapshot.metadata["fixture_path"]).endswith(f"{SAMPLE_MODEL}.html")
    assert "LG" in snapshot.body_text


def test_skroutz_provider_normalize_returns_provider_result(
    skroutz_fixtures_root: Path,
) -> None:
    provider = build_provider(skroutz_fixtures_root)
    identity = ProviderInputIdentity(model=SAMPLE_MODEL, url=SAMPLE_URL)

    snapshot = provider.fetch_snapshot(identity)
    result = provider.normalize(snapshot, identity)

    assert result.provider.provider_id == "skroutz"
    assert result.provider.kind == ProviderKind.VENDOR_SITE
    assert result.snapshot is snapshot
    assert result.product.source_name == "skroutz"
    assert result.product.page_type == "product"
    assert result.product.canonical_url == SAMPLE_URL
    assert result.metadata["fetch_method"] == "fixture"
    assert "name" in result.provenance
    assert "name" in result.field_diagnostics


def test_skroutz_provider_fetch_snapshot_uses_raw_http_fetcher_when_no_fixture_override() -> (
    None
):
    identity = ProviderInputIdentity(model=SAMPLE_MODEL, url=SAMPLE_URL)
    calls = {"fetch": 0}

    class LiveFetcher:
        def fetch(self, url: str) -> SkroutzFetchResult:
            calls["fetch"] += 1
            return SkroutzFetchResult(
                url=url,
                final_url=url,
                html="<html></html>",
                status_code=200,
                method="httpx",
                status=SkroutzFetchStatus.OK,
                headers={"content-type": "text/html"},
            )

    provider = SkroutzProvider(fetcher=LiveFetcher())

    snapshot = provider.fetch_snapshot(identity)

    assert calls == {"fetch": 1}
    assert snapshot.requested_url == SAMPLE_URL
    assert snapshot.final_url == SAMPLE_URL
    assert snapshot.metadata["fetch_method"] == "httpx"
    assert snapshot.metadata["fallback_used"] is False


def test_manufacturer_tefal_provider_fetch_snapshot_reads_fixture_html(
    manufacturer_tefal_provider_fixtures_root: Path,
) -> None:
    provider = build_manufacturer_provider(manufacturer_tefal_provider_fixtures_root)
    identity = ProviderInputIdentity(model=MANUFACTURER_MODEL, url=MANUFACTURER_URL)

    snapshot = provider.fetch_snapshot(identity)

    assert provider.supports_identity(identity) is True
    assert snapshot.snapshot_kind == ProviderSnapshotKind.HTML
    assert snapshot.requested_url == MANUFACTURER_URL
    assert snapshot.final_url == MANUFACTURER_URL
    assert snapshot.status_code == 200
    assert snapshot.metadata["fetch_method"] == "fixture"
    assert str(snapshot.metadata["fixture_path"]).endswith("product.html")
    assert "Tefal Dolci Παγωτομηχανή IG602A" in snapshot.body_text


def test_manufacturer_tefal_provider_normalize_returns_provider_result(
    manufacturer_tefal_provider_fixtures_root: Path,
) -> None:
    provider = build_manufacturer_provider(manufacturer_tefal_provider_fixtures_root)
    identity = ProviderInputIdentity(model=MANUFACTURER_MODEL, url=MANUFACTURER_URL)

    snapshot = provider.fetch_snapshot(identity)
    result = provider.normalize(snapshot, identity)

    assert result.provider.provider_id == "manufacturer_tefal"
    assert result.provider.kind == ProviderKind.MANUFACTURER_SITE
    assert result.snapshot is snapshot
    assert result.product.source_name == "manufacturer_tefal"
    assert result.product.page_type == "product"
    assert result.product.canonical_url == MANUFACTURER_URL
    assert result.product.mpn == "IG602A"
    assert result.metadata["fetch_method"] == "fixture"
    assert "name" in result.provenance
    assert "name" in result.field_diagnostics


def test_execute_prepare_stage_uses_test_injected_skroutz_provider(
    tmp_path: Path, skroutz_fixtures_root: Path
) -> None:
    cli = CLIInput(
        model=SAMPLE_MODEL,
        url=SAMPLE_URL,
        photos=2,
        sections=0,
        skroutz_status=0,
        boxnow=1,
        price="19",
        out=str(tmp_path),
    )
    provider = build_provider(skroutz_fixtures_root)
    identity_calls: list[ProviderInputIdentity] = []

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / SAMPLE_MODEL,
        validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
        fetcher_factory=DummyFetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: (
            identity_calls.append(
                ProviderInputIdentity(model=cli_arg.model, url=cli_arg.url)
            )
            or build_prepare_provider_resolution_result(
                source="skroutz",
                url=cli_arg.url,
                parsed=ParsedProduct(
                    source=provider.normalize(
                        provider.fetch_snapshot(
                            ProviderInputIdentity(model=cli_arg.model, url=cli_arg.url)
                        ),
                        ProviderInputIdentity(model=cli_arg.model, url=cli_arg.url),
                    ).product
                ),
                fetch_method="fixture",
            )
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment_result(),
        assemble_prepare_result_fn=lambda **kwargs: PrepareResultAssemblyResult(
            schema_match=SchemaMatchResult(matched_schema_id="schema-1", score=0.9),
            schema_candidates=[],
            row={"model": kwargs["cli"].model},
            normalized={"input": kwargs["cli"].to_dict()},
            report={
                "source": kwargs["source"],
                "fetch_mode": kwargs["fetch"].method,
                "identity_checks": {"source": kwargs["source"]},
                "warnings": [],
            },
        ),
    )

    assert identity_calls == [ProviderInputIdentity(model=SAMPLE_MODEL, url=SAMPLE_URL)]
    assert result["report"]["source"] == "skroutz"
    assert result["report"]["fetch_mode"] == "fixture"
    assert result["fetch"].method == "fixture"
    assert result["parsed"].source.source_name == "skroutz"
    assert result["source_json_path"].exists()


def test_execute_prepare_stage_reuses_injected_provider_resolution_payload(
    tmp_path: Path,
) -> None:
    cli = CLIInput(
        model="229957",
        url="https://www.electronet.gr/example",
        photos=2,
        sections=0,
        skroutz_status=1,
        boxnow=0,
        price="599",
        out=str(tmp_path),
    )
    parsed = ParsedProduct(
        source=SourceProductData(
            url=cli.url,
            canonical_url=cli.url,
            product_code="235370",
            brand="LG",
            name="LG RHX5009TWB",
        ),
    )
    seam_calls: list[tuple[CLIInput, dict[str, object]]] = []

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("electronet", True, ""),
        fetcher_factory=DummyFetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **kwargs: (
            seam_calls.append((cli_arg, kwargs))
            or build_prepare_provider_resolution_result(
                source="electronet",
                url=cli_arg.url,
                parsed=parsed,
                fetch_method="httpx",
            )
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment_result(
            manufacturer_enrichment={}
        ),
        assemble_prepare_result_fn=lambda **kwargs: PrepareResultAssemblyResult(
            schema_match=SchemaMatchResult(matched_schema_id="schema-1", score=0.9),
            schema_candidates=[],
            row={"model": kwargs["cli"].model},
            normalized={"input": kwargs["cli"].to_dict()},
            report={
                "source": kwargs["source"],
                "fetch_mode": kwargs["fetch"].method,
                "identity_checks": {"source": kwargs["source"]},
                "warnings": [],
            },
        ),
    )

    assert seam_calls
    assert seam_calls[0][0].model == cli.model
    assert seam_calls[0][0].url == cli.url
    assert seam_calls[0][0].photos == cli.photos
    assert seam_calls[0][0].sections == 0
    assert seam_calls[0][0].skroutz_status == 0
    assert seam_calls[0][0].boxnow == 0
    assert seam_calls[0][0].price == 0
    assert seam_calls[0][0].out == str(tmp_path / cli.model)
    assert result["parsed"] is parsed
    assert result["parsed"].warnings == []
    assert result["report"]["source"] == "electronet"
    assert result["report"]["identity_checks"]["source"] == "electronet"


def test_execute_prepare_stage_calls_persistence_seam_once_with_typed_input(
    tmp_path: Path,
) -> None:
    cli = CLIInput(
        model="229957",
        url="https://www.electronet.gr/example",
        photos=2,
        sections=0,
        skroutz_status=1,
        boxnow=0,
        price="599",
        out=str(tmp_path),
    )
    parsed = ParsedProduct(
        source=SourceProductData(
            url=cli.url,
            canonical_url=cli.url,
            product_code="235370",
            brand="LG",
            name="LG RHX5009TWB",
        ),
    )
    persistence_calls: list[PrepareScrapePersistenceInput] = []

    def fake_persist(
        persistence_input: PrepareScrapePersistenceInput,
    ) -> PrepareScrapePersistenceResult:
        persistence_calls.append(persistence_input)
        return PrepareScrapePersistenceResult(
            scrape_dir=persistence_input.scrape_dir,
            raw_html_path=persistence_input.raw_html_path,
            source_json_path=persistence_input.source_json_path,
            normalized_json_path=persistence_input.normalized_json_path,
            report_json_path=persistence_input.report_json_path,
            bescos_raw_path=persistence_input.bescos_raw_path,
        )

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("electronet", True, ""),
        fetcher_factory=DummyFetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: build_prepare_provider_resolution_result(
            source="electronet",
            url=cli_arg.url,
            parsed=parsed,
            fetch_method="httpx",
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment_result(
            manufacturer_enrichment={}
        ),
        assemble_prepare_result_fn=lambda **kwargs: PrepareResultAssemblyResult(
            schema_match=SchemaMatchResult(matched_schema_id="schema-1", score=0.9),
            schema_candidates=[],
            row={"model": kwargs["cli"].model},
            normalized={"input": kwargs["cli"].to_dict()},
            report={
                "source": kwargs["source"],
                "fetch_mode": kwargs["fetch"].method,
                "identity_checks": {"source": kwargs["source"]},
                "warnings": [],
            },
        ),
        persist_prepare_scrape_artifacts_fn=fake_persist,
    )

    assert len(persistence_calls) == 1
    persistence_input = persistence_calls[0]
    assert persistence_input.model == cli.model
    assert persistence_input.scrape_dir == tmp_path / cli.model
    assert persistence_input.raw_html == "<html></html>"
    assert persistence_input.source_payload["raw_html_path"] == str(
        persistence_input.raw_html_path
    )
    assert persistence_input.normalized_payload["input"]["model"] == cli.model
    assert result["raw_html_path"] == persistence_input.raw_html_path
    assert result["source_json_path"] == persistence_input.source_json_path
    assert result["normalized_json_path"] == persistence_input.normalized_json_path
    assert result["report_json_path"] == persistence_input.report_json_path


def test_execute_prepare_stage_routes_skroutz_through_provider_by_default(
    tmp_path: Path,
) -> None:
    cli = CLIInput(
        model=SAMPLE_MODEL,
        url=SAMPLE_URL,
        photos=2,
        sections=0,
        skroutz_status=0,
        boxnow=1,
        price="19",
        out=str(tmp_path),
    )
    parsed = ParsedProduct(
        source=SourceProductData(
            source_name="skroutz",
            page_type="product",
            url=cli.url,
            canonical_url=cli.url,
            product_code=cli.model,
            brand="Estia",
            mpn="06-24567",
            name="Estia 06-24567",
            breadcrumbs=[
                "Αρχική",
                "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
                "Συσκευές Κουζίνας",
                "Βραστήρες",
            ],
            taxonomy_source_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ:::Συσκευές Κουζίνας///Βραστήρες",
            taxonomy_match_type="exact_category",
            taxonomy_rule_id="family:kettle",
            price_text="19,00 €",
            price_value=19.0,
            key_specs=[SpecItem(label="Ισχύς", value="2200 W")],
            spec_sections=[
                SpecSection(
                    section="Χαρακτηριστικά",
                    items=[SpecItem(label="Ισχύς", value="2200 W")],
                )
            ],
        ),
    )
    seam_calls: list[CLIInput] = []

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
        fetcher_factory=DummyFetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: (
            seam_calls.append(cli_arg)
            or build_prepare_provider_resolution_result(
                source="skroutz",
                url=cli_arg.url,
                parsed=parsed,
                fetch_method="playwright",
                fallback_used=True,
            )
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment_result(),
        assemble_prepare_result_fn=lambda **kwargs: PrepareResultAssemblyResult(
            schema_match=SchemaMatchResult(matched_schema_id="schema-1", score=0.9),
            schema_candidates=[],
            row={"model": kwargs["cli"].model},
            normalized={"input": kwargs["cli"].to_dict()},
            report={
                "source": kwargs["source"],
                "fetch_mode": kwargs["fetch"].method,
                "identity_checks": {"source": kwargs["source"]},
                "warnings": [],
            },
        ),
    )

    assert len(seam_calls) == 1
    assert seam_calls[0].model == cli.model
    assert seam_calls[0].url == cli.url
    assert seam_calls[0].photos == cli.photos
    assert seam_calls[0].sections == 0
    assert seam_calls[0].skroutz_status == 0
    assert seam_calls[0].boxnow == 0
    assert seam_calls[0].price == 0
    assert seam_calls[0].out == str(tmp_path / cli.model)
    assert result["report"]["source"] == "skroutz"
    assert result["report"]["fetch_mode"] == "playwright"
    assert result["fetch"].method == "playwright"
    assert result["parsed"].source.source_name == "skroutz"


def test_execute_prepare_stage_routes_manufacturer_tefal_through_provider_by_default(
    tmp_path: Path,
) -> None:
    cli = CLIInput(
        model=MANUFACTURER_MODEL,
        url=MANUFACTURER_URL,
        photos=3,
        sections=0,
        skroutz_status=0,
        boxnow=1,
        price="219",
        out=str(tmp_path),
    )
    parsed = ParsedProduct(
        source=SourceProductData(
            source_name="manufacturer_tefal",
            page_type="product",
            url=cli.url,
            canonical_url=cli.url,
            product_code="IG602A",
            brand="Tefal",
            mpn="IG602A",
            name="Tefal Dolci Παγωτομηχανή IG602A",
            breadcrumbs=[
                "Αρχική",
                "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
                "Μικροί Μάγειρες",
                "Παγωτομηχανές",
            ],
            taxonomy_source_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ:::ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Μικροί Μάγειρες///Παγωτομηχανές",
            taxonomy_match_type="exact_category",
            taxonomy_rule_id="manufacturer_tefal:ice_cream_maker",
            price_text="229,90 €",
            price_value=229.9,
            key_specs=[
                SpecItem(label="Χωρητικότητα", value="1.4 lt"),
                SpecItem(label="Αριθμός Προγραμμάτων", value="10"),
                SpecItem(label="Αριθμός Δοχείων", value="3"),
            ],
            spec_sections=[
                SpecSection(
                    section="Παραγωγή & Δυνατότητες",
                    items=[
                        SpecItem(label="Χωρητικότητα", value="1.4 lt"),
                        SpecItem(label="Αριθμός Προγραμμάτων", value="10"),
                        SpecItem(label="Αριθμός Δοχείων", value="3"),
                    ],
                )
            ],
            manufacturer_spec_sections=[
                SpecSection(
                    section="Χαρακτηριστικά Κατασκευαστή",
                    items=[SpecItem(label="Τάση", value="220-240 V")],
                )
            ],
        ),
    )

    class DummyManufacturerResolver:
        def resolve(self, **_kwargs):
            return (
                TaxonomyResolution(
                    parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
                    leaf_category="Μικροί Μάγειρες",
                    sub_category="Παγωτομηχανές",
                ),
                [],
            )

    seam_calls: list[CLIInput] = []

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: (
            "manufacturer_tefal",
            True,
            "manufacturer_tefal_product_path",
        ),
        fetcher_factory=DummyFetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: (
            seam_calls.append(cli_arg)
            or build_prepare_provider_resolution_result(
                source="manufacturer_tefal",
                url=cli_arg.url,
                parsed=parsed,
                fetch_method="httpx",
            )
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment_result(
            taxonomy=TaxonomyResolution(
                parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
                leaf_category="Μικροί Μάγειρες",
                sub_category="Παγωτομηχανές",
            ),
            manufacturer_enrichment={
                "applied": False,
                "documents": [],
                "presentation_applied": False,
            },
        ),
        assemble_prepare_result_fn=lambda **kwargs: PrepareResultAssemblyResult(
            schema_match=SchemaMatchResult(matched_schema_id="schema-1", score=0.9),
            schema_candidates=[],
            row={"model": kwargs["cli"].model},
            normalized={
                "input": kwargs["cli"].to_dict(),
                "deterministic_product": {"mpn": "IG602A"},
            },
            report={
                "source": kwargs["source"],
                "fetch_mode": kwargs["fetch"].method,
                "identity_checks": {"source": kwargs["source"]},
                "warnings": [],
            },
        ),
    )

    assert len(seam_calls) == 1
    assert seam_calls[0].model == cli.model
    assert seam_calls[0].url == cli.url
    assert seam_calls[0].photos == cli.photos
    assert seam_calls[0].sections == 0
    assert seam_calls[0].skroutz_status == 0
    assert seam_calls[0].boxnow == 0
    assert seam_calls[0].price == 0
    assert seam_calls[0].out == str(tmp_path / cli.model)
    assert result["parsed"].source.source_name == "manufacturer_tefal"
    assert result["report"]["fetch_mode"] == "httpx"
    assert result["fetch"].method == "httpx"
    assert result["normalized"]["deterministic_product"]["mpn"] == "IG602A"


def test_execute_prepare_stage_fails_fast_when_supported_source_has_no_provider(
    tmp_path: Path,
) -> None:
    cli = CLIInput(
        model=SAMPLE_MODEL,
        url=SAMPLE_URL,
        photos=2,
        sections=0,
        skroutz_status=0,
        boxnow=1,
        price="19",
        out=str(tmp_path),
    )

    with pytest.raises(RuntimeError, match="Provider 'skroutz' is not registered"):
        execute_prepare_stage(
            cli,
            model_dir=tmp_path / SAMPLE_MODEL,
            validate_url_scope_fn=lambda _url: (
                "skroutz",
                True,
                "skroutz_product_path",
            ),
            fetcher_factory=DummyFetcher,
            resolve_prepare_provider_input_fn=lambda _cli, **_kwargs: (
                _ for _ in ()
            ).throw(RuntimeError("Provider 'skroutz' is not registered")),
            resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment_result(),
            assemble_prepare_result_fn=lambda **kwargs: PrepareResultAssemblyResult(
                schema_match=SchemaMatchResult(matched_schema_id="schema-1", score=0.9),
                schema_candidates=[],
                row={"model": kwargs["cli"].model},
                normalized={"input": kwargs["cli"].to_dict()},
                report={
                    "source": kwargs["source"],
                    "fetch_mode": kwargs["fetch"].method,
                    "identity_checks": {"source": kwargs["source"]},
                    "warnings": [],
                },
            ),
        )


def test_execute_prepare_stage_keeps_source_capture_sync_failure_as_prepare_warning(
    tmp_path: Path,
) -> None:
    cli = CLIInput(
        model="229957",
        url="https://www.electronet.gr/example",
        photos=0,
        sections=0,
        skroutz_status=1,
        boxnow=0,
        price="599",
        out=str(tmp_path),
    )
    parsed = ParsedProduct(
        source=SourceProductData(
            source_name="electronet",
            page_type="product",
            url=cli.url,
            canonical_url=cli.url,
            product_code=cli.model,
            brand="LG",
            name="LG RHX5009TWB",
            spec_sections=[
                SpecSection(
                    section="Χαρακτηριστικά",
                    items=[SpecItem(label="Τύπος", value="Στεγνωτήριο")],
                )
            ],
        ),
    )

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_domain"),
        fetcher_factory=DummyFetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: build_prepare_provider_resolution_result(
            source="electronet",
            url=cli_arg.url,
            parsed=parsed,
            fetch_method="httpx",
        ),
        source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(
            status="failed", message="connection refused"
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment_result(
            manufacturer_enrichment={}
        ),
        assemble_prepare_result_fn=lambda **kwargs: PrepareResultAssemblyResult(
            schema_match=SchemaMatchResult(matched_schema_id="schema-1", score=0.9),
            schema_candidates=[],
            row={"model": kwargs["cli"].model},
            normalized={"input": kwargs["cli"].to_dict()},
            report={
                "source": kwargs["source"],
                "fetch_mode": kwargs["fetch"].method,
                "identity_checks": {"source": kwargs["source"]},
                "warnings": list(kwargs["parsed"].warnings),
            },
        ),
    )

    assert result["report"]["warnings"] == [
        "source_capture_sync_failed:connection refused"
    ]
    assert result["source_json_path"].exists()
