from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.product_factory_batch import repository  # noqa: E402
from ecommerce.product_factory_batch.csv_parser import parse_product_factory_batch_csv  # noqa: E402
from ecommerce.product_factory_batch.service import SUPPORTED_BATCH_SOURCE_NAMES, run_batch_resolution_background  # noqa: E402
from ecommerce.product_factory_source_resolution import (  # noqa: E402
    PreferredSourceConfig,
    ProductFactorySourceResolver,
    SourceResolutionConfig,
)
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
    assert fetcher.queries
    assert any("skroutz.gr" in query for query in fetcher.queries)
    assert all("bestprice.gr" not in query and "electronet.gr" not in query for query in fetcher.queries)


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
