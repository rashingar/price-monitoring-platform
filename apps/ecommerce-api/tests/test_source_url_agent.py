import sys
import json
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.source_url_agent.browser import PageSnapshot  # noqa: E402
from ecommerce.source_url_agent.products import AgentProduct  # noqa: E402
from ecommerce.source_url_agent.products import read_products_from_csv  # noqa: E402
from ecommerce.source_url_agent.search import discover_source_evidence, generate_search_queries  # noqa: E402
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

    assert registry.default_cascade == ("browser_fallback",)
    provider = registry.get("browser_fallback")
    assert provider.provider_type == "browser"
    assert provider.enabled is True
    assert provider.allow_high_confidence_auto_apply is True
    assert [item.provider_name for item in registry.cascade_for_source("bestprice")] == ["browser_fallback"]


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

    result = discover_source_evidence(
        product=product,
        source=source,
        browser=browser,
        max_searches=1,
        max_candidates=1,
        rate_limit_seconds=0,
    )

    assert result.searched_queries == ["Bosch HBA514BS3"]
    assert result.searched_urls == [search_url]
    assert len(result.evidence) == 1
    provenance = result.evidence[0].to_json()["provider_provenance"]
    assert provenance["provider_name"] == "browser_fallback"
    assert provenance["search_url"] == search_url
    assert provenance["candidate_url"] == product_url


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
