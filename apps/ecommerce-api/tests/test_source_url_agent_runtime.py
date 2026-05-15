import csv
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.api.source_url_agent import runs as source_url_agent_run_routes  # noqa: E402
from ecommerce.api.source_url_agent import state as source_url_agent_api_state  # noqa: E402
from ecommerce.api.source_url_agent import validation as source_url_agent_api_validation  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base  # noqa: E402
from ecommerce.db.models.jobs import EcommerceJob  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.source_urls import (  # noqa: E402
    SourceUrl,
    SourceUrlCandidate,
    SourceUrlDiscoveryRun,
    SourceUrlDiscoveryTask,
)
from ecommerce.db.repositories.jobs import create_queued_job, get_job_by_id, mark_running  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.jobs import source_url_agent as source_url_agent_job  # noqa: E402
from ecommerce.jobs.worker import build_default_registry, run_worker_iteration  # noqa: E402
from ecommerce.source_url_agent.agent import SourceUrlAgentOptions, run_source_url_agent  # noqa: E402
from ecommerce.source_url_agent.artifacts import write_run_artifacts  # noqa: E402
from ecommerce.source_url_agent.candidates import candidate_from_evidence  # noqa: E402
from ecommerce.source_url_agent.evidence import PageEvidence, error_evidence, extract_page_evidence  # noqa: E402
from ecommerce.source_url_agent import job_handler as source_url_agent_job_handler  # noqa: E402
from ecommerce.source_url_agent.products import AgentProduct  # noqa: E402
from ecommerce.source_url_agent.progress import (  # noqa: E402
    SOURCE_URL_AGENT_JOB_TYPE,
    SOURCE_URL_AGENT_PROGRESS_STEP_DEFINITIONS,
    SOURCE_URL_AGENT_PROGRESS_STEP_IDS,
    SOURCE_URL_AGENT_PROGRESS_STEP_LABELS,
    SourceUrlAgentProgressReporter,
)
from ecommerce.source_url_agent.scoring import score_candidate  # noqa: E402
from ecommerce.source_url_agent.search import SourceSearchResult  # noqa: E402
from ecommerce.source_url_agent.search_providers import SearchProviderDefinition  # noqa: E402
from ecommerce.source_url_agent.sources import load_source_registry  # noqa: E402


NOW = datetime(2026, 5, 3, 12, tzinfo=timezone.utc)


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _create_schema(database_url: str) -> None:
    Base.metadata.create_all(get_engine(database_url))


def _product(**overrides) -> AgentProduct:
    values = {
        "catalog_product_id": None,
        "catalog_source": "sourceCata",
        "model": "005606",
        "mpn": "MR25GB",
        "name": "LG MR25GB Magic Remote Control",
        "category": "ΕΙΚΟΝΑ & ΗΧΟΣ///Αξεσουάρ///TV Control",
        "manufacturer": "LG",
        "price": None,
        "quantity": 1,
        "status": 1,
        "bestprice_status": 1,
        "skroutz_status": 1,
    }
    values.update(overrides)
    return AgentProduct(**values)


def _catalog_product(session, *, model: str = "005606", mpn: str = "MR25GB") -> CatalogProductRow:
    row = CatalogProductRow(
        catalog_source="sourceCata",
        model=model,
        mpn=mpn,
        name="LG MR25GB Magic Remote Control",
        category="ΕΙΚΟΝΑ & ΗΧΟΣ///Αξεσουάρ///TV Control",
        raw_category="ΕΙΚΟΝΑ & ΗΧΟΣ///Αξεσουάρ///TV Control",
        manufacturer="LG",
        status=1,
        active=True,
        imported_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def _html(*, include_mpn: bool = True, title: str = "LG MR25GB Magic Remote Control") -> str:
    mpn = "MR25GB" if include_mpn else "OTHER"
    return f"""
    <html>
      <head>
        <title>{title}</title>
        <link rel="canonical" href="https://www.skroutz.gr/s/123/LG-MR25GB.html" />
        <script type="application/ld+json">
        {{
          "@type": "Product",
          "name": "{title}",
          "brand": {{"name": "LG"}},
          "mpn": "{mpn}",
          "category": "TV Control",
          "offers": {{"price": "19.00", "priceCurrency": "EUR"}}
        }}
        </script>
      </head>
      <body>Brand LG MPN {mpn} TV Control 19,00 €</body>
    </html>
    """


def _candidate(product: AgentProduct, source_name: str = "skroutz"):
    source = load_source_registry().get(source_name)
    evidence = extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        html_text=_html(),
    )
    score = score_candidate(product=product, source=source, evidence=evidence)
    return candidate_from_evidence(
        run_id="run-1",
        product=product,
        source=source,
        evidence=evidence,
        score=score,
        expected_listing="listed",
        competing_candidates_count=0,
        searched_queries=["MR25GB"],
    )


