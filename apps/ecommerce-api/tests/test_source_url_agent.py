import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.source_url_agent.products import AgentProduct  # noqa: E402
from ecommerce.source_url_agent.products import read_products_from_csv  # noqa: E402
from ecommerce.source_url_agent.search import generate_search_queries  # noqa: E402
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
