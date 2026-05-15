import sys
import json
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.source_url_agent.browser import PageSnapshot  # noqa: E402
from ecommerce.source_url_agent.google_top_results import (  # noqa: E402
    CandidateUrlNormalizer,
    GoogleTopResultsProvider,
    KnownSourceUrlClassifier,
    SourceProductUrlFilter,
    build_google_product_queries,
    google_result_urls,
)
from ecommerce.source_url_agent.products import AgentProduct  # noqa: E402
from ecommerce.source_url_agent.products import read_products_from_csv  # noqa: E402
from ecommerce.source_url_agent.search import (  # noqa: E402
    discover_google_top_results_product_evidence,
    discover_source_evidence,
    generate_search_queries,
)
from ecommerce.source_url_agent.search_providers import (  # noqa: E402
    BrowserFallbackSearchProvider,
    SearchProviderDefinition,
    SearchProviderRegistry,
    discover_with_provider_cascade,
    load_search_provider_registry,
)
from ecommerce.source_url_agent.sources import load_source_registry  # noqa: E402


def _product(**overrides) -> AgentProduct:
    values = {
        "catalog_product_id": None,
        "catalog_source": "sourceCata",
        "model": "123456",
        "mpn": "HBA514BS3",
        "name": "Series 4 built in oven",
        "category": "Ovens",
        "manufacturer": "Bosch",
        "price": None,
        "quantity": 1,
        "status": 1,
        "bestprice_status": 1,
        "skroutz_status": 1,
    }
    values.update(overrides)
    return AgentProduct(**values)


def test_csv_input_preserves_leading_zero_model_and_filters_active(tmp_path: Path) -> None:
    path = tmp_path / "input.csv"
    path.write_text(
        "model,mpn,name,category,manufacturer,price,quantity,status,date_added,bestprice_status,skroutz_status\n"
        "005606,MPN-1,Product One,Category,Brand,12.34,2,1,,1,1\n"
        "123456,MPN-2,Inactive,Category,Brand,9.99,0,0,,1,1\n",
        encoding="utf-8-sig",
    )

    products = read_products_from_csv(path)
    all_products = read_products_from_csv(path, active_only=False)

    assert [product.model for product in products] == ["005606"]
    assert all_products[0].model == "005606"
    assert all_products[0].mpn == "MPN-1"


def test_source_registry_loading() -> None:
    registry = load_source_registry()

    assert registry.get("bestprice").source_domain == "www.bestprice.gr"
    assert registry.get("electronet").source_type == "direct_vendor"
    assert {source.source_name for source in registry.selected("all")} >= {"bestprice", "skroutz", "electronet"}


def test_search_provider_registry_loading_and_source_specific_cascade() -> None:
    registry = load_search_provider_registry()

    assert registry.default_cascade == ("google_top_results",)
    provider = registry.get("google_top_results")
    assert provider.provider_type == "google"
    assert provider.enabled is True
    assert provider.allow_high_confidence_auto_apply is False
    assert provider.search_url_template == "https://www.google.gr/search?q={query}&hl=el&gl=GR&num=10&pws=0"
    assert [item.provider_name for item in registry.cascade_for_source("bestprice")] == ["google_top_results"]


def test_search_provider_registry_uses_default_cascade_when_source_is_not_configured(tmp_path: Path) -> None:
    path = tmp_path / "search_providers.json"
    path.write_text(
        json.dumps(
            {
                "default_cascade": ["browser_fallback"],
                "providers": [
                    {
                        "provider_name": "browser_fallback",
                        "provider_type": "browser",
                        "enabled": True,
                        "allow_high_confidence_auto_apply": True,
                    }
                ],
                "source_cascades": {},
            }
        ),
        encoding="utf-8",
    )

    registry = load_search_provider_registry(path)

    assert [item.provider_name for item in registry.cascade_for_source("electronet")] == ["browser_fallback"]


