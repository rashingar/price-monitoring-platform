import csv
import json
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api import routes_price_monitoring  # noqa: E402
from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.artifacts import ARTIFACT_ROOTS_ENV_VAR  # noqa: E402
from ecommerce.file_editor import FILE_ROOTS_ENV_VAR  # noqa: E402
from ecommerce.ignore.product_ignore import PRICE_IGNORE_ENV_VAR, load_ignored_products  # noqa: E402
from ecommerce.price_monitoring.export import export_price_update_csv  # noqa: E402
from ecommerce.price_monitoring.review import (  # noqa: E402
    REVIEW_COLUMNS,
    PriceActionInput,
    PriceReviewError,
    apply_price_actions,
    load_price_review_rows,
    load_price_review_rows_from_observations,
    load_review_csv,
)


@pytest.fixture(autouse=True)
def _allow_monitoring_api_without_real_db(monkeypatch):
    monkeypatch.setattr(routes_price_monitoring, "require_database_ready_for_price_monitoring", lambda: None)


def _write_run(run_dir: Path, *, source: str = "skroutz") -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "selection_summary.json").write_text(
        json.dumps({"run_id": run_dir.name, "source": source}),
        encoding="utf-8",
    )
    (run_dir / "input.csv").write_text(
        "model,mpn,name,price\n"
        "005606,MPN-1,Product One,123.45\n"
        "123456,MPN-2,Product Two,100.00\n"
        "233374-233203,MPN-3,Bundle Product,90.00\n"
        "111111,MPN-4,No Competitor,50.00\n",
        encoding="utf-8",
    )
    enriched = run_dir / ("bestprice_enriched.csv" if source == "bestprice" else "skroutz_enriched.csv")
    if source == "bestprice":
        enriched.write_text(
            "model,mpn,bestprice_price,bestprice_url,bestprice_best_store,bestprice_best_store_price\n"
            "005606,MPN-1,119.90,https://bestprice.test/p1,Store A,119.90\n"
            "123456,MPN-2,120.00,https://bestprice.test/p2,Store B,120.00\n"
            "233374-233203,MPN-3,80.00,https://bestprice.test/p3,Store C,80.00\n"
            "111111,MPN-4,,,\n",
            encoding="utf-8",
        )
    else:
        enriched.write_text(
            "model,mpn,skroutz_price,skroutz_url,match_status\n"
            "005606,MPN-1,119.90,https://skroutz.test/p1,matched\n"
            "123456,MPN-2,120.00,https://skroutz.test/p2,matched\n"
            "233374-233203,MPN-3,80.00,https://skroutz.test/p3,matched\n"
            "111111,MPN-4,,https://skroutz.test/p4,error\n",
            encoding="utf-8",
        )
    return enriched


def _set_input_price(run_dir: Path, price: str, *, model: str = "005606") -> None:
    input_path = run_dir / "input.csv"
    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    for row in rows:
        if row.get("model") == model:
            row["price"] = price
    with input_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _db_observations() -> list[dict[str, object]]:
    return [
        {
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "skroutz",
            "competitor_name": "Store A",
            "competitor_price": "118.50",
            "own_price": "123.45",
            "product_url": "https://skroutz.test/db-p1",
            "match_status": "matched",
            "raw_observation": {"source_url": "https://skroutz.test/db-p1"},
        },
        {
            "model": "123456",
            "mpn": "MPN-2",
            "product_name": "Product Two",
            "source": "skroutz",
            "competitor_name": "Store B",
            "competitor_price": "120.00",
            "own_price": "100.00",
            "product_url": "https://skroutz.test/db-p2",
            "match_status": "matched",
            "raw_observation": {},
        },
    ]


def _install_db_observation_fallback(monkeypatch, observations: list[dict[str, object]]) -> None:
    @contextmanager
    def fake_session_scope(*_args, **_kwargs):
        yield object()

    def fake_list_price_observations(*_args, **_kwargs):
        return observations, len(observations)

    monkeypatch.setattr(routes_price_monitoring, "session_scope", fake_session_scope)
    monkeypatch.setattr(routes_price_monitoring, "list_price_observations", fake_list_price_observations)