def test_source_url_agent_scores_marketplace_meta_description_evidence_as_review() -> None:
    product = _product(
        mpn="CTN/CTG-356W",
        name="Toyotomi CTN/CTG-356W air conditioner",
        manufacturer="Toyotomi",
    )
    source = load_source_registry().get("bestprice")
    evidence = extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.bestprice.gr/item/2158816161/toyotomi-erai.html",
        final_url="https://www.bestprice.gr/item/2158816161/toyotomi-erai.html",
        html_text="""
        <html>
          <head>
            <title>BestPrice.gr</title>
            <link rel="canonical" href="https://www.bestprice.gr/item/2158816161/toyotomi-erai.html" />
            <meta name="description" content="Toyotomi CTN/CTG-356W Κλιματιστικό Inverter 18000 BTU" />
          </head>
          <body></body>
        </html>
        """,
    )
    score = score_candidate(product=product, source=source, evidence=evidence)

    assert evidence.exact_mpn_found
    assert evidence.exact_mpn_source == "meta"
    assert evidence.brand_found
    assert score.match_status == "needs_review"
    assert score.confidence_score == 0.88


def test_source_url_agent_keeps_inaccessible_url_mpn_brand_evidence_for_review() -> None:
    product = _product(
        mpn="CTN/CTG-356W",
        name="Toyotomi CTN/CTG-356W air conditioner",
        manufacturer="Toyotomi",
    )
    source = load_source_registry().get("bestprice")
    evidence = error_evidence(
        product=product,
        source=source,
        requested_url=(
            "https://www.bestprice.gr/item/2158816161/"
            "toyotomi-erai-ctnctg-356w-klimatistiko-inverter-18000-btu.html"
        ),
        error_code="inaccessible",
        error_message="Page.goto: net::ERR_CONNECTION_CLOSED",
    )
    score = score_candidate(product=product, source=source, evidence=evidence)

    assert evidence.exact_mpn_found
    assert evidence.exact_mpn_source == "url"
    assert evidence.brand_found
    assert score.match_status == "needs_review"
    assert score.match_method == "url_identifier_and_brand_inaccessible"
    assert score.confidence_score == 0.80


def _allow_source_url_agent_run_database(monkeypatch) -> None:
    monkeypatch.setattr(source_url_agent_run_routes, "_require_source_url_agent_run_database_ready", lambda: None)


def _fake_resolver(product, source) -> SourceSearchResult:
    url = f"https://{source.source_domain}/item/{product.model}/lg-remote.html"
    evidence = PageEvidence(
        requested_url=url,
        final_url=url,
        canonical_url=url,
        title=f"{product.manufacturer} {product.mpn} remote control",
        body_text_sample=f"{product.manufacturer} {product.mpn}",
        candidate_price=Decimal("18.50"),
        exact_mpn_found=True,
        exact_mpn_fragment=product.mpn,
        exact_mpn_source="title",
        exact_model_found=False,
        exact_model_fragment="",
        exact_model_source="",
        brand_found=True,
        brand_fragment=product.manufacturer,
        category_compatible=True,
        category_fragment=product.category,
        title_similarity=0.95,
        title_matched_tokens=(product.manufacturer.lower(), product.mpn.lower()),
        price_compatible=None,
        jsonld_products=(),
    )
    return SourceSearchResult(evidence=[evidence], searched_queries=[f"{product.manufacturer} {product.mpn}"], searched_urls=[], errors=[])


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


