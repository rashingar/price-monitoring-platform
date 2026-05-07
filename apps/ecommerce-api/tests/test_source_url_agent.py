import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.source_url_agent.products import read_products_from_csv  # noqa: E402
from ecommerce.source_url_agent.sources import load_source_registry  # noqa: E402


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