def test_loading_review_rows_preserves_models_and_computes_deltas(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir)

    rows = load_price_review_rows(run_dir, enriched)

    assert [row.model for row in rows] == ["005606", "123456", "233374-233203", "111111"]
    assert rows[0].competitor_price == Decimal("119.90")
    assert rows[0].price_delta == Decimal("3.55")
    assert rows[0].price_delta_percent.quantize(Decimal("0.01")) == Decimal("2.88")
    assert rows[0].recommended_action == "match_price"
    assert rows[1].recommended_action == "ignore"
    assert rows[3].status == "not_exportable"
    assert rows[3].recommended_action == "ignore"


def test_bestprice_mapper_uses_existing_store_and_price_fields(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir, source="bestprice")

    rows = load_price_review_rows(run_dir)

    assert rows[0].source == "bestprice"
    assert rows[0].competitor_store == "Store A"
    assert rows[0].competitor_url == "https://bestprice.test/p1"
    assert rows[0].competitor_price == Decimal("119.90")


def test_loading_review_rows_from_db_observations_preserves_price_review_behavior(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir)
    enriched.unlink()

    rows = load_price_review_rows_from_observations(run_dir, _db_observations())

    assert rows[0].model == "005606"
    assert rows[0].source == "skroutz"
    assert rows[0].competitor_price == Decimal("118.50")
    assert rows[0].competitor_store == "Store A"
    assert rows[0].competitor_url == "https://skroutz.test/db-p1"
    assert rows[0].price_delta == Decimal("4.95")
    assert rows[0].recommended_action == "match_price"
    assert rows[1].recommended_action == "ignore"


def test_db_observations_build_top_three_listings_and_next_store_delta(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir)
    enriched.unlink()
    _set_input_price(run_dir, "94.90")
    observations = [
        {
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "skroutz",
            "competitor_name": "Our Marketplace Store",
            "competitor_price": "94.90",
            "own_price": "94.90",
            "product_url": "https://skroutz.test/our",
            "raw_observation": {},
        },
        {
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "skroutz",
            "competitor_name": "Next Store",
            "competitor_price": "99.90",
            "own_price": "94.90",
            "product_url": "https://skroutz.test/next",
            "raw_observation": {},
        },
        {
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "skroutz",
            "competitor_name": "Third Store",
            "competitor_price": "101.00",
            "own_price": "94.90",
            "product_url": "https://skroutz.test/third",
            "raw_observation": {},
        },
        {
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "skroutz",
            "competitor_name": "Fourth Store",
            "competitor_price": "105.00",
            "own_price": "94.90",
            "product_url": "https://skroutz.test/fourth",
            "raw_observation": {},
        },
    ]

    rows = load_price_review_rows_from_observations(run_dir, observations)

    assert rows[0].competitor_price == Decimal("94.90")
    assert rows[0].next_competitor_price == Decimal("99.90")
    assert rows[0].price_delta == Decimal("-5.00")
    assert rows[0].next_store_delta == Decimal("-5.00")
    assert rows[0].delta_basis == "next_store"
    assert [listing.store for listing in rows[0].top_listings or []] == [
        "Our Marketplace Store",
        "Next Store",
        "Third Store",
    ]
    assert rows[0].captured_listings_count == 4
    assert rows[0].listings_incomplete is False


def test_db_review_uses_persisted_listing_rows_before_primary_observations(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir)
    enriched.unlink()
    _set_input_price(run_dir, "180.90")
    observations = [
        {
            "id": 10,
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "skroutz",
            "competitor_name": "Collapsed Primary",
            "competitor_price": "999.00",
            "own_price": "180.90",
            "product_url": "https://skroutz.test/product",
            "raw_observation": {},
            "price_observation_listings": [
                {"id": 1, "price_observation_id": 10, "seller_name": "Store B", "price": "181.00", "seller_url": "https://store.test/b", "source": "skroutz"},
                {"id": 2, "price_observation_id": 10, "seller_name": "Store A", "price": "180.90", "seller_url": "https://store.test/a", "source": "skroutz"},
                {"id": 3, "price_observation_id": 10, "seller_name": "Store C", "price": "181.50", "seller_url": "https://store.test/c", "source": "skroutz"},
                {"id": 4, "price_observation_id": 10, "seller_name": "Store D", "price": "182.00", "seller_url": "https://store.test/d", "source": "skroutz"},
            ],
        }
    ]

    rows = load_price_review_rows_from_observations(run_dir, observations, include_all_listings=True)

    assert [listing.store for listing in rows[0].top_listings or []] == ["Store A", "Store B", "Store C"]
    assert rows[0].competitor_store == "Store A"
    assert rows[0].next_competitor_store == "Store B"
    assert rows[0].price_delta == Decimal("-0.10")
    assert rows[0].delta_basis == "next_store"
    assert rows[0].captured_listings_count == 4
    assert len(rows[0].all_listings or []) == 4