def _run_api_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    monkeypatch.chdir(tmp_path)
    _allow_source_url_agent_run_database(monkeypatch)
    monkeypatch.setattr(source_url_agent_api_state, "SOURCE_URL_AGENT_API_RESOLVER", _fake_resolver)
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    _create_schema(database_url)
    return TestClient(create_app()), database_url


def test_artifact_writing_creates_required_files(tmp_path: Path) -> None:
    product = _product()
    candidate = _candidate(product)

    paths = write_run_artifacts(
        run_id="run-1",
        candidates=[candidate],
        summary={"run_id": "run-1", "selected_count": 1},
        output_dir=tmp_path,
    )

    assert paths.source_url_results.exists()
    assert paths.approved_source_urls.exists()
    assert paths.needs_review_source_urls.exists()
    assert paths.not_found_source_urls.exists()
    assert paths.errors.exists()
    assert paths.source_url_run_summary.exists()
    assert paths.searched_queries.exists()
    assert paths.rule_suggestions.exists()


def test_artifact_writing_includes_provider_provenance_in_searched_queries(tmp_path: Path) -> None:
    product = _product()
    candidate = _candidate(product)
    provenance = {
        "provider_name": "browser_fallback",
        "source_name": "skroutz",
        "original_query": "MR25GB",
        "search_url": "https://www.skroutz.gr/search?keyphrase=MR25GB",
        "candidate_url": candidate.candidate_url,
        "result_index": 1,
        "discovery_method": "public_source_search_page",
        "allow_high_confidence_auto_apply": True,
    }
    candidate = replace(candidate, evidence_json={**candidate.evidence_json, "provider_provenance": provenance})

    paths = write_run_artifacts(
        run_id="run-1",
        candidates=[candidate],
        summary={"run_id": "run-1", "selected_count": 1},
        output_dir=tmp_path,
    )

    payload = json.loads(paths.searched_queries.read_text(encoding="utf-8"))

    assert payload["items"][0]["provider_provenance"] == [provenance]


def test_source_url_agent_progress_definitions_are_stable() -> None:
    assert SOURCE_URL_AGENT_PROGRESS_STEP_IDS == (
        "product_selection_started",
        "product_selection_completed",
        "source_registry_loaded",
        "discovery_started",
        "product_source_started",
        "product_source_completed",
        "candidate_scoring_started",
        "candidate_scoring_completed",
        "high_confidence_apply_started",
        "high_confidence_apply_completed",
        "artifact_writing_started",
        "artifact_writing_completed",
        "candidate_persistence_started",
        "candidate_persistence_completed",
        "run_completed",
    )
    assert [definition.label for definition in SOURCE_URL_AGENT_PROGRESS_STEP_DEFINITIONS]
    assert SOURCE_URL_AGENT_PROGRESS_STEP_LABELS["product_source_completed"] == "Product-source completed"