def test_search_provider_registry_rejects_unknown_provider_in_cascade(tmp_path: Path) -> None:
    path = tmp_path / "search_providers.json"
    path.write_text(
        json.dumps(
            {
                "default_cascade": ["missing_provider"],
                "providers": [
                    {
                        "provider_name": "browser_fallback",
                        "provider_type": "browser",
                        "enabled": True,
                        "allow_high_confidence_auto_apply": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_search_provider_registry(path)
    except ValueError as exc:
        assert "Unknown source URL search provider" in str(exc)
    else:
        raise AssertionError("Expected unknown provider cascade to fail.")


def test_disabled_search_provider_is_skipped_without_fetching() -> None:
    source = load_source_registry().get("bestprice")
    registry = SearchProviderRegistry(
        default_cascade=("browser_fallback",),
        providers={
            "browser_fallback": SearchProviderDefinition(
                provider_name="browser_fallback",
                provider_type="browser",
                enabled=False,
                allow_high_confidence_auto_apply=True,
            )
        },
        source_cascades={},
    )
    browser = _FakeBrowser({})

    result = discover_with_provider_cascade(
        product=_product(),
        source=source,
        browser=browser,
        queries=["Bosch HBA514BS3"],
        registry=registry,
    )

    assert result.candidates == []
    assert result.errors == ["provider_disabled:browser_fallback"]
    assert browser.fetched_urls == []


def test_generate_search_queries_with_full_data_uses_ranked_identifier_variants() -> None:
    source = replace(load_source_registry().get("electronet"), max_searches_per_product=8)

    assert generate_search_queries(_product(), source) == [
        "Bosch HBA514BS3",
        "HBA514BS3",
        "Bosch 123456",
        "123456",
        "Bosch Series 4 built in oven",
        "Series 4 built in oven",
    ]


def test_generate_search_queries_without_manufacturer_keeps_identifier_and_name_variants() -> None:
    source = replace(load_source_registry().get("electronet"), max_searches_per_product=8)

    assert generate_search_queries(_product(manufacturer=""), source) == [
        "HBA514BS3",
        "123456",
        "Series 4 built in oven",
    ]


def test_generate_search_queries_without_mpn_keeps_model_and_name_variants() -> None:
    source = replace(load_source_registry().get("electronet"), max_searches_per_product=8)

    assert generate_search_queries(_product(mpn=""), source) == [
        "Bosch 123456",
        "123456",
        "Bosch Series 4 built in oven",
        "Series 4 built in oven",
    ]


def test_generate_search_queries_dedupes_case_insensitively_and_respects_bounds() -> None:
    source = replace(load_source_registry().get("electronet"), max_searches_per_product=2)
    product = _product(model="mr25gb", mpn="MR25GB", name="LG MR25GB", manufacturer="LG")

    assert generate_search_queries(product, source) == ["LG MR25GB", "MR25GB"]


def test_generate_search_queries_uses_source_query_templates_before_generic_defaults() -> None:
    source = replace(
        load_source_registry().get("electronet"),
        max_searches_per_product=3,
        query_templates=("{mpn} {manufacturer}", "{manufacturer} {mpn}", "{unknown}"),
    )

    assert generate_search_queries(_product(), source) == [
        "HBA514BS3 Bosch",
        "Bosch HBA514BS3",
        "HBA514BS3",
    ]


def test_browser_fallback_provider_uses_source_search_urls_and_product_url_rules() -> None:
    source = replace(load_source_registry().get("bestprice"), max_searches_per_product=1, max_candidates_per_product=2)
    search_url = "https://www.bestprice.gr/search?q=Bosch+HBA514BS3"
    product_url = "https://www.bestprice.gr/item/123/bosch-hba514bs3.html?utm_source=test"
    browser = _FakeBrowser(
        {
            search_url: PageSnapshot(
                requested_url=search_url,
                final_url=search_url,
                title="Search",
                html="<html></html>",
                body_text="",
                links=(product_url, "https://www.bestprice.gr/search?q=ignored"),
            )
        }
    )
    definition = SearchProviderDefinition(
        provider_name="browser_fallback",
        provider_type="browser",
        enabled=True,
        allow_high_confidence_auto_apply=True,
    )

    result = BrowserFallbackSearchProvider(definition).discover(
        product=_product(),
        source=source,
        browser=browser,
        queries=["Bosch HBA514BS3"],
        max_searches=None,
        max_candidates=None,
        rate_limit_seconds=0,
    )

    assert result.searched_queries == ["Bosch HBA514BS3"]
    assert result.searched_urls == [search_url]
    assert [item.candidate_url for item in result.candidates] == [
        "https://www.bestprice.gr/item/123/bosch-hba514bs3.html"
    ]
    assert result.candidates[0].provenance.to_json() == {
        "provider_name": "browser_fallback",
        "source_name": "bestprice",
        "original_query": "Bosch HBA514BS3",
        "search_url": search_url,
        "candidate_url": "https://www.bestprice.gr/item/123/bosch-hba514bs3.html",
        "result_index": 1,
        "discovery_method": "public_source_search_page",
        "allow_high_confidence_auto_apply": True,
    }


def test_discover_source_evidence_uses_provider_cascade_and_preserves_provenance() -> None:
    product = _product()
    source = replace(load_source_registry().get("bestprice"), max_searches_per_product=1, max_candidates_per_product=1)
    search_url = "https://www.bestprice.gr/search?q=Bosch+HBA514BS3"
    product_url = "https://www.bestprice.gr/item/123/bosch-hba514bs3.html"
    browser = _FakeBrowser(
        {
            search_url: PageSnapshot(
                requested_url=search_url,
                final_url=search_url,
                title="Search",
                html="<html></html>",
                body_text="",
                links=(product_url,),
            ),
            product_url: PageSnapshot(
                requested_url=product_url,
                final_url=product_url,
                title="Bosch HBA514BS3 oven",
                html="<html><head><title>Bosch HBA514BS3 oven</title></head><body>Bosch HBA514BS3 Ovens</body></html>",
                body_text="Bosch HBA514BS3 Ovens",
            ),
        }
    )
    provider_registry = SearchProviderRegistry(
        default_cascade=("browser_fallback",),
        providers={
            "browser_fallback": SearchProviderDefinition(
                provider_name="browser_fallback",
                provider_type="browser",
                enabled=True,
                allow_high_confidence_auto_apply=True,
            )
        },
        source_cascades={},
    )

    result = discover_source_evidence(
        product=product,
        source=source,
        browser=browser,
        max_searches=1,
        max_candidates=1,
        rate_limit_seconds=0,
        provider_registry=provider_registry,
    )

    assert result.searched_queries == ["Bosch HBA514BS3"]
    assert result.searched_urls == [search_url]
    assert len(result.evidence) == 1
    provenance = result.evidence[0].to_json()["provider_provenance"]
    assert provenance["provider_name"] == "browser_fallback"
    assert provenance["search_url"] == search_url
    assert provenance["candidate_url"] == product_url


def test_google_top_results_query_generation_uses_model_or_mpn_then_brand() -> None:
    assert build_google_product_queries(_product(mpn="55C8L", manufacturer="TCL")) == ["55C8L TCL"]
    assert build_google_product_queries(_product(mpn="UTG-12CH", manufacturer="Toyotomi")) == ["UTG-12CH Toyotomi"]
    assert build_google_product_queries(_product(mpn="", model="HBA514BS3", manufacturer="Bosch")) == ["HBA514BS3 Bosch"]


def test_google_result_html_extraction_and_redirect_unwrapping(fixtures_root: Path) -> None:
    html = (fixtures_root / "source_url_agent" / "google" / "utg_12ch_toyotomi.txt").read_text(encoding="utf-8")
    search_url = "https://www.google.gr/search?q=UTG-12CH+Toyotomi&hl=el&gl=GR&num=10&pws=0"
    snapshot = PageSnapshot(
        requested_url=search_url,
        final_url=search_url,
        title="UTG-12CH Toyotomi - Google Search",
        html=html,
        body_text="",
    )
    urls = google_result_urls(snapshot, base_url=search_url, max_results=10)
    normalizer = CandidateUrlNormalizer()

    assert len(urls) == 7
    assert normalizer.normalize(urls[0], base_url=search_url) == "https://www.skroutz.gr/s/123456/Toyotomi-UTG-12CH.html"
    assert normalizer.normalize(urls[1], base_url=search_url) == "https://www.bestprice.gr/item/987654/toyotomi-utg-12ch.html"


def test_google_known_source_classification_and_product_url_filtering() -> None:
    registry = load_source_registry()
    sources = registry.selected("all")
    classifier = KnownSourceUrlClassifier(sources)
    product_filter = SourceProductUrlFilter()
    skroutz = registry.get("skroutz")

    assert classifier.classify("https://www.skroutz.gr/s/123/toyotomi.html").source_name == "skroutz"
    assert classifier.classify("https://unknown.example/product") is None
    assert product_filter.keep(skroutz, "https://www.skroutz.gr/s/123/toyotomi.html?utm_source=x") == (
        "https://www.skroutz.gr/s/123/toyotomi.html"
    )
    assert product_filter.keep(skroutz, "https://www.skroutz.gr/c/1492/klimatistika.html") == ""
    assert product_filter.keep(skroutz, "https://www.skroutz.gr/search?keyphrase=UTG-12CH") == ""


def test_google_top_results_provider_keeps_known_product_urls_grouped_by_source(fixtures_root: Path) -> None:
    registry = load_source_registry()
    sources = registry.selected("all")
    product = _product(mpn="UTG-12CH", manufacturer="Toyotomi")
    definition = SearchProviderDefinition(
        provider_name="google_top_results",
        provider_type="google",
        enabled=True,
        allow_high_confidence_auto_apply=False,
        search_url_template="https://www.google.gr/search?q={query}&hl=el&gl=GR&num=10&pws=0",
        max_results_per_query=10,
        stop_after_first_query_with_candidates=True,
    )
    search_url = "https://www.google.gr/search?q=UTG-12CH+Toyotomi&hl=el&gl=GR&num=10&pws=0"
    html = (fixtures_root / "source_url_agent" / "google" / "utg_12ch_toyotomi.txt").read_text(encoding="utf-8")
    browser = _FakeBrowser(
        {
            search_url: PageSnapshot(
                requested_url=search_url,
                final_url=search_url,
                title="UTG-12CH Toyotomi - Google Search",
                html=html,
                body_text="",
            )
        }
    )

    result = GoogleTopResultsProvider(definition).discover_product(
        product=product,
        sources=sources,
        browser=browser,
        rate_limit_seconds=0,
    )

    assert browser.fetched_urls == [search_url]
    assert result.status == "found_candidates"
    assert [candidate.candidate_url for candidate in result.candidates] == [
        "https://www.skroutz.gr/s/123456/Toyotomi-UTG-12CH.html",
        "https://www.bestprice.gr/item/987654/toyotomi-utg-12ch.html",
        "https://www.plaisio.gr/product/oikiakes-syskeues/klimatistika/toyotomi/klimatistiko-toyotomi-utg-12ch",
    ]
    assert result.kept_candidates_by_source == {"skroutz": 1, "bestprice": 1, "plaisio": 1}
    assert result.discarded_count == 4
    assert result.to_summary()["kept_candidates_by_source"] == {"skroutz": 1, "bestprice": 1, "plaisio": 1}


def test_google_top_results_product_evidence_fetches_only_kept_candidates(fixtures_root: Path) -> None:
    registry = load_source_registry()
    sources = registry.selected("all")
    product = _product(mpn="UTG-12CH", manufacturer="Toyotomi", name="Toyotomi UTG-12CH air conditioner")
    provider_registry = SearchProviderRegistry(
        default_cascade=("google_top_results",),
        providers={
            "google_top_results": SearchProviderDefinition(
                provider_name="google_top_results",
                provider_type="google",
                enabled=True,
                allow_high_confidence_auto_apply=False,
                search_url_template="https://www.google.gr/search?q={query}&hl=el&gl=GR&num=10&pws=0",
            )
        },
        source_cascades={},
    )
    search_url = "https://www.google.gr/search?q=UTG-12CH+Toyotomi&hl=el&gl=GR&num=10&pws=0"
    skroutz_url = "https://www.skroutz.gr/s/123456/Toyotomi-UTG-12CH.html"
    bestprice_url = "https://www.bestprice.gr/item/987654/toyotomi-utg-12ch.html"
    plaisio_url = "https://www.plaisio.gr/product/oikiakes-syskeues/klimatistika/toyotomi/klimatistiko-toyotomi-utg-12ch"
    google_html = (fixtures_root / "source_url_agent" / "google" / "utg_12ch_toyotomi.txt").read_text(encoding="utf-8")
    product_html = "<html><head><title>Toyotomi UTG-12CH</title></head><body>Toyotomi UTG-12CH</body></html>"
    browser = _FakeBrowser(
        {
            search_url: PageSnapshot(
                requested_url=search_url,
                final_url=search_url,
                title="UTG-12CH Toyotomi - Google Search",
                html=google_html,
                body_text="",
            ),
            skroutz_url: PageSnapshot(skroutz_url, skroutz_url, "Toyotomi UTG-12CH", product_html, "Toyotomi UTG-12CH"),
            bestprice_url: PageSnapshot(bestprice_url, bestprice_url, "Toyotomi UTG-12CH", product_html, "Toyotomi UTG-12CH"),
            plaisio_url: PageSnapshot(plaisio_url, plaisio_url, "Toyotomi UTG-12CH", product_html, "Toyotomi UTG-12CH"),
        }
    )

    results = discover_google_top_results_product_evidence(
        product=product,
        sources=sources,
        browser=browser,
        provider_registry=provider_registry,
        rate_limit_seconds=0,
    )

    assert browser.fetched_urls == [search_url, skroutz_url, bestprice_url, plaisio_url]
    assert len(results["skroutz"].evidence) == 1
    assert len(results["bestprice"].evidence) == 1
    assert len(results["plaisio"].evidence) == 1
    assert results["electronet"].evidence == []
    assert results["skroutz"].provider_summary == {
        "query": "UTG-12CH Toyotomi",
        "status": "found_candidates",
        "kept_candidates_by_source": {"skroutz": 1, "bestprice": 1, "plaisio": 1},
        "discarded_count": 4,
    }


def test_google_top_results_provider_dedupes_and_stops_after_one_query() -> None:
    product = _product(mpn="UTG-12CH", manufacturer="Toyotomi")
    source = load_source_registry().get("skroutz")
    definition = SearchProviderDefinition(
        provider_name="google_top_results",
        provider_type="google",
        enabled=True,
        allow_high_confidence_auto_apply=False,
        search_url_template="https://www.google.gr/search?q={query}",
    )
    search_url = "https://www.google.gr/search?q=UTG-12CH+Toyotomi"
    html = """
    <html><body>
      <a href="/url?q=https%3A%2F%2Fwww.skroutz.gr%2Fs%2F1%2Ftoyotomi.html&amp;sa=U">one</a>
      <a href="https://www.skroutz.gr/s/1/toyotomi.html?utm_campaign=x">duplicate</a>
    </body></html>
    """
    browser = _FakeBrowser(
        {
            search_url: PageSnapshot(
                requested_url=search_url,
                final_url=search_url,
                title="Search",
                html=html,
                body_text="",
            )
        }
    )

    result = GoogleTopResultsProvider(definition).discover_product(
        product=product,
        sources=[source],
        browser=browser,
        rate_limit_seconds=0,
    )

    assert browser.fetched_urls == [search_url]
    assert [candidate.candidate_url for candidate in result.candidates] == ["https://www.skroutz.gr/s/1/toyotomi.html"]


def test_google_top_results_blocked_or_consent_page_returns_status_without_candidates() -> None:
    product = _product(mpn="UTG-12CH", manufacturer="Toyotomi")
    source = load_source_registry().get("skroutz")
    definition = SearchProviderDefinition(
        provider_name="google_top_results",
        provider_type="google",
        enabled=True,
        allow_high_confidence_auto_apply=False,
        search_url_template="https://www.google.gr/search?q={query}",
    )
    search_url = "https://www.google.gr/search?q=UTG-12CH+Toyotomi"
    browser = _FakeBrowser(
        {
            search_url: PageSnapshot(
                requested_url=search_url,
                final_url="https://consent.google.com/m",
                title="Before you continue to Google Search",
                html="<html>Before you continue to Google Search</html>",
                body_text="Before you continue to Google Search",
            )
        }
    )

    result = GoogleTopResultsProvider(definition).discover_product(
        product=product,
        sources=[source],
        browser=browser,
        rate_limit_seconds=0,
    )

    assert result.status == "consent_required"
    assert result.candidates == []
    assert result.errors == ["google_top_results:consent_required"]


class _FakeBrowser:
    def __init__(self, snapshots: dict[str, PageSnapshot]) -> None:
        self.snapshots = snapshots
        self.fetched_urls: list[str] = []

    def fetch_snapshot(self, url: str, *, rate_limit_seconds: float | None = None) -> PageSnapshot:
        del rate_limit_seconds
        self.fetched_urls.append(url)
        try:
            return self.snapshots[url]
        except KeyError:
            return PageSnapshot(
                requested_url=url,
                final_url="",
                title="",
                html="",
                body_text="",
                status="error",
                error_code="not_found",
                error_message="Missing fake snapshot.",
            )