def test_near_equal_top_listing_uses_next_store_delta_basis(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir)
    enriched.unlink()
    _set_input_price(run_dir, "94.93")
    observations = [
        {
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "skroutz",
            "competitor_name": "Top Store",
            "competitor_price": "94.90",
            "own_price": "94.93",
            "product_url": "https://skroutz.test/top",
            "raw_observation": {},
        },
        {
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "skroutz",
            "competitor_name": "Next Store",
            "competitor_price": "99.90",
            "own_price": "94.93",
            "product_url": "https://skroutz.test/next",
            "raw_observation": {},
        },
    ]

    rows = load_price_review_rows_from_observations(run_dir, observations)

    assert rows[0].price_delta == Decimal("-4.97")
    assert rows[0].delta_basis == "next_store"


def test_skroutz_raw_payload_extraction_adds_listings(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir)
    enriched.unlink()
    _set_input_price(run_dir, "94.90")
    observations = [
        {
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "skroutz",
            "competitor_name": "Top Store",
            "competitor_price": "94.90",
            "own_price": "94.90",
            "product_url": "https://skroutz.test/top",
            "raw_observation": {
                "product_cards": [
                    {"shop_name": "Top Store", "final_price": "94.90", "shop_url": "https://skroutz.test/top"},
                    {"seller_name": "Raw Next", "price": "99.90", "seller_url": "https://skroutz.test/raw-next"},
                ]
            },
        }
    ]

    rows = load_price_review_rows_from_observations(run_dir, observations)

    assert [listing.store for listing in rows[0].top_listings or []] == ["Top Store", "Raw Next"]
    assert rows[0].price_delta == Decimal("-5.00")
    assert rows[0].delta_basis == "next_store"


def test_offer_observation_listing_fallback_adds_listings(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir)
    enriched.unlink()
    observations = [
        {
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "skroutz",
            "competitor_name": "Collapsed Primary",
            "competitor_price": "999.00",
            "own_price": "123.45",
            "product_url": "https://skroutz.test/product",
            "raw_observation": {},
            "offer_observation_listings": [
                {"seller_name": "Offer A", "price": "118.50", "seller_url": "https://offer.test/a", "source": "skroutz"},
                {"seller_name": "Offer B", "price": "119.90", "seller_url": "https://offer.test/b", "source": "skroutz"},
                {"seller_name": "Offer C", "price": "120.00", "seller_url": "https://offer.test/c", "source": "skroutz"},
            ],
        }
    ]

    rows = load_price_review_rows_from_observations(run_dir, observations)

    assert [listing.store for listing in rows[0].top_listings or []] == ["Offer A", "Offer B", "Offer C"]
    assert rows[0].competitor_price == Decimal("118.50")


def test_bestprice_raw_payload_extraction_adds_listings(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir, source="bestprice")
    enriched.unlink()
    observations = [
        {
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "bestprice",
            "competitor_name": "Best Store",
            "competitor_price": "94.90",
            "own_price": "94.90",
            "product_url": "https://bestprice.test/best",
            "raw_observation": {
                "bestprice_best_store": "Best Store",
                "bestprice_best_store_price": "94.90",
                "bestprice_best_store_url": "https://bestprice.test/best",
                "bestprice_next_store": "Next Best",
                "bestprice_next_store_price": "99.90",
                "bestprice_next_store_url": "https://bestprice.test/next",
                "stores": [
                    {"storeName": "Third Best", "finalPrice": "101.00", "url": "https://bestprice.test/third"},
                ],
            },
        }
    ]

    rows = load_price_review_rows_from_observations(run_dir, observations)

    assert [listing.store for listing in rows[0].top_listings or []] == ["Best Store", "Next Best", "Third Best"]
    assert rows[0].next_competitor_store == "Next Best"