def test_agent_records_durable_progress_counts_and_resolver_errors(tmp_path: Path, monkeypatch) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    _create_schema(database_url)
    registry = load_source_registry()
    clock = _Clock(datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc))

    with session_scope(database_url) as session:
        row = _catalog_product(session)
        create_queued_job(session, job_type=SOURCE_URL_AGENT_JOB_TYPE, payload={}, job_id="job-source-agent")
        mark_running(session, "job-source-agent")
        catalog_product_id = row.id

    product = _product(catalog_product_id=catalog_product_id)

    def resolver(_product, source):
        return SourceSearchResult(
            evidence=[],
            searched_queries=["MR25GB"],
            searched_urls=[f"https://{source.source_domain}/search?q=MR25GB&token=secret"],
            errors=[f"https://{source.source_domain}/search?q=MR25GB&token=secret: timeout"],
        )

    with SourceUrlAgentProgressReporter("job-source-agent", heartbeat_interval_seconds=60, now=clock) as reporter:
        with session_scope(database_url) as session:
            result = run_source_url_agent(
                products=[product],
                options=SourceUrlAgentOptions(
                    mode="catalog",
                    source="bestprice",
                    output_dir=tmp_path / "runs",
                    dry_run=True,
                    apply_high_confidence=False,
                    progress_reporter=reporter,
                ),
                registry=registry,
                session=session,
                resolver=resolver,
            )
            assert session.query(SourceUrl).count() == 0
        progress = reporter.current_payload()

    with session_scope(database_url) as session:
        job = get_job_by_id(session, "job-source-agent")
        assert job is not None
        persisted_progress = job.result_json["progress"]

    assert result.summary["error_count"] == 1
    assert progress["current_step"] == "run_completed"
    assert persisted_progress["current_step"] in {"candidate_persistence_started", "candidate_persistence_completed", "run_completed"}
    assert progress["details"]["product_count"] == 1
    assert progress["details"]["source_count"] == 1
    assert progress["details"]["product_source_task_count"] == 1
    assert progress["details"]["completed_product_source_task_count"] == 1
    assert progress["details"]["candidate_count"] == 1
    assert progress["details"]["error_count"] == 1
    assert progress["details"]["persisted_candidate_count"] == 1
    assert progress["details"]["applied_high_confidence_url_count"] == 0
    completed = {step["step"]: step for step in progress["completed_steps"]}
    assert completed["product_source_completed"]["details"]["completed_product_source_task_count"] == 1
    scoring_errors = completed["candidate_scoring_completed"]["errors"]
    assert scoring_errors
    assert "token=secret" not in str(scoring_errors)
    assert "token=%5Bredacted%5D" in str(scoring_errors)


