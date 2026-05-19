from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api import routes_product_factory_batches  # noqa: E402
from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.product_factory_batch import repository  # noqa: E402
from ecommerce.product_factory_batch.csv_parser import parse_product_factory_batch_csv  # noqa: E402
from ecommerce.product_factory_batch.service import SUPPORTED_BATCH_SOURCE_NAMES, run_batch_resolution_background  # noqa: E402
from ecommerce.product_factory_batch.enqueue import batch_auto_enqueue_confidence_threshold, row_is_enqueueable  # noqa: E402
from ecommerce.product_factory_source_resolution import (  # noqa: E402
    PreferredSourceConfig,
    ProductFactorySourceResolver,
    SourceResolutionConfig,
    SourceResolutionProduct,
)
from ecommerce.product_factory_source_resolution.queries import build_source_scoped_queries  # noqa: E402
from ecommerce.product_factory_source_resolution.scoring import score_candidate  # noqa: E402
from ecommerce.product_factory_source_resolution.urls import normalized_product_url  # noqa: E402
from ecommerce.product_factory_telegram.client import ProductFactoryClientError, ProductFactoryJob  # noqa: E402
from ecommerce.source_url_agent.brave_search import BraveSearchResultItem  # noqa: E402


def test_csv_parser_supports_semicolon_model_brand_name() -> None:
    parsed = parse_product_factory_batch_csv("model;brand;name\n000123; Brand ; Product Name \n")

    assert parsed.delimiter == ";"
    assert parsed.rows[0].model == "000123"
    assert parsed.rows[0].brand == "Brand"
    assert parsed.rows[0].name == "Product Name"