def test_bestprice_raw_numbered_payload_extraction_adds_top_three(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir, source="bestprice")
    enriched.unlink()
    observations = [
        {
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "bestprice",
            "competitor_name": "Best Store",
            "competitor_price": "94.90",
            "own_price": "94.90",
            "product_url": "https://bestprice.test/product",
            "raw_observation": {
                "bestprice_store_1": "Best Store",
                "bestprice_store_1_price": "94.90",
                "bestprice_store_1_url": "https://bestprice.test/store-1",
                "bestprice_store_2": "Second Store",
                "bestprice_store_2_price": "99.90",
                "bestprice_store_2_url": "https://bestprice.test/store-2",
                "bestprice_store_3": "Third Store",
                "bestprice_store_3_price": "101.00",
                "bestprice_store_3_url": "https://bestprice.test/store-3",
            },
        }
    ]

    rows = load_price_review_rows_from_observations(run_dir, observations)

    assert [listing.store for listing in rows[0].top_listings or []] == ["Best Store", "Second Store", "Third Store"]


def test_generic_raw_payload_extraction_handles_unknown_shapes(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir)
    enriched.unlink()
    observations = [
        {
            "model": "005606",
            "mpn": "MPN-1",
            "product_name": "Product One",
            "source": "unknown-market",
            "competitor_name": "Known Store",
            "competitor_price": "94.90",
            "own_price": "94.90",
            "product_url": "https://market.test/known",
            "raw_observation": {
                "results": [
                    {"merchant": "Known Store", "price": "94.90", "url": "https://market.test/known"},
                    {"merchant": "Generic Next", "sale_price": "99.90", "href": "https://market.test/next"},
                ]
            },
        }
    ]

    rows = load_price_review_rows_from_observations(run_dir, observations)

    assert [listing.store for listing in rows[0].top_listings or []] == ["Known Store", "Generic Next"]


def test_malformed_raw_payloads_do_not_fail_review_loading(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir)
    enriched.unlink()
    observations = [
        {
            "model": "005606",
            "mpn": "MPN-1",
            "source": "skroutz",
            "competitor_name": "Store A",
            "competitor_price": "118.50",
            "own_price": "123.45",
            "product_url": "https://skroutz.test/a",
            "raw_observation": "not json",
        }
    ]

    rows = load_price_review_rows_from_observations(run_dir, observations)

    assert rows[0].competitor_price == Decimal("118.50")
    assert [listing.store for listing in rows[0].top_listings or []] == ["Store A"]
    assert rows[0].next_competitor_price is None


def test_top_three_listings_do_not_add_synthetic_current_row(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir)
    enriched.unlink()
    observations = [
        {
            "model": "005606",
            "mpn": "MPN-1",
            "source": "skroutz",
            "competitor_name": "Only Store",
            "competitor_price": "99.90",
            "own_price": "94.90",
            "product_url": "https://skroutz.test/only",
            "raw_observation": {},
        }
    ]

    rows = load_price_review_rows_from_observations(run_dir, observations)

    assert len(rows[0].top_listings or []) == 1
    assert rows[0].top_listings[0].store == "Only Store"
    assert rows[0].next_competitor_price is None
    assert rows[0].captured_listings_count == 1
    assert rows[0].listings_incomplete is True


def test_loading_bestprice_db_observation_uses_source_url_for_review_row(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir, source="bestprice")
    enriched.unlink()
    observations = [
        {
            "model": "005606",
            "mpn": "MPN-1",
            "source": "bestprice",
            "competitor_name": "eTranoulis",
            "competitor_price": "94.90",
            "own_price": "100.00",
            "product_url": "https://www.bestprice.gr/item/2159389060/product.html",
            "raw_observation": {
                "bestprice_best_store": "eTranoulis",
                "bestprice_best_store_price": "94.90",
                "bestprice_best_store_url": "https://www.bestprice.gr/to/160584639/product.html",
            },
        }
    ]

    rows = load_price_review_rows_from_observations(run_dir, observations)

    assert rows[0].competitor_store == "eTranoulis"
    assert rows[0].competitor_url == "https://www.bestprice.gr/to/160584639/product.html"
    assert rows[0].source_url == "https://www.bestprice.gr/item/2159389060/product.html"
    assert rows[0].to_api_dict()["source_url"] == "https://www.bestprice.gr/item/2159389060/product.html"


