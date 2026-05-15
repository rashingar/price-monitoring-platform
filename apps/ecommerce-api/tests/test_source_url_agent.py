import sys
import json
import httpx
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.source_url_agent.browser import PageSnapshot  # noqa: E402
from ecommerce.source_url_agent.brave_search import (  # noqa: E402
    BRAVE_DISCOVERY_METHOD,
    BRAVE_SEARCH_API_KEY_ENV_VAR,
    BRAVE_SEARCH_PROVIDER_NAME,
    BraveSearchProvider,
    HttpxBraveSearchClient,
    build_brave_product_queries,
    brave_web_results,
)
from ecommerce.source_url_agent.result_url_candidates import (  # noqa: E402
    KnownSourceUrlClassifier,
    SourceProductUrlFilter,
)
from ecommerce.source_url_agent.products import AgentProduct  # noqa: E402
from ecommerce.source_url_agent.products import read_products_from_csv  # noqa: E402
from ecommerce.source_url_agent.options import SourceUrlAgentOptions  # noqa: E402
from ecommerce.source_url_agent.search import (  # noqa: E402
    SourceSearchResult,
    discover_product_level_search_evidence,
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
from ecommerce.source_url_agent import task_execution  # noqa: E402


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

    assert registry.default_cascade == ("brave_search",)
    provider = registry.get("brave_search")
    assert provider.provider_type == "brave"
    assert provider.enabled is True
    assert provider.allow_high_confidence_auto_apply is False
    assert provider.endpoint_url == "https://api.search.brave.com/res/v1/web/search"
    assert provider.country == "GR"
    assert provider.search_lang == "el"
    assert provider.ui_lang == "el-GR"
    assert provider.count == 10
    assert provider.result_filter == "web"
    assert provider.spellcheck is False
    assert [item.provider_name for item in registry.cascade_for_source("bestprice")] == ["brave_search"]


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


def test_brave_search_missing_api_key_returns_status_without_candidates(monkeypatch) -> None:
    monkeypatch.delenv(BRAVE_SEARCH_API_KEY_ENV_VAR, raising=False)
    definition = _brave_definition()

    result = BraveSearchProvider(definition, client=_FakeBraveClient(_brave_response())).discover_product(
        product=_product(mpn="UTG-12CH", manufacturer="Toyotomi"),
        sources=load_source_registry().selected("all"),
    )

    assert result.status == "missing_api_key"
    assert result.candidates == []
    assert result.errors == ["brave_search:missing_api_key"]


def test_brave_search_query_generation_uses_model_or_mpn_then_brand() -> None:
    assert build_brave_product_queries(_product(mpn="55C8L", manufacturer="TCL")) == ["55C8L TCL"]
    assert build_brave_product_queries(_product(mpn="UTG-12CH", manufacturer="Toyotomi")) == ["UTG-12CH Toyotomi"]
    assert build_brave_product_queries(_product(mpn="", model="HBA514BS3", manufacturer="Bosch")) == ["HBA514BS3 Bosch"]


def test_brave_search_request_uses_configured_api_contract(monkeypatch) -> None:
    monkeypatch.setenv(BRAVE_SEARCH_API_KEY_ENV_VAR, "fake-token")
    client = _FakeBraveClient(_brave_response())
    definition = _brave_definition()

    BraveSearchProvider(definition, client=client).discover_product(
        product=_product(mpn="UTG-12CH", manufacturer="Toyotomi"),
        sources=[load_source_registry().get("skroutz")],
    )

    request = client.requests[0]
    assert request["endpoint_url"] == "https://api.search.brave.com/res/v1/web/search"
    assert request["api_key"] == "fake-token"
    assert request["query"] == "UTG-12CH Toyotomi"
    assert request["definition"].country == "GR"
    assert request["definition"].search_lang == "el"
    assert request["definition"].ui_lang == "el-GR"
    assert request["definition"].count == 10
    assert request["definition"].result_filter == "web"
    assert request["definition"].spellcheck is False


def test_brave_http_client_sends_subscription_token_header(monkeypatch) -> None:
    captured: dict = {}

    class FakeHttpxClient:
        def __init__(self, *, timeout) -> None:
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def get(self, url, *, params, headers):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            return _FakeBraveResponse(_brave_response())

    monkeypatch.setattr("ecommerce.source_url_agent.brave_search.httpx.Client", FakeHttpxClient)

    response = HttpxBraveSearchClient().search(
        definition=_brave_definition(),
        query="UTG-12CH Toyotomi",
        api_key="fake-token",
    )

    assert response.status_code == 200
    assert captured["url"] == "https://api.search.brave.com/res/v1/web/search"
    assert captured["headers"]["X-Subscription-Token"] == "fake-token"
    assert captured["headers"]["Accept"] == "application/json"
    assert captured["headers"]["Accept-Encoding"] == "gzip"
    assert captured["params"]["q"] == "UTG-12CH Toyotomi"
    assert captured["params"]["country"] == "GR"
    assert captured["params"]["search_lang"] == "el"
    assert captured["params"]["ui_lang"] == "el-GR"
    assert captured["params"]["count"] == 10
    assert captured["params"]["result_filter"] == "web"
    assert captured["params"]["spellcheck"] == "false"


def test_brave_json_response_parsing_from_web_results() -> None:
    items = brave_web_results(_brave_response(), max_results=10)

    assert [(item.rank, item.url, item.title, item.description) for item in items[:2]] == [
        (
            1,
            "https://www.skroutz.gr/s/123456/Toyotomi-UTG-12CH.html?utm_source=brave",
            "Toyotomi UTG-12CH | Skroutz",
            "Skroutz product page",
        ),
        (
            2,
            "https://www.bestprice.gr/item/987654/toyotomi-utg-12ch.html",
            "Toyotomi UTG-12CH | BestPrice",
            "BestPrice product page",
        ),
    ]


def test_known_source_classification_and_product_url_filtering() -> None:
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


def test_brave_search_provider_keeps_known_product_urls_grouped_by_source(monkeypatch) -> None:
    monkeypatch.setenv(BRAVE_SEARCH_API_KEY_ENV_VAR, "fake-token")
    registry = load_source_registry()
    sources = registry.selected("all")
    product = _product(mpn="UTG-12CH", manufacturer="Toyotomi")
    client = _FakeBraveClient(_brave_response())

    result = BraveSearchProvider(_brave_definition(), client=client).discover_product(
        product=product,
        sources=sources,
    )

    assert len(client.requests) == 1
    assert result.status == "found_candidates"
    assert [candidate.candidate_url for candidate in result.candidates] == [
        "https://www.skroutz.gr/s/123456/Toyotomi-UTG-12CH.html",
        "https://www.bestprice.gr/item/987654/toyotomi-utg-12ch.html",
        "https://www.plaisio.gr/product/oikiakes-syskeues/klimatistika/toyotomi/klimatistiko-toyotomi-utg-12ch",
    ]
    assert result.kept_candidates_by_source == {"skroutz": 1, "bestprice": 1, "plaisio": 1}
    assert result.discarded_count == 2
    assert result.to_summary()["kept_candidates_by_source"] == {"skroutz": 1, "bestprice": 1, "plaisio": 1}
    provenance = result.candidates[0].provenance.to_json()
    assert provenance["provider_name"] == BRAVE_SEARCH_PROVIDER_NAME
    assert provenance["discovery_method"] == BRAVE_DISCOVERY_METHOD
    assert provenance["search_url"].startswith("https://api.search.brave.com/res/v1/web/search?")
    assert "fake-token" not in provenance["search_url"]


def test_brave_search_product_evidence_fetches_only_kept_candidates(monkeypatch) -> None:
    monkeypatch.setenv(BRAVE_SEARCH_API_KEY_ENV_VAR, "fake-token")
    registry = load_source_registry()
    sources = registry.selected("all")
    product = _product(mpn="UTG-12CH", manufacturer="Toyotomi", name="Toyotomi UTG-12CH air conditioner")
    provider_registry = SearchProviderRegistry(
        default_cascade=("brave_search",),
        providers={
            "brave_search": SearchProviderDefinition(
                provider_name="brave_search",
                provider_type="brave",
                enabled=True,
                allow_high_confidence_auto_apply=False,
                endpoint_url="https://api.search.brave.com/res/v1/web/search",
            )
        },
        source_cascades={},
    )
    skroutz_url = "https://www.skroutz.gr/s/123456/Toyotomi-UTG-12CH.html"
    bestprice_url = "https://www.bestprice.gr/item/987654/toyotomi-utg-12ch.html"
    plaisio_url = "https://www.plaisio.gr/product/oikiakes-syskeues/klimatistika/toyotomi/klimatistiko-toyotomi-utg-12ch"
    product_html = "<html><head><title>Toyotomi UTG-12CH</title></head><body>Toyotomi UTG-12CH</body></html>"
    browser = _FakeBrowser(
        {
            skroutz_url: PageSnapshot(skroutz_url, skroutz_url, "Toyotomi UTG-12CH", product_html, "Toyotomi UTG-12CH"),
            bestprice_url: PageSnapshot(bestprice_url, bestprice_url, "Toyotomi UTG-12CH", product_html, "Toyotomi UTG-12CH"),
            plaisio_url: PageSnapshot(plaisio_url, plaisio_url, "Toyotomi UTG-12CH", product_html, "Toyotomi UTG-12CH"),
        }
    )
    client = _FakeBraveClient(_brave_response())
    monkeypatch.setattr("ecommerce.source_url_agent.search.BraveSearchProvider", lambda definition: BraveSearchProvider(definition, client=client))

    results = discover_product_level_search_evidence(
        product=product,
        sources=sources,
        browser=browser,
        provider_registry=provider_registry,
        rate_limit_seconds=0,
    )

    assert len(client.requests) == 1
    assert browser.fetched_urls == [skroutz_url, bestprice_url, plaisio_url]
    assert len(results["skroutz"].evidence) == 1
    assert len(results["bestprice"].evidence) == 1
    assert len(results["plaisio"].evidence) == 1
    assert results["electronet"].evidence == []
    assert results["skroutz"].provider_summary == {
        "provider_name": "brave_search",
        "query": "UTG-12CH Toyotomi",
        "status": "found_candidates",
        "kept_candidates_by_source": {"skroutz": 1, "bestprice": 1, "plaisio": 1},
        "discarded_count": 2,
    }


def test_product_level_execution_calls_brave_once_per_product_not_per_source(monkeypatch, tmp_path: Path) -> None:
    registry = load_source_registry()
    sources = [registry.get("skroutz"), registry.get("bestprice"), registry.get("plaisio")]
    calls: list[tuple[str, tuple[str, ...]]] = []

    class FakeBrowserSession:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    def fake_product_level_evidence(*, product, sources, browser, provider_registry, max_candidates, rate_limit_seconds):
        del browser, provider_registry, max_candidates, rate_limit_seconds
        calls.append((product.model, tuple(source.source_name for source in sources)))
        return {
            source.source_name: SourceSearchResult(
                evidence=[],
                searched_queries=[f"{product.mpn} {product.manufacturer}"],
                searched_urls=["https://api.search.brave.com/res/v1/web/search?q=fake"],
                errors=[],
            )
            for source in sources
        }

    monkeypatch.setattr(task_execution, "SourceUrlBrowserSession", FakeBrowserSession)
    monkeypatch.setattr(task_execution, "discover_product_level_search_evidence", fake_product_level_evidence)

    task_execution.run_with_browser(
        run_id="run-1",
        products=[_product(model="111111", mpn="UTG-12CH", manufacturer="Toyotomi")],
        sources=sources,
        options=SourceUrlAgentOptions(mode="catalog", source="all", output_dir=tmp_path, dry_run=True),
        session=None,
    )

    assert calls == [("111111", ("skroutz", "bestprice", "plaisio"))]


def test_brave_search_provider_dedupes_and_stops_after_one_query(monkeypatch) -> None:
    monkeypatch.setenv(BRAVE_SEARCH_API_KEY_ENV_VAR, "fake-token")
    product = _product(mpn="UTG-12CH", manufacturer="Toyotomi")
    source = load_source_registry().get("skroutz")
    client = _FakeBraveClient(
        {
            "web": {
                "results": [
                    {"url": "https://www.skroutz.gr/s/1/toyotomi.html?utm_campaign=x"},
                    {"url": "https://www.skroutz.gr/s/1/toyotomi.html"},
                ]
            }
        }
    )

    result = BraveSearchProvider(_brave_definition(), client=client).discover_product(
        product=product,
        sources=[source],
    )

    assert len(client.requests) == 1
    assert [candidate.candidate_url for candidate in result.candidates] == ["https://www.skroutz.gr/s/1/toyotomi.html"]


def test_brave_search_http_error_statuses(monkeypatch) -> None:
    monkeypatch.setenv(BRAVE_SEARCH_API_KEY_ENV_VAR, "fake-token")
    product = _product(mpn="UTG-12CH", manufacturer="Toyotomi")
    source = load_source_registry().get("skroutz")

    unauthorized = BraveSearchProvider(_brave_definition(), client=_FakeBraveClient({}, status_code=401)).discover_product(
        product=product, sources=[source]
    )
    rate_limited = BraveSearchProvider(_brave_definition(), client=_FakeBraveClient({}, status_code=429)).discover_product(
        product=product, sources=[source]
    )

    assert unauthorized.status == "unauthorized"
    assert unauthorized.candidates == []
    assert rate_limited.status == "rate_limited"
    assert rate_limited.candidates == []


def test_brave_search_timeout_and_invalid_json_statuses(monkeypatch) -> None:
    monkeypatch.setenv(BRAVE_SEARCH_API_KEY_ENV_VAR, "fake-token")
    product = _product(mpn="UTG-12CH", manufacturer="Toyotomi")
    source = load_source_registry().get("skroutz")

    timeout = BraveSearchProvider(_brave_definition(), client=_TimeoutBraveClient()).discover_product(product=product, sources=[source])
    invalid_json = BraveSearchProvider(_brave_definition(), client=_InvalidJsonBraveClient()).discover_product(
        product=product, sources=[source]
    )

    assert timeout.status == "timeout"
    assert timeout.candidates == []
    assert invalid_json.status == "error"
    assert invalid_json.candidates == []


def _brave_definition(**overrides) -> SearchProviderDefinition:
    values = {
        "provider_name": "brave_search",
        "provider_type": "brave",
        "enabled": True,
        "allow_high_confidence_auto_apply": False,
        "endpoint_url": "https://api.search.brave.com/res/v1/web/search",
        "country": "GR",
        "search_lang": "el",
        "ui_lang": "el-GR",
        "count": 10,
        "safesearch": "moderate",
        "result_filter": "web",
        "spellcheck": False,
        "timeout_seconds": 10,
    }
    values.update(overrides)
    return SearchProviderDefinition(**values)


def _brave_response() -> dict:
    return {
        "web": {
            "results": [
                {
                    "url": "https://www.skroutz.gr/s/123456/Toyotomi-UTG-12CH.html?utm_source=brave",
                    "title": "Toyotomi UTG-12CH | Skroutz",
                    "description": "Skroutz product page",
                },
                {
                    "url": "https://www.bestprice.gr/item/987654/toyotomi-utg-12ch.html",
                    "title": "Toyotomi UTG-12CH | BestPrice",
                    "description": "BestPrice product page",
                },
                {
                    "url": "https://www.plaisio.gr/product/oikiakes-syskeues/klimatistika/toyotomi/klimatistiko-toyotomi-utg-12ch",
                    "title": "Toyotomi UTG-12CH | Plaisio",
                    "description": "Plaisio product page",
                },
                {
                    "url": "https://unknown.example/toyotomi-utg-12ch",
                    "title": "Unknown",
                    "description": "Unknown domain",
                },
                {
                    "url": "https://www.skroutz.gr/c/1492/klimatistika.html",
                    "title": "Skroutz category",
                    "description": "Category page",
                },
            ]
        }
    }


class _FakeBraveResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class _FakeBraveClient:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.requests: list[dict] = []

    def search(self, *, definition: SearchProviderDefinition, query: str, api_key: str):
        self.requests.append(
            {
                "endpoint_url": definition.endpoint_url,
                "definition": definition,
                "query": query,
                "api_key": api_key,
            }
        )
        return _FakeBraveResponse(self.payload, self.status_code)


class _TimeoutBraveClient:
    def search(self, *, definition: SearchProviderDefinition, query: str, api_key: str):
        del definition, query, api_key
        raise httpx.TimeoutException("timeout")


class _InvalidJsonResponse:
    status_code = 200

    def json(self):
        raise ValueError("bad json")


class _InvalidJsonBraveClient:
    def search(self, *, definition: SearchProviderDefinition, query: str, api_key: str):
        del definition, query, api_key
        return _InvalidJsonResponse()


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