def test_agent_persists_run_and_candidate_models_when_apply_high_confidence(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        source = registry.get("skroutz")
        evidence = extract_page_evidence(
            product=product,
            source=source,
            requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
            final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
            html_text=_html(),
        )

        def resolver(_product, _source):
            return SourceSearchResult(evidence=[evidence], searched_queries=["MR25GB"], searched_urls=[], errors=[])

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="csv",
                source="skroutz",
                output_dir=tmp_path / "runs",
                dry_run=False,
                apply_high_confidence=True,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        assert session.query(SourceUrlDiscoveryRun).count() == 1
        assert session.query(SourceUrlCandidate).count() == 1
        assert session.query(SourceUrl).count() == 1

    assert result.summary["matched_count"] == 1


def test_provider_auto_apply_gate_prevents_high_confidence_write(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        source = registry.get("skroutz")
        fake_provider = SearchProviderDefinition(
            provider_name="fake_review_only",
            provider_type="test",
            enabled=True,
            allow_high_confidence_auto_apply=False,
        )
        evidence = extract_page_evidence(
            product=product,
            source=source,
            requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
            final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
            html_text=_html(),
            provider_provenance={
                "provider_name": fake_provider.provider_name,
                "source_name": "skroutz",
                "original_query": "MR25GB",
                "search_url": "https://provider.example/search?q=MR25GB",
                "candidate_url": "https://www.skroutz.gr/s/123/LG-MR25GB.html",
                "result_index": 1,
                "discovery_method": "test_provider",
                "allow_high_confidence_auto_apply": fake_provider.allow_high_confidence_auto_apply,
            },
        )

        def resolver(_product, _source):
            return SourceSearchResult(evidence=[evidence], searched_queries=["MR25GB"], searched_urls=[], errors=[])

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="csv",
                source="skroutz",
                output_dir=tmp_path / "runs",
                dry_run=False,
                apply_high_confidence=True,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        assert session.query(SourceUrlDiscoveryRun).count() == 1
        assert session.query(SourceUrlCandidate).count() == 1
        assert session.query(SourceUrl).count() == 0

    assert result.summary["matched_count"] == 1
    assert result.candidates[0].status == "pending"
    assert result.summary["source_url_write_results"] == [
        {
            "candidate_index": 0,
            "action": "skipped",
            "source_url_id": None,
            "reason": "provider_auto_apply_disabled:fake_review_only",
        }
    ]
    assert "source_url_write_skipped: provider_auto_apply_disabled:fake_review_only" in result.warnings


def test_agent_persists_high_confidence_needs_review_candidates_during_dry_run(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        source = registry.get("electronet")
        evidence = extract_page_evidence(
            product=product,
            source=source,
            requested_url="https://www.electronet.gr/lg-remote",
            final_url="https://www.electronet.gr/lg-remote",
            html_text="""
            <html>
              <head>
                <title>Magic Remote</title>
                <link rel="canonical" href="https://www.electronet.gr/lg-remote" />
              </head>
              <body>Compatible with MR25GB remote controls</body>
            </html>
            """,
        )

        def resolver(_product, _source):
            return SourceSearchResult(evidence=[evidence], searched_queries=["LG MR25GB"], searched_urls=[], errors=[])

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="electronet",
                output_dir=tmp_path / "runs",
                dry_run=True,
                apply_high_confidence=False,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidate = session.query(SourceUrlCandidate).one()

        assert session.query(SourceUrlDiscoveryRun).count() == 1
        assert session.query(SourceUrl).count() == 0
        assert stored_candidate.match_status == "needs_review"
        assert stored_candidate.status == "needs_review"
        assert stored_candidate.confidence_score >= Decimal("0.8000")
        assert stored_candidate.candidate_url == "https://www.electronet.gr/lg-remote"

    assert result.summary["needs_review_count"] == 1
    assert result.summary["persisted_candidate_count"] == 1


def test_agent_discards_low_confidence_candidates_from_storage_and_artifacts(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        source = registry.get("bestprice")
        evidence = extract_page_evidence(
            product=product,
            source=source,
            requested_url="https://www.bestprice.gr/item/999/lg-remote.html",
            final_url="https://www.bestprice.gr/item/999/lg-remote.html",
            html_text="""
            <html>
              <head>
                <title>LG Magic Remote | BestPrice.gr</title>
                <link rel="canonical" href="https://www.bestprice.gr/item/999/lg-remote.html" />
              </head>
              <body>Brand LG compatible with MR25GB remote controls</body>
            </html>
            """,
        )

        def resolver(_product, _source):
            return SourceSearchResult(evidence=[evidence], searched_queries=["LG MR25GB"], searched_urls=[], errors=[])

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="bestprice",
                output_dir=tmp_path / "runs",
                dry_run=True,
                apply_high_confidence=False,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        assert session.query(SourceUrlDiscoveryRun).count() == 1
        assert session.query(SourceUrlCandidate).count() == 0
        assert session.query(SourceUrl).count() == 0

    with result.artifacts.source_url_results.open("r", encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == []
    assert result.summary["needs_review_count"] == 1
    assert result.summary["persisted_candidate_count"] == 0
    assert result.summary["discarded_low_confidence_candidate_count"] == 1


def test_agent_persists_matched_candidates_during_dry_run_without_source_url_write(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        source = registry.get("skroutz")
        evidence = extract_page_evidence(
            product=product,
            source=source,
            requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
            final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
            html_text=_html(),
        )

        def resolver(_product, _source):
            return SourceSearchResult(evidence=[evidence], searched_queries=["MR25GB"], searched_urls=[], errors=[])

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="skroutz",
                output_dir=tmp_path / "runs",
                dry_run=True,
                apply_high_confidence=False,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidate = session.query(SourceUrlCandidate).one()

        assert session.query(SourceUrlDiscoveryRun).count() == 1
        assert session.query(SourceUrl).count() == 0
        assert stored_candidate.match_status == "matched"
        assert stored_candidate.status == "pending"

    assert result.summary["matched_count"] == 1
    assert result.summary["persisted_candidate_count"] == 1


def test_agent_persists_terminal_error_candidates_for_review_filtering(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)

        def resolver(_product, _source):
            return SourceSearchResult(
                evidence=[],
                searched_queries=["MR25GB"],
                searched_urls=["https://www.bestprice.gr/search?q=MR25GB"],
                errors=["https://www.bestprice.gr/search?q=MR25GB: http_500"],
            )

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="bestprice",
                output_dir=tmp_path / "runs",
                dry_run=True,
                apply_high_confidence=False,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidate = session.query(SourceUrlCandidate).one()

        assert stored_candidate.match_status == "error"
        assert stored_candidate.status == "error"
        assert stored_candidate.confidence_score == Decimal("0.0000")
        assert "http_500" in (stored_candidate.notes or "")

    assert result.summary["error_count"] == 1
    assert result.summary["persisted_candidate_count"] == 1


def test_agent_persists_terminal_not_found_candidates_for_review_filtering(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)

        def resolver(_product, _source):
            return SourceSearchResult(evidence=[], searched_queries=["MR25GB"], searched_urls=[], errors=[])

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="bestprice",
                output_dir=tmp_path / "runs",
                dry_run=True,
                apply_high_confidence=False,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidate = session.query(SourceUrlCandidate).one()

        assert stored_candidate.match_status == "not_found"
        assert stored_candidate.status == "not_found"
        assert stored_candidate.confidence_score == Decimal("0.0000")

    assert result.summary["not_found_count"] == 1
    assert result.summary["persisted_candidate_count"] == 1


def test_source_url_agent_csv_run_requires_database_for_direct_persistence(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("ECOMMERCE_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    input_path = tmp_path / "input.csv"
    input_path.write_text("model,mpn,name\n005606,MR25GB,LG Remote\n", encoding="utf-8")

    code = source_url_agent_job.main(["run", "--input", str(input_path), "--source", "skroutz"])

    assert code == 1
    assert "requires ECOMMERCE_DATABASE_URL" in capsys.readouterr().err


def test_source_url_agent_run_api_dry_run_from_catalog_persists_run_and_candidates(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)

    response = client.post(
        "/api/source-url-agent/runs",
        json={
            "source": "bestprice",
            "mode": "catalog",
            "catalog_product_id": product.id,
            "limit": 1,
            "dry_run": True,
            "max_products_per_batch": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"]
    assert payload["dry_run"] is True
    assert payload["summary"]["selected_count"] == 1
    assert payload["status"] == "queued"
    assert payload["summary"]["task_total_count"] == 1
    with session_scope(database_url) as session:
        run = session.query(SourceUrlDiscoveryRun).one()
        candidate = session.query(SourceUrlCandidate).one()
        job = session.query(EcommerceJob).filter_by(job_id=payload["run_id"]).one()
        assert run.run_id == payload["run_id"]
        assert run.source_name == "bestprice"
        assert run.status == "completed"
        assert candidate.run_id == payload["run_id"]
        assert candidate.match_status == "matched"
        assert job.job_type == SOURCE_URL_AGENT_JOB_TYPE
        assert job.status == "succeeded"
        assert job.result_json["progress"]["current_step"] == "run_completed"
        assert job.result_json["progress"]["details"]["matched_count"] == 1
    history = client.get("/api/source-url-agent/runs")
    detail = client.get(f"/api/source-url-agent/runs/{payload['run_id']}")
    assert history.status_code == 200
    assert history.json()["items"][0]["run_id"] == payload["run_id"]
    assert detail.status_code == 200
    assert detail.json()["run_id"] == payload["run_id"]
    assert detail.json()["summary"]["matched_count"] == 1
    assert detail.json()["summary"]["task_finished_count"] == 1
    assert detail.json()["artifacts"]


def test_source_url_agent_worker_executes_queued_run_and_persists_progress(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    monkeypatch.setattr(source_url_agent_run_routes, "execute_source_url_agent_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(source_url_agent_job_handler, "SOURCE_URL_AGENT_JOB_RESOLVER", _fake_resolver)
    with session_scope(database_url) as session:
        product = _catalog_product(session)

    response = client.post(
        "/api/source-url-agent/runs",
        json={
            "source": "bestprice",
            "mode": "catalog",
            "catalog_product_id": product.id,
            "limit": 1,
            "dry_run": True,
            "max_products_per_batch": 1,
        },
    )

    assert response.status_code == 200
    run_id = response.json()["run_id"]
    with session_scope(database_url) as session:
        assert get_job_by_id(session, run_id).status == "queued"

    result = run_worker_iteration(
        registry=build_default_registry(),
        job_type=SOURCE_URL_AGENT_JOB_TYPE,
        database_url=database_url,
    )

    assert result.claimed == 1
    assert result.executed == 1
    with session_scope(database_url) as session:
        run = session.query(SourceUrlDiscoveryRun).one()
        candidate = session.query(SourceUrlCandidate).one()
        job = get_job_by_id(session, run_id)
        assert run.status == "completed"
        assert run.matched_count == 1
        assert candidate.run_id == run_id
        assert candidate.match_status == "matched"
        assert job.status == "succeeded"
        assert job.result_json["run_id"] == run_id
        assert job.result_json["summary"]["matched_count"] == 1
        assert job.result_json["progress"]["current_step"] == "run_completed"


def test_source_url_agent_worker_marks_failed_run_and_job_on_execution_error(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    monkeypatch.setattr(source_url_agent_run_routes, "execute_source_url_agent_job", lambda *_args, **_kwargs: None)

    def failing_resolver(_product, _source):
        raise RuntimeError("resolver exploded")

    monkeypatch.setattr(source_url_agent_job_handler, "SOURCE_URL_AGENT_JOB_RESOLVER", failing_resolver)
    with session_scope(database_url) as session:
        product = _catalog_product(session)

    response = client.post(
        "/api/source-url-agent/runs",
        json={
            "source": "bestprice",
            "mode": "catalog",
            "catalog_product_id": product.id,
            "limit": 1,
            "dry_run": True,
            "max_products_per_batch": 1,
        },
    )

    assert response.status_code == 200
    run_id = response.json()["run_id"]

    result = run_worker_iteration(
        registry=build_default_registry(),
        job_type=SOURCE_URL_AGENT_JOB_TYPE,
        database_url=database_url,
    )

    assert result.claimed == 1
    assert result.executed == 1
    with session_scope(database_url) as session:
        run = session.query(SourceUrlDiscoveryRun).one()
        task = session.query(SourceUrlDiscoveryTask).filter_by(run_id=run_id).one()
        job = get_job_by_id(session, run_id)
        assert run.status == "failed"
        assert task.status == "failed"
        assert task.error_message == "resolver exploded"
        assert job.status == "failed"
        assert job.error_message == "resolver exploded"
        assert job.result_json["progress"]["current_step"] == "product_source_started"


def test_source_url_agent_background_execution_noops_when_worker_already_claimed_job(tmp_path: Path, monkeypatch) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        create_queued_job(
            session,
            job_type=SOURCE_URL_AGENT_JOB_TYPE,
            payload={"run_id": "job-source-agent", "request": {"source": "bestprice", "mode": "catalog"}},
            job_id="job-source-agent",
        )
        mark_running(session, "job-source-agent")

    def should_not_run(_product, _source):
        raise AssertionError("running jobs should not be executed by an unclaimed background task")

    job = source_url_agent_job_handler.execute_source_url_agent_job("job-source-agent", resolver=should_not_run)

    assert job.status == "running"
    with session_scope(database_url) as session:
        persisted = get_job_by_id(session, "job-source-agent")
        assert persisted.status == "running"
        assert persisted.attempt_count == 1


def test_source_url_agent_run_api_lists_persisted_error_candidates(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)

    def error_resolver(product, source):
        return SourceSearchResult(
            evidence=[],
            searched_queries=[f"{product.manufacturer} {product.mpn}"],
            searched_urls=[f"https://{source.source_domain}/search?q={product.mpn}"],
            errors=[f"https://{source.source_domain}/search?q={product.mpn}: http_500"],
        )

    monkeypatch.setattr(source_url_agent_api_state, "SOURCE_URL_AGENT_API_RESOLVER", error_resolver)
    with session_scope(database_url) as session:
        product = _catalog_product(session)

    response = client.post(
        "/api/source-url-agent/runs",
        json={
            "source": "bestprice",
            "mode": "catalog",
            "catalog_product_id": product.id,
            "limit": 1,
            "dry_run": True,
            "max_products_per_batch": 1,
        },
    )

    assert response.status_code == 200
    run_id = response.json()["run_id"]
    with session_scope(database_url) as session:
        run = session.query(SourceUrlDiscoveryRun).one()
        assert run.error_count == 1
        assert session.query(SourceUrlCandidate).count() == 1

    candidates = client.get("/api/source-url-agent/candidates", params={"status": "error", "run_id": run_id})

    assert candidates.status_code == 200
    payload = candidates.json()
    assert payload["total"] == 1
    assert payload["items"][0]["status"] == "error"
    assert payload["items"][0]["match_status"] == "error"
    assert "http_500" in payload["items"][0]["notes"]


def test_vendor_sources_agent_run_namespace_delegates_to_source_url_agent(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)

    response = client.post(
        "/api/source-url-agent/runs",
        json={
            "source": "electronet",
            "mode": "catalog",
            "catalog_product_id": product.id,
            "limit": 1,
            "dry_run": True,
            "max_products_per_batch": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "electronet"
    history = client.get("/api/source-url-agent/runs")
    assert history.status_code == 200
    assert history.json()["items"][0]["run_id"] == payload["run_id"]


def test_source_url_agent_run_api_accepts_selected_models(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        _catalog_product(session, model="SELECT-1", mpn="MPN-1")
        _catalog_product(session, model="SELECT-2", mpn="MPN-2")
        _catalog_product(session, model="SKIP-1", mpn="MPN-3")

    response = client.post(
        "/api/source-url-agent/runs",
        json={
            "source": "bestprice",
            "mode": "catalog",
            "selected_models": ["SELECT-1", "SELECT-2"],
            "limit": 2,
            "dry_run": True,
            "max_products_per_batch": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["selected_count"] == 2
    with session_scope(database_url) as session:
        run = session.query(SourceUrlDiscoveryRun).one()
        assert run.filters_json["selected_models"] == ["SELECT-1", "SELECT-2"]
        candidate_models = {candidate.model for candidate in session.query(SourceUrlCandidate).all()}
        assert candidate_models == {"SELECT-1", "SELECT-2"}


def test_source_url_agent_run_api_enforces_bounded_default_limit(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    monkeypatch.setattr(source_url_agent_api_validation, "DEFAULT_API_MAX_PRODUCTS_PER_BATCH", 2)
    with session_scope(database_url) as session:
        for index in range(4):
            _catalog_product(session, model=f"MODEL-{index}", mpn=f"MPN-{index}")

    response = client.post("/api/source-url-agent/runs", json={"source": "bestprice", "mode": "catalog"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["selected_count"] == 2
    with session_scope(database_url) as session:
        assert session.query(SourceUrlCandidate).count() == 2


def test_source_url_agent_run_artifact_endpoint_returns_safe_metadata(tmp_path: Path, monkeypatch) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)

    run_response = client.post(
        "/api/source-url-agent/runs",
        json={"source": "bestprice", "mode": "catalog", "catalog_product_id": product.id, "limit": 1},
    )
    run_id = run_response.json()["run_id"]
    artifact_response = client.get(f"/api/source-url-agent/runs/{run_id}/artifacts")

    assert artifact_response.status_code == 200
    payload = artifact_response.json()
    assert payload["run_id"] == run_id
    names = {item["name"] for item in payload["items"]}
    assert "source_url_run_summary.json" in names
    assert all(item["is_allowed"] for item in payload["items"])
    assert all(item["read_url"].startswith("/api/artifacts/read?path=") for item in payload["items"])