def test_loading_review_rows_from_db_observations_does_not_match_by_position(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    enriched = _write_run(run_dir)
    enriched.unlink()
    observations = [
        {
            "model": "999999",
            "mpn": "OTHER",
            "source": "bestprice",
            "competitor_name": "Other Store",
            "competitor_price": "1.00",
            "product_url": "https://bestprice.test/other",
            "raw_observation": {},
        }
    ]

    rows = load_price_review_rows_from_observations(run_dir, observations)

    assert rows[0].model == "005606"
    assert rows[0].competitor_price is None
    assert rows[0].competitor_store == ""
    assert rows[0].status == "not_exportable"
    assert "missing_or_invalid_competitor_price" in rows[0].warnings


def test_match_price_action_writes_review_artifacts(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir)
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "price_ignore.csv"))

    result = apply_price_actions(
        run_dir,
        [PriceActionInput(model="005606", selected_action="match_price")],
    )

    assert result.rows[0].target_price == Decimal("119.90")
    assert result.rows[0].status == "exportable"
    assert result.review_csv_path.exists()
    assert result.review_actions_path.exists()

    with result.review_csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == REVIEW_COLUMNS

    payload = json.loads(result.review_actions_path.read_text(encoding="utf-8"))
    assert payload["actions_count"] == 1
    assert payload["exportable_count"] == 1


def test_undercut_action_computes_target_price(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir)
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "price_ignore.csv"))

    result = apply_price_actions(
        run_dir,
        [PriceActionInput(model="005606", selected_action="undercut", undercut_amount=Decimal("1.00"))],
    )

    assert result.rows[0].target_price == Decimal("118.90")


def test_undercut_requires_positive_amount(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir)
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "price_ignore.csv"))

    with pytest.raises(PriceReviewError, match="greater than 0"):
        apply_price_actions(
            run_dir,
            [PriceActionInput(model="005606", selected_action="undercut", undercut_amount=Decimal("0"))],
        )


def test_ignore_action_updates_ignore_list_and_export_excludes_ignored(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir)
    ignore_path = tmp_path / "price_ignore.csv"
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(ignore_path))

    result = apply_price_actions(
        run_dir,
        [
            PriceActionInput(model="005606", selected_action="ignore", reason="manual ignore from price review"),
            PriceActionInput(model="123456", selected_action="match_price"),
        ],
    )

    ignored = load_ignored_products(ignore_path)
    assert [product.model for product in ignored] == ["005606"]

    export = export_price_update_csv(run_dir, result.rows)
    with export.output_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert rows == [{"model": "123456", "price": "120.00"}]


def test_composite_model_action_is_rejected(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir)
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "price_ignore.csv"))

    with pytest.raises(PriceReviewError, match="non-atomic"):
        apply_price_actions(
            run_dir,
            [PriceActionInput(model="233374-233203", selected_action="match_price")],
        )


def test_row_without_competitor_price_rejects_price_action(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir)
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "price_ignore.csv"))

    with pytest.raises(PriceReviewError, match="without valid competitor price"):
        apply_price_actions(run_dir, [PriceActionInput(model="111111", selected_action="match_price")])


def test_opencart_export_contains_only_model_and_price(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-1"
    _write_run(run_dir)
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "price_ignore.csv"))
    result = apply_price_actions(
        run_dir,
        [
            PriceActionInput(model="005606", selected_action="match_price"),
            PriceActionInput(model="123456", selected_action="undercut", undercut_amount=Decimal("1.00")),
        ],
    )

    export = export_price_update_csv(run_dir, result.rows)

    with export.output_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == ["model", "price"]
    assert rows == [{"model": "005606", "price": "119.90"}, {"model": "123456", "price": "119.00"}]


def test_export_endpoint_uses_review_csv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "price_ignore.csv"))
    apply_price_actions(run_dir, [PriceActionInput(model="005606", selected_action="match_price")])

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs/run-1/export-price-update",
        json={"review_csv_path": None, "output_path": None},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "price_update_exported"
    assert payload["rows_exported"] == 1
    assert payload["columns"] == ["model", "price"]
    assert payload["artifact"]["is_allowed"] is True
    assert payload["artifact"]["download_url"].startswith("/api/artifacts/download?path=")


def test_export_endpoint_rejects_unsafe_explicit_output_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "price_ignore.csv"))
    apply_price_actions(run_dir, [PriceActionInput(model="005606", selected_action="match_price")])
    unsafe_output = tmp_path / "custom" / "opencart_price_update.csv"

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs/run-1/export-price-update",
        json={"review_csv_path": None, "output_path": str(unsafe_output)},
    )

    assert response.status_code == 403
    assert "outside allowed artifact roots" in response.json()["detail"]
    assert not unsafe_output.exists()