def test_upload_creates_batch_and_rows(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/product-factory-batches/upload",
        files={"file": ("batch.csv", b"model,brand,name\n000001,Brand,Alpha Mixer\n000002,Brand,Beta Toaster\n", "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_rows"] == 2
    assert payload["pending_count"] == 2
    assert [row["model"] for row in payload["preview_rows"]] == ["000001", "000002"]


def test_resolve_stores_candidates_and_review_statuses(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    fetcher = QueryFetcher()
    scheduled: list[tuple[int, tuple[str, ...]]] = []
    monkeypatch.setattr(
        "ecommerce.product_factory_batch.service._batch_resolver",
        lambda _path=None, *, source_names=None: ProductFactorySourceResolver(
            config=_resolution_config().with_preferred_sources(tuple(source_names or SUPPORTED_BATCH_SOURCE_NAMES)),
            fetcher=fetcher,
            source_scoped_queries=True,
        ),
    )
    monkeypatch.setattr(
        "ecommerce.api.routes_product_factory_batches._schedule_batch_resolution",
        lambda _background_tasks, *, batch_id, source_names: scheduled.append((batch_id, source_names)),
    )
    batch_id = _upload_batch(
        client,
        "model,brand,name\n000001,Brand,Alpha Mixer\n000002,Brand,Beta Toaster\n000003,Brand,Gamma Kettle\n",
    )

    response = client.post(f"/api/product-factory-batches/{batch_id}/resolve")

    assert response.status_code == 200
    started = response.json()
    assert started["status"] == "resolving"
    assert started["metadata"]["selected_source_names"] == list(SUPPORTED_BATCH_SOURCE_NAMES)
    assert [row["status"] for row in started["rows"]] == ["pending", "pending", "pending"]
    assert scheduled == [(batch_id, SUPPORTED_BATCH_SOURCE_NAMES)]

    run_batch_resolution_background(batch_id=batch_id, source_names=scheduled[0][1])

    resolved = client.get(f"/api/product-factory-batches/{batch_id}").json()
    rows = client.get(f"/api/product-factory-batches/{batch_id}/rows").json()["items"]
    assert resolved["status"] == "resolved"
    assert rows[0]["status"] == "auto_selected"
    assert rows[0]["selected_source"] == "electronet"
    assert rows[0]["candidates"][0]["url"] == "https://www.electronet.gr/a/b/c/brand-alpha-mixer"
    assert rows[1]["status"] == "needs_review"
    assert rows[1]["selected_url"] is None
    assert rows[1]["candidates"][0]["source_name"] == "bestprice"
    assert rows[2]["status"] == "no_usable_source"
    assert rows[2]["selected_url"] is None
    assert all("00000" not in query for query in fetcher.queries)
    assert any("Brand Alpha Mixer site:electronet.gr" == query for query in fetcher.queries)
    assert "Brand Alpha Mixer" not in fetcher.queries


def test_resolve_accepts_and_persists_selected_sources(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    fetcher = QueryFetcher()
    seen_source_names: list[tuple[str, ...]] = []
    scheduled: list[tuple[int, tuple[str, ...]]] = []

    def fake_resolver(_path=None, *, source_names=None):
        selected = tuple(source_names or SUPPORTED_BATCH_SOURCE_NAMES)
        seen_source_names.append(selected)
        return ProductFactorySourceResolver(
            config=_resolution_config().with_preferred_sources(selected),
            fetcher=fetcher,
            source_scoped_queries=True,
        )

    monkeypatch.setattr("ecommerce.product_factory_batch.service._batch_resolver", fake_resolver)
    monkeypatch.setattr(
        "ecommerce.api.routes_product_factory_batches._schedule_batch_resolution",
        lambda _background_tasks, *, batch_id, source_names: scheduled.append((batch_id, source_names)),
    )
    batch_id = _upload_batch(client, "model,brand,name\n000001,Brand,Alpha Mixer\n")

    response = client.post(f"/api/product-factory-batches/{batch_id}/resolve", json={"source_names": ["skroutz"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "resolving"
    assert payload["metadata"]["selected_source_names"] == ["skroutz"]
    assert payload["metadata"]["selected_source_labels"] == ["Skroutz"]
    assert scheduled == [(batch_id, ("skroutz",))]

    run_batch_resolution_background(batch_id=batch_id, source_names=scheduled[0][1])

    rows = client.get(f"/api/product-factory-batches/{batch_id}/rows").json()["items"]
    assert seen_source_names == [("skroutz",)]
    assert rows[0]["selected_source"] == "skroutz"
    assert rows[0]["candidates"]
    assert {candidate["source_name"] for candidate in rows[0]["candidates"]} == {"skroutz"}
    assert fetcher.queries == ["Brand Alpha Mixer site:skroutz.gr"]
    assert all("bestprice.gr" not in query and "electronet.gr" not in query for query in fetcher.queries)


def test_source_scoped_queries_do_not_append_general_search() -> None:
    product = SourceResolutionProduct(model="409966", brand="INVENTOR", name="L4VI32-12WiFiR")
    config = _resolution_config().with_preferred_sources(("skroutz",))

    queries = build_source_scoped_queries(product, config)

    assert queries == ["INVENTOR L4VI32-12WiFiR site:skroutz.gr"]


def test_sku_scoring_selects_exact_skroutz_result_without_full_wifi_suffix() -> None:
    source = _skroutz_source(weight=70)
    product = SourceResolutionProduct(model="409965", brand="INVENTOR", name="L4VI32-09WiFiR")
    correct = _brave_item("https://www.skroutz.gr/s/11863799/Inventor-Life-Pro-L4VI32-09-L4VO32-09.html", "Inventor Life Pro L4VI32-09 / L4VO32-09 - Skroutz.gr", rank=1)
    wrong = _brave_item("https://www.skroutz.gr/s/14825092/Inventor-Omnia-Eco-O3MVI32-09WiFiR-O3MVO32-09.html", "Inventor Omnia Eco O3MVI32-09WiFiR/O3MVO32-09 - Skroutz.gr", rank=1)

    correct_score = score_candidate(product=product, source=source, item=correct, url=correct.url)
    wrong_score = score_candidate(product=product, source=source, item=wrong, url=wrong.url)

    assert correct_score >= 70
    assert correct_score > wrong_score


def test_sku_scoring_keeps_partial_variant_under_auto_threshold() -> None:
    source = _skroutz_source(weight=70)
    product = SourceResolutionProduct(model="412785", brand="INVENTOR", name="SUVI-18WFIB SUPREME UVC")
    partial_variant = _brave_item("https://www.skroutz.gr/s/31959533/Inventor-Supreme-SUVI-18WFI-SUVO-18.html", "Inventor Supreme SUVI-18WFI/SUVO-18 - Skroutz.gr", rank=1)

    score = score_candidate(product=product, source=source, item=partial_variant, url=partial_variant.url)

    assert score < 70


def test_skroutz_discussion_urls_are_not_product_candidates() -> None:
    source = _skroutz_source(weight=70)
    discussion_url = "https://www.skroutz.gr/s/40982178/Inventor-Neo-2-N2UVI-12WFI-N2UVO-12/discussion"

    assert normalized_product_url(discussion_url, source) == ""


def test_resolve_rejects_invalid_and_empty_source_names(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    batch_id = _upload_batch(client, "model,brand,name\n000001,Brand,Alpha Mixer\n")

    invalid = client.post(f"/api/product-factory-batches/{batch_id}/resolve", json={"source_names": ["skroutz", "plaisio"]})
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "invalid_batch_source_names"

    empty = client.post(f"/api/product-factory-batches/{batch_id}/resolve", json={"source_names": []})
    assert empty.status_code == 400
    assert empty.json()["detail"]["code"] == "invalid_batch_source_names"


def test_resolve_does_not_start_duplicate_or_conflicting_runs(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    scheduled: list[tuple[int, tuple[str, ...]]] = []
    monkeypatch.setattr(
        "ecommerce.api.routes_product_factory_batches._schedule_batch_resolution",
        lambda _background_tasks, *, batch_id, source_names: scheduled.append((batch_id, source_names)),
    )
    batch_id = _upload_batch(client, "model,brand,name\n000001,Brand,Alpha Mixer\n")

    first = client.post(f"/api/product-factory-batches/{batch_id}/resolve", json={"source_names": ["skroutz"]})
    duplicate = client.post(f"/api/product-factory-batches/{batch_id}/resolve", json={"source_names": ["skroutz"]})
    conflict = client.post(f"/api/product-factory-batches/{batch_id}/resolve", json={"source_names": ["bestprice"]})

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "batch_resolution_conflict"
    assert scheduled == [(batch_id, ("skroutz",))]


def test_background_resolution_preserves_skipped_and_manual_rows(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    fetcher = QueryFetcher()
    monkeypatch.setattr(
        "ecommerce.product_factory_batch.service._batch_resolver",
        lambda _path=None, *, source_names=None: ProductFactorySourceResolver(
            config=_resolution_config().with_preferred_sources(tuple(source_names or SUPPORTED_BATCH_SOURCE_NAMES)),
            fetcher=fetcher,
            source_scoped_queries=True,
        ),
    )
    batch_id = _upload_batch(client, "model,brand,name\n000001,Brand,Alpha Mixer\n000002,Brand,Beta Toaster\n000003,Brand,Gamma Kettle\n")
    with session_scope() as session:
        rows = repository.list_batch_rows(session, batch_id)
        rows[0].status = "skipped"
        rows[0].selection_metadata_json = {"selection_method": "skipped"}
        rows[1].status = "manually_selected"
        rows[1].selected_url = "https://www.bestprice.gr/item/123/manual.html"
        rows[1].selected_source = "bestprice"
        rows[1].confidence = 100
        rows[1].selection_metadata_json = {"selection_method": "manual_url"}
        batch = repository.get_batch(session, batch_id)
        assert batch is not None
        repository.refresh_batch_counts(session, batch)

    run_batch_resolution_background(batch_id=batch_id, source_names=SUPPORTED_BATCH_SOURCE_NAMES)

    rows = client.get(f"/api/product-factory-batches/{batch_id}/rows").json()["items"]
    assert rows[0]["status"] == "skipped"
    assert rows[0]["selected_url"] is None
    assert rows[1]["status"] == "manually_selected"
    assert rows[1]["selected_url"] == "https://www.bestprice.gr/item/123/manual.html"
    assert rows[2]["status"] == "no_usable_source"


def test_enqueue_selected_enqueues_eligible_rows_and_forces_low_confidence_review(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    fake_product_factory = FakeProductFactoryClient()
    monkeypatch.setenv("PRODUCT_FACTORY_BATCH_AUTO_ENQUEUE_CONFIDENCE_THRESHOLD", "85")
    monkeypatch.setattr(routes_product_factory_batches, "_product_factory_client", lambda: fake_product_factory)
    batch_id = _upload_batch(
        client,
        "model,brand,name\n000001,Brand,Manual Product\n000002,Brand,High Confidence\n000003,Brand,Low Confidence\n000004,Brand,Needs Review\n",
    )
    with session_scope() as session:
        batch = repository.get_batch(session, batch_id)
        assert batch is not None
        rows = repository.list_batch_rows(session, batch_id)
        _select_row(rows[0], status="manually_selected", confidence=100, url="https://www.skroutz.gr/s/1/manual.html")
        _select_row(rows[1], status="auto_selected", confidence=91, url="https://www.skroutz.gr/s/2/high.html")
        _select_row(rows[2], status="auto_selected", confidence=70, url="https://www.skroutz.gr/s/3/low.html")
        rows[3].status = "needs_review"
        assert row_is_enqueueable(rows[0], threshold=85)
        assert row_is_enqueueable(rows[1], threshold=85)
        assert not row_is_enqueueable(rows[2], threshold=85)
        assert not row_is_enqueueable(rows[3], threshold=85)
        repository.refresh_batch_counts(session, batch)

    response = client.post(f"/api/product-factory-batches/{batch_id}/enqueue-selected")

    assert response.status_code == 200
    payload = response.json()
    assert payload["threshold"] == 85
    assert payload["enqueued_count"] == 2
    assert payload["forced_needs_review_count"] == 1
    assert payload["failed_count"] == 0
    assert len(fake_product_factory.start_payloads) == 2
    first_payload = fake_product_factory.start_payloads[0]
    assert first_payload["model"] == "000001"
    assert first_payload["product_name"] == "Manual Product"
    assert first_payload["source_url"] == "https://www.skroutz.gr/s/1/manual.html"
    assert first_payload["photos"] == 100
    assert first_payload["sections"] == 20
    assert first_payload["gallery_mode"] == "all"
    assert first_payload["bestprice_enabled"] is False
    assert first_payload["skroutz_enabled"] is False
    assert first_payload["boxnow_enabled"] is False
    assert first_payload["trigger_source"] == "csv_batch"
    assert first_payload["source_resolution"]["batch_id"] == batch_id
    assert first_payload["source_resolution"]["selected_source"] == "skroutz"
    low_row = next(row for row in payload["rows"] if row["model"] == "000003")
    assert low_row["status"] == "needs_review"
    assert low_row["selected_url"] == "https://www.skroutz.gr/s/3/low.html"
    assert low_row["selection_metadata"]["selection_method"] == "auto_selected_below_enqueue_threshold"
    enqueued_rows = [row for row in payload["rows"] if row["product_factory_job_id"]]
    assert {row["model"] for row in enqueued_rows} == {"000001", "000002"}


def test_row_enqueue_forces_low_confidence_auto_selected_to_review_and_rejects(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("PRODUCT_FACTORY_BATCH_AUTO_ENQUEUE_CONFIDENCE_THRESHOLD", "85")
    monkeypatch.setattr(routes_product_factory_batches, "_product_factory_client", lambda: FakeProductFactoryClient())
    batch_id = _upload_batch(client, "model,brand,name\n000001,Brand,Low Confidence\n")
    with session_scope() as session:
        batch = repository.get_batch(session, batch_id)
        assert batch is not None
        row = repository.list_batch_rows(session, batch_id)[0]
        _select_row(row, status="auto_selected", confidence=84, url="https://www.skroutz.gr/s/1/low.html")
        repository.refresh_batch_counts(session, batch)
        row_id = row.id

    response = client.post(f"/api/product-factory-batches/{batch_id}/rows/{row_id}/enqueue")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "batch_row_not_enqueueable"
    rows = client.get(f"/api/product-factory-batches/{batch_id}/rows").json()["items"]
    assert rows[0]["status"] == "needs_review"
    assert rows[0]["selection_metadata"]["requires_manual_review"] is True


def test_row_enqueue_is_idempotent_for_existing_job(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    fake_product_factory = FakeProductFactoryClient()
    monkeypatch.setattr(routes_product_factory_batches, "_product_factory_client", lambda: fake_product_factory)
    batch_id = _upload_batch(client, "model,brand,name\n000001,Brand,Already Enqueued\n")
    with session_scope() as session:
        batch = repository.get_batch(session, batch_id)
        assert batch is not None
        row = repository.list_batch_rows(session, batch_id)[0]
        _select_row(row, status="manually_selected", confidence=100, url="https://www.skroutz.gr/s/1/manual.html")
        row.product_factory_job_id = "job-existing"
        row.product_factory_job_status = "queued"
        repository.refresh_batch_counts(session, batch)
        row_id = row.id

    response = client.post(f"/api/product-factory-batches/{batch_id}/rows/{row_id}/enqueue")

    assert response.status_code == 200
    assert response.json()["product_factory_job_id"] == "job-existing"
    assert fake_product_factory.start_payloads == []


def test_row_enqueue_stores_product_factory_errors(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(routes_product_factory_batches, "_product_factory_client", lambda: FakeProductFactoryClient(fail_start=True))
    batch_id = _upload_batch(client, "model,brand,name\n000001,Brand,Manual Product\n")
    with session_scope() as session:
        batch = repository.get_batch(session, batch_id)
        assert batch is not None
        row = repository.list_batch_rows(session, batch_id)[0]
        _select_row(row, status="manually_selected", confidence=100, url="https://www.skroutz.gr/s/1/manual.html")
        repository.refresh_batch_counts(session, batch)
        row_id = row.id

    response = client.post(f"/api/product-factory-batches/{batch_id}/rows/{row_id}/enqueue")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "product_factory_enqueue_failed"
    rows = client.get(f"/api/product-factory-batches/{batch_id}/rows").json()["items"]
    assert rows[0]["product_factory_error_code"] == "product_factory_enqueue_failed"
    assert "no job was started" in rows[0]["product_factory_error_message"]


def test_refresh_job_statuses_updates_rows_and_continues_after_failure(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    fake_product_factory = FakeProductFactoryClient(fail_get_ids={"job-fail"})
    monkeypatch.setattr(routes_product_factory_batches, "_product_factory_client", lambda: fake_product_factory)
    batch_id = _upload_batch(client, "model,brand,name\n000001,Brand,Good Job\n000002,Brand,Bad Job\n")
    with session_scope() as session:
        batch = repository.get_batch(session, batch_id)
        assert batch is not None
        rows = repository.list_batch_rows(session, batch_id)
        _select_row(rows[0], status="manually_selected", confidence=100, url="https://www.skroutz.gr/s/1/good.html")
        rows[0].product_factory_job_id = "job-good"
        rows[0].product_factory_job_status = "queued"
        _select_row(rows[1], status="manually_selected", confidence=100, url="https://www.skroutz.gr/s/2/bad.html")
        rows[1].product_factory_job_id = "job-fail"
        rows[1].product_factory_job_status = "queued"
        repository.refresh_batch_counts(session, batch)

    response = client.post(f"/api/product-factory-batches/{batch_id}/refresh-job-statuses")

    assert response.status_code == 200
    payload = response.json()
    assert payload["refreshed_count"] == 1
    assert payload["failed_count"] == 1
    by_model = {row["model"]: row for row in payload["rows"]}
    assert by_model["000001"]["product_factory_job_status"] == "succeeded"
    assert by_model["000001"]["product_factory_job_message"] == "Done"
    assert by_model["000002"]["product_factory_error_code"] == "product_factory_status_refresh_failed"
    assert fake_product_factory.get_job_calls == ["job-good", "job-fail"]


def test_enqueue_eligibility_threshold_env(monkeypatch) -> None:
    monkeypatch.setenv("PRODUCT_FACTORY_BATCH_AUTO_ENQUEUE_CONFIDENCE_THRESHOLD", "not-an-int")
    assert batch_auto_enqueue_confidence_threshold() == 85
    monkeypatch.setenv("PRODUCT_FACTORY_BATCH_AUTO_ENQUEUE_CONFIDENCE_THRESHOLD", "101")
    assert batch_auto_enqueue_confidence_threshold() == 85
    monkeypatch.setenv("PRODUCT_FACTORY_BATCH_AUTO_ENQUEUE_CONFIDENCE_THRESHOLD", "70")
    assert batch_auto_enqueue_confidence_threshold() == 70


def test_row_resolution_commits_in_progress_status_before_search(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    batch_id = _upload_batch(client, "model,brand,name\n000001,Brand,Alpha Mixer\n")
    fetcher = InspectingFetcher(batch_id=batch_id)
    monkeypatch.setattr(
        "ecommerce.product_factory_batch.service._batch_resolver",
        lambda _path=None, *, source_names=None: ProductFactorySourceResolver(
            config=_resolution_config().with_preferred_sources(tuple(source_names or SUPPORTED_BATCH_SOURCE_NAMES)),
            fetcher=fetcher,
            source_scoped_queries=True,
        ),
    )

    run_batch_resolution_background(batch_id=batch_id, source_names=("skroutz",))

    assert ["resolving_source"] in fetcher.status_snapshots
    rows = client.get(f"/api/product-factory-batches/{batch_id}/rows").json()["items"]
    assert rows[0]["status"] == "no_usable_source"


def test_manual_source_selection_validates_supported_product_urls(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "ecommerce.product_factory_batch.service._batch_resolver",
        lambda _path=None, *, source_names=None: ProductFactorySourceResolver(
            config=_resolution_config().with_preferred_sources(tuple(source_names or SUPPORTED_BATCH_SOURCE_NAMES)),
            fetcher=QueryFetcher(),
            source_scoped_queries=True,
        ),
    )
    batch_id = _upload_batch(client, "model,brand,name\n000002,Brand,Beta Toaster\n")
    assert client.post(f"/api/product-factory-batches/{batch_id}/resolve").status_code == 200
    rows = client.get(f"/api/product-factory-batches/{batch_id}/rows").json()["items"]
    row_id = rows[0]["id"]
    candidate_url = rows[0]["candidates"][0]["url"]

    unsupported = client.post(
        f"/api/product-factory-batches/{batch_id}/rows/{row_id}/select-source",
        json={"manual_url": "https://example.com/product"},
    )
    assert unsupported.status_code == 400
    assert unsupported.json()["detail"]["code"] == "unsupported_source_url"

    selected = client.post(
        f"/api/product-factory-batches/{batch_id}/rows/{row_id}/select-source",
        json={"candidate_url": candidate_url},
    )

    assert selected.status_code == 200
    payload = selected.json()
    assert payload["status"] == "manually_selected"
    assert payload["selected_source"] == "bestprice"
    assert payload["selected_url"] == candidate_url


def test_generic_resolver_preserves_telegram_adapter_behavior() -> None:
    from ecommerce.product_factory_telegram.source_resolution import ProductFactorySourceResolver as TelegramResolver
    from ecommerce.product_factory_telegram.warehouse import WarehouseProduct

    product = WarehouseProduct(
        model="012345",
        name="Brand Alpha Mixer",
        metadata={"manufacturer": "Brand", "mpn": "MPN-1", "barcode": "5200000000000", "category": "Mixers"},
    )
    resolver = TelegramResolver(
        config=_resolution_config(),
        fetcher=StaticFetcher(
            [_brave_item("https://www.electronet.gr/a/b/c/brand-mpn-1", "Brand MPN-1 Alpha Mixer", rank=1)]
        ),
    )

    result = resolver.resolve(product=product)

    assert result.selected is not None
    assert result.selected.source_name == "electronet"
    assert result.queries[0] == '"MPN-1" Brand Brand Alpha Mixer'


class StaticFetcher:
    def __init__(self, items: list[BraveSearchResultItem]) -> None:
        self.items = items

    def search(self, query: str, *, max_results: int) -> list[BraveSearchResultItem]:
        del query
        return self.items[:max_results]


class QueryFetcher:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, *, max_results: int) -> list[BraveSearchResultItem]:
        self.queries.append(query)
        if "Alpha Mixer" in query and "electronet.gr" in query:
            return [_brave_item("https://www.electronet.gr/a/b/c/brand-alpha-mixer", "Brand Alpha Mixer", rank=1)][:max_results]
        if "Alpha Mixer" in query and "skroutz.gr" in query:
            return [_brave_item("https://www.skroutz.gr/s/123/brand-alpha-mixer.html", "Brand Alpha Mixer", rank=1)][:max_results]
        if "Beta Toaster" in query and "bestprice.gr" in query:
            return [_brave_item("https://www.bestprice.gr/item/123/brand-beta-toaster.html", "Brand Beta Toaster", rank=1)][:max_results]
        return []


class InspectingFetcher:
    def __init__(self, *, batch_id: int) -> None:
        self.batch_id = batch_id
        self.status_snapshots: list[list[str]] = []

    def search(self, query: str, *, max_results: int) -> list[BraveSearchResultItem]:
        del query, max_results
        with session_scope() as session:
            self.status_snapshots.append([row.status for row in repository.list_batch_rows(session, self.batch_id)])
        return []


class FakeProductFactoryClient:
    def __init__(self, *, fail_start: bool = False, fail_get_ids: set[str] | None = None) -> None:
        self.fail_start = fail_start
        self.fail_get_ids = fail_get_ids or set()
        self.start_payloads: list[dict[str, Any]] = []
        self.get_job_calls: list[str] = []

    def start_full_pipeline(self, payload: dict[str, Any]) -> ProductFactoryJob:
        self.start_payloads.append(payload)
        if self.fail_start:
            raise ProductFactoryClientError("Product Factory API is unavailable; no job was started.")
        job_number = len(self.start_payloads)
        return ProductFactoryJob(job_id=f"job-{job_number}", status="queued", message="Queued", raw={"job_id": f"job-{job_number}", "status": "queued"})

    def get_job(self, job_id: str) -> ProductFactoryJob:
        self.get_job_calls.append(job_id)
        if job_id in self.fail_get_ids:
            raise ProductFactoryClientError(f"Product Factory job {job_id} was not found.")
        return ProductFactoryJob(job_id=job_id, status="succeeded", message="Done", raw={"job_id": job_id, "status": "succeeded", "message": "Done"})


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    return TestClient(create_app())


def _upload_batch(client: TestClient, csv_text: str) -> int:
    response = client.post(
        "/api/product-factory-batches/upload",
        files={"file": ("batch.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    return int(response.json()["id"])


def _select_row(row: Any, *, status: str, confidence: int, url: str) -> None:
    row.status = status
    row.selected_url = url
    row.selected_source = "skroutz"
    row.confidence = confidence
    row.candidate_urls_json = [
        {
            "source_name": "skroutz",
            "url": url,
            "title": row.name,
            "confidence": confidence,
            "result_rank": 1,
        }
    ]
    row.selection_metadata_json = {"selection_method": status}


def _resolution_config() -> SourceResolutionConfig:
    return SourceResolutionConfig(
        minimum_confidence=70,
        suggestion_confidence=40,
        max_suggestions=5,
        pending_choice_ttl_minutes=15,
        preferred_sources=(
            PreferredSourceConfig("electronet", 100, ("electronet.gr", "www.electronet.gr"), ("electronet",), ("/",)),
            PreferredSourceConfig("skroutz", 100, ("skroutz.gr", "www.skroutz.gr"), ("skroutz",), ("/s/",)),
            PreferredSourceConfig("bestprice", 50, ("bestprice.gr", "www.bestprice.gr"), ("bestprice",), ("/",)),
        ),
    )


def _skroutz_source(*, weight: int) -> PreferredSourceConfig:
    return PreferredSourceConfig("skroutz", weight, ("skroutz.gr", "www.skroutz.gr"), ("skroutz",), ("/s/",))


def _brave_item(url: str, title: str, *, rank: int) -> BraveSearchResultItem:
    return BraveSearchResultItem(
        url=url,
        title=title,
        description=f"{title} product page",
        extra_snippets=(f"{title} barcode 5200000000000",),
        profile={},
        fetch_metadata={},
        rank=rank,
    )