def test_export_endpoint_rejects_output_path_that_is_only_file_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    custom_root = tmp_path / "custom"
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "price_ignore.csv"))
    monkeypatch.setenv(FILE_ROOTS_ENV_VAR, str(custom_root))
    apply_price_actions(run_dir, [PriceActionInput(model="005606", selected_action="match_price")])

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs/run-1/export-price-update",
        json={"review_csv_path": None, "output_path": str(custom_root / "opencart_price_update.csv")},
    )

    assert response.status_code == 403
    assert "outside allowed artifact roots" in response.json()["detail"]


def test_export_endpoint_allows_custom_output_when_artifact_root_configured(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    custom_root = tmp_path / "custom"
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "price_ignore.csv"))
    monkeypatch.setenv(ARTIFACT_ROOTS_ENV_VAR, f"{tmp_path / 'output' / 'ecommerce' / 'monitoring' / 'runs'};{custom_root}")
    apply_price_actions(run_dir, [PriceActionInput(model="005606", selected_action="match_price")])
    custom_output = custom_root / "opencart_price_update.csv"

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs/run-1/export-price-update",
        json={"review_csv_path": None, "output_path": str(custom_output)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["output_path"] == str(custom_output)
    assert payload["artifact"]["is_allowed"] is True
    assert custom_output.exists()


def test_get_review_rejects_unsafe_explicit_enriched_csv_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)
    unsafe_enriched = tmp_path / "custom" / "skroutz_enriched.csv"
    unsafe_enriched.parent.mkdir()
    unsafe_enriched.write_text("model,mpn,skroutz_price,skroutz_url,match_status\n", encoding="utf-8")

    response = TestClient(create_app()).get(
        "/api/price-monitoring/runs/run-1/review",
        params={"enriched_csv_path": str(unsafe_enriched)},
    )

    assert response.status_code == 403
    assert "outside allowed read roots" in response.json()["detail"]


def test_get_review_rejects_path_traversal_in_explicit_enriched_csv_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)

    response = TestClient(create_app()).get(
        "/api/price-monitoring/runs/run-1/review",
        params={"enriched_csv_path": str(Path("output") / "ecommerce" / "monitoring" / "runs" / "run-1" / ".." / "x.csv")},
    )

    assert response.status_code == 400
    assert "Path traversal" in response.json()["detail"]


def test_api_get_review_and_post_actions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "price_ignore.csv"))
    client = TestClient(create_app())

    get_response = client.get("/api/price-monitoring/runs/run-1/review")
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["items"][0]["model"] == "005606"
    assert get_payload["items"][0]["price_delta"] == 3.55
    assert get_payload["summary"] == {"total": 4, "review_required": 3, "not_exportable": 1}

    post_response = client.post(
        "/api/price-monitoring/runs/run-1/review/actions",
        json={
            "enriched_csv_path": None,
            "actions": [{"model": "005606", "selected_action": "undercut", "undercut_amount": 1.0}],
        },
    )

    assert post_response.status_code == 200
    post_payload = post_response.json()
    assert post_payload["status"] == "review_actions_applied"
    assert post_payload["summary"]["actions_count"] == 1
    assert Path(post_payload["review_csv_path"]).exists()
    assert post_payload["artifacts"][0]["is_allowed"] is True
    assert post_payload["artifacts"][0]["read_url"].startswith("/api/artifacts/read?path=")
    assert load_review_csv(Path(post_payload["review_csv_path"]))[0].target_price == Decimal("118.90")


def test_api_get_review_falls_back_to_db_observations_when_enriched_csv_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    enriched = _write_run(run_dir)
    enriched.unlink()
    _install_db_observation_fallback(monkeypatch, _db_observations())

    response = TestClient(create_app()).get("/api/price-monitoring/runs/run-1/review")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["model"] == "005606"
    assert payload["items"][0]["competitor_price"] == 118.5
    assert payload["items"][0]["competitor_store"] == "Store A"
    assert payload["items"][0]["competitor_url"] == "https://skroutz.test/db-p1"
    assert payload["summary"]["review_required"] == 2


def test_api_post_review_actions_falls_back_to_db_observations_when_enriched_csv_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    enriched = _write_run(run_dir)
    enriched.unlink()
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "price_ignore.csv"))
    _install_db_observation_fallback(monkeypatch, _db_observations())

    response = TestClient(create_app()).post(
        "/api/price-monitoring/runs/run-1/review/actions",
        json={
            "enriched_csv_path": None,
            "actions": [{"model": "005606", "selected_action": "match_price"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "review_actions_applied"
    assert load_review_csv(Path(payload["review_csv_path"]))[0].target_price == Decimal("118.50")
