import csv
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.api.source_url_agent import (
    runs as source_url_agent_run_routes,
)  # noqa: E402
from ecommerce.api.source_url_agent import (
    state as source_url_agent_api_state,
)  # noqa: E402
from ecommerce.api.source_url_agent import (
    validation as source_url_agent_api_validation,
)  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.models.jobs import EcommerceJob  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.source_urls import (  # noqa: E402
    SourceUrl,
    SourceUrlCandidate,
    SourceUrlDiscoveryRun,
    SourceUrlDiscoveryTask,
)
from ecommerce.db.repositories.jobs import (
    create_queued_job,
    get_job_by_id,
    mark_running,
)  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.jobs import source_url_agent as source_url_agent_job  # noqa: E402
from ecommerce.jobs.execution_policy import (
    API_EXECUTE_DURABLE_JOBS_INLINE_ENV_VAR,
)  # noqa: E402
from ecommerce.jobs.worker import (
    build_default_registry,
    run_worker_iteration,
)  # noqa: E402
from ecommerce.source_url_agent.artifacts import write_run_artifacts  # noqa: E402
from ecommerce.source_url_agent.candidates import candidate_from_evidence  # noqa: E402
from ecommerce.source_url_agent.evidence import (
    PageEvidence,
    error_evidence,
    extract_page_evidence,
)  # noqa: E402
from ecommerce.source_url_agent import (
    job_handler as source_url_agent_job_handler,
)  # noqa: E402
from ecommerce.source_url_agent import llm_evaluation as source_url_llm_evaluation  # noqa: E402
from ecommerce.source_url_agent.enqueue_service import (  # noqa: E402
    SourceUrlAgentEnqueueCommand,
    enqueue_source_url_agent_run_setup,
)
from ecommerce.source_url_agent.llm_evaluation import (  # noqa: E402
    SourceUrlLLMEvaluation,
    SourceUrlLLMEvaluationError,
    compact_candidate_payload,
)
from ecommerce.source_url_agent.llm_config import load_source_url_llm_config  # noqa: E402
from ecommerce.source_url_agent.options import SourceUrlAgentOptions  # noqa: E402
from ecommerce.source_url_agent.products import AgentProduct  # noqa: E402
from ecommerce.source_url_agent.progress import (  # noqa: E402
    SOURCE_URL_AGENT_JOB_TYPE,
    SOURCE_URL_AGENT_PROGRESS_STEP_DEFINITIONS,
    SOURCE_URL_AGENT_PROGRESS_STEP_IDS,
    SOURCE_URL_AGENT_PROGRESS_STEP_LABELS,
    SourceUrlAgentProgressReporter,
)
from ecommerce.source_url_agent.runner import run_source_url_agent  # noqa: E402
from ecommerce.source_url_agent.scoring import score_candidate  # noqa: E402
from ecommerce.source_url_agent.search import SourceSearchResult  # noqa: E402
from ecommerce.source_url_agent.search_providers import (
    SearchProviderDefinition,
)  # noqa: E402
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


def _catalog_product(
    session, *, model: str = "005606", mpn: str = "MR25GB"
) -> CatalogProductRow:
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


def _html(
    *, include_mpn: bool = True, title: str = "LG MR25GB Magic Remote Control"
) -> str:
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


def _bestprice_review_evidence(product: AgentProduct, *, url: str | None = None):
    source = load_source_registry().get("bestprice")
    candidate_url = url or "https://www.bestprice.gr/item/987654/lg-mr25gb.html"
    return extract_page_evidence(
        product=product,
        source=source,
        requested_url=candidate_url,
        final_url=candidate_url,
        html_text=f"""
        <html>
          <head>
            <title>BestPrice.gr</title>
            <link rel="canonical" href="{candidate_url}" />
            <meta name="description" content="LG MR25GB Magic Remote Control" />
          </head>
          <body></body>
        </html>
        """,
        provider_provenance={
            "provider_name": "brave_search",
            "source_name": "bestprice",
            "original_query": 'site:bestprice.gr LG "MR25GB"',
            "search_url": "https://api.search.brave.com/res/v1/web/search?q=MR25GB",
            "candidate_url": candidate_url,
            "result_index": 1,
            "discovery_method": "brave_web_search",
            "allow_high_confidence_auto_apply": False,
        },
    )


def _same_product_llm(url: str = "https://www.bestprice.gr/item/987654/lg-mr25gb.html"):
    return SourceUrlLLMEvaluation(
        verdict="same_product",
        confidence=Decimal("0.96"),
        apply_recommendation="auto_apply",
        reasons=["Exact MPN and brand evidence match."],
        positive_evidence=["MR25GB", "LG"],
        negative_evidence=[],
        selected_candidate_url=url,
        warnings=[],
    )


def test_source_url_agent_scores_marketplace_meta_description_evidence_as_review() -> (
    None
):
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


def test_source_url_agent_keeps_inaccessible_url_mpn_brand_evidence_for_review() -> (
    None
):
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
    monkeypatch.setattr(
        source_url_agent_run_routes,
        "require_source_url_agent_run_database_ready",
        lambda: None,
    )


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
    return SourceSearchResult(
        evidence=[evidence],
        searched_queries=[f"{product.manufacturer} {product.mpn}"],
        searched_urls=[],
        errors=[],
    )


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
    monkeypatch.setattr(
        source_url_agent_api_state, "SOURCE_URL_AGENT_API_RESOLVER", _fake_resolver
    )
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    _create_schema(database_url)
    return TestClient(create_app()), database_url


def test_source_url_agent_enqueue_service_creates_queued_run_tasks_and_job(
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        result = enqueue_source_url_agent_run_setup(
            session,
            SourceUrlAgentEnqueueCommand(
                run_id="run-service",
                source_name="bestprice",
                mode="catalog",
                input_path=None,
                limit=1,
                catalog_product_id=product.id,
                selected_models=[],
                missing_only=False,
                active_only=True,
                dry_run=True,
                apply_high_confidence=False,
                max_products_per_batch=1,
                llm_evaluate_candidates=True,
                llm_auto_apply_candidates=True,
                request_payload={
                    "source": "bestprice",
                    "mode": "catalog",
                    "catalog_product_id": product.id,
                    "limit": 1,
                    "dry_run": True,
                    "max_products_per_batch": 1,
                    "llm_evaluate_candidates": True,
                    "llm_auto_apply_candidates": True,
                },
            ),
        )

        run = session.query(SourceUrlDiscoveryRun).filter_by(run_id="run-service").one()
        task = (
            session.query(SourceUrlDiscoveryTask).filter_by(run_id="run-service").one()
        )
        job = session.query(EcommerceJob).filter_by(job_id="run-service").one()

        assert result.run_id == "run-service"
        assert result.run is run
        assert result.selected_count == 1
        assert result.task_count == 1
        assert run.status == "queued"
        assert run.source_name == "bestprice"
        assert run.filters_json["limit"] == 1
        assert run.filters_json["llm_evaluate_candidates"] is True
        assert run.filters_json["llm_auto_apply_candidates"] is True
        assert run.filters_json["task_count"] == 1
        assert task.status == "queued"
        assert task.catalog_product_id == product.id
        assert task.source_name == "bestprice"
        assert job.job_type == SOURCE_URL_AGENT_JOB_TYPE
        assert job.status == "queued"
        assert job.payload_json["run_id"] == "run-service"
        assert job.payload_json["source"] == "bestprice"
        assert job.payload_json["request"]["source"] == "bestprice"
        assert job.payload_json["request"]["llm_evaluate_candidates"] is True
        assert job.payload_json["request"]["llm_auto_apply_candidates"] is True
        assert job.payload_json["effective_limit"] == 1
        job_payload = dict(job.payload_json)

    parsed = source_url_agent_job_handler.source_url_agent_job_request_from_payload(
        job_payload
    )
    assert parsed.llm_evaluate_candidates is True
    assert parsed.llm_auto_apply_candidates is True


def test_source_url_agent_cli_options_preserve_llm_flags(tmp_path: Path) -> None:
    options = source_url_agent_job._options(
        SimpleNamespace(
            source="bestprice",
            output_dir=tmp_path,
            limit=1,
            offset=0,
            catalog_product_id=None,
            model=None,
            missing_only=False,
            dry_run=False,
            apply_high_confidence=False,
            max_products_per_batch=1,
            max_searches_per_product_source=None,
            rate_limit_seconds=None,
            headed=False,
            no_browser_cache=False,
            llm_evaluate_candidates=True,
            llm_auto_apply_candidates=True,
        ),
        mode="catalog",
        input_path=None,
        active_only=True,
    )

    assert options.llm_evaluate_candidates is True
    assert options.llm_auto_apply_candidates is True


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


def test_artifact_writing_includes_provider_provenance_in_searched_queries(
    tmp_path: Path,
) -> None:
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
    candidate = replace(
        candidate,
        evidence_json={
            **candidate.evidence_json,
            "provider_provenance": provenance,
            "provider_summary": {
                "provider_name": "brave_search",
                "searched_queries": [
                    'site:bestprice.gr Toyotomi "OTN/OTG-12QINV"',
                    'site:bestprice.gr Toyotomi "OTN-12QINV/OTG-12QINV"',
                ],
                "searched_identifier_variants": [
                    "OTN/OTG-12QINV",
                    "OTN-12QINV/OTG-12QINV",
                ],
                "executed_query_count": 2,
                "matched_identifier_variant": "OTN-12QINV/OTG-12QINV",
            },
            "matched_identifier_variant": "OTN-12QINV/OTG-12QINV",
        },
        searched_queries=[
            'site:bestprice.gr Toyotomi "OTN/OTG-12QINV"',
            'site:bestprice.gr Toyotomi "OTN-12QINV/OTG-12QINV"',
        ],
    )

    paths = write_run_artifacts(
        run_id="run-1",
        candidates=[candidate],
        summary={"run_id": "run-1", "selected_count": 1},
        output_dir=tmp_path,
    )

    payload = json.loads(paths.searched_queries.read_text(encoding="utf-8"))

    assert payload["items"][0]["provider_provenance"] == [provenance]
    assert payload["items"][0]["searched_queries"] == [
        'site:bestprice.gr Toyotomi "OTN/OTG-12QINV"',
        'site:bestprice.gr Toyotomi "OTN-12QINV/OTG-12QINV"',
    ]
    assert payload["items"][0]["executed_query_count"] == 2
    assert payload["items"][0]["searched_identifier_variants"] == [
        "OTN/OTG-12QINV",
        "OTN-12QINV/OTG-12QINV",
    ]
    assert (
        payload["items"][0]["matched_identifier_variant"]
        == "OTN-12QINV/OTG-12QINV"
    )

    with paths.source_url_results.open("r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["executed_query_count"] == "2"
    assert row["searched_identifier_variants_json"] == (
        '["OTN/OTG-12QINV", "OTN-12QINV/OTG-12QINV"]'
    )
    assert row["matched_identifier_variant"] == "OTN-12QINV/OTG-12QINV"


def test_artifact_writing_includes_llm_fields(tmp_path: Path) -> None:
    product = _product()
    candidate = replace(
        _candidate(product, source_name="bestprice"),
        evidence_json={
            **_candidate(product, source_name="bestprice").evidence_json,
            "llm_evaluation": _same_product_llm().to_json(),
        },
    )

    paths = write_run_artifacts(
        run_id="run-1",
        candidates=[candidate],
        summary={"run_id": "run-1", "selected_count": 1},
        output_dir=tmp_path,
    )

    with paths.source_url_results.open("r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))

    assert row["llm_verdict"] == "same_product"
    assert row["llm_confidence"] == "0.96"
    assert row["llm_apply_recommendation"] == "auto_apply"
    assert row["llm_reasons"] == "Exact MPN and brand evidence match."


def test_source_url_llm_config_defaults_and_env_overrides(monkeypatch) -> None:
    monkeypatch.delenv("ECOMMERCE_SOURCE_URL_LLM_ENABLED", raising=False)
    default_config = load_source_url_llm_config(env={})

    assert default_config.enabled is False
    assert default_config.model == "gpt-5.4-mini"
    assert default_config.escalation_model == "gpt-5.5"
    assert default_config.reasoning_effort == "low"
    assert default_config.max_candidates == 3
    assert default_config.max_calls_per_run == 25
    assert default_config.auto_apply_min_confidence == Decimal("0.92")
    assert default_config.review_min_confidence == Decimal("0.75")

    config = load_source_url_llm_config(
        env={
            "ECOMMERCE_SOURCE_URL_LLM_ENABLED": "true",
            "ECOMMERCE_SOURCE_URL_LLM_MODEL": "custom-mini",
            "ECOMMERCE_SOURCE_URL_LLM_ESCALATION_MODEL": "custom-full",
            "ECOMMERCE_SOURCE_URL_LLM_REASONING_EFFORT": "medium",
            "ECOMMERCE_SOURCE_URL_LLM_MAX_CANDIDATES": "2",
            "ECOMMERCE_SOURCE_URL_LLM_MAX_CALLS_PER_RUN": "4",
            "ECOMMERCE_SOURCE_URL_LLM_AUTO_APPLY_MIN_CONFIDENCE": "0.94",
            "ECOMMERCE_SOURCE_URL_LLM_REVIEW_MIN_CONFIDENCE": "0.80",
        }
    )

    assert config.enabled is True
    assert config.model == "custom-mini"
    assert config.escalation_model == "custom-full"
    assert config.reasoning_effort == "medium"
    assert config.max_candidates == 2
    assert config.max_calls_per_run == 4
    assert config.auto_apply_min_confidence == Decimal("0.94")
    assert config.review_min_confidence == Decimal("0.80")


def test_llm_candidate_payload_is_compact_and_sanitized() -> None:
    product = _product()
    candidate = _candidate(product, source_name="bestprice")
    long_text = "x" * 1200
    candidate = replace(
        candidate,
        evidence_json={
            **candidate.evidence_json,
            "body_text_sample": long_text,
            "provider_provenance": {
                "provider_name": "brave_search",
                "source_name": "bestprice",
                "original_query": "MR25GB",
                "search_url": "https://api.search.example/search?q=MR25GB",
                "candidate_url": candidate.candidate_url,
                "authorization": "secret",
                "headers": {"authorization": "secret"},
            },
            "jsonld_products": [
                {
                    "name": long_text,
                    "brand": "LG",
                    "mpn": "MR25GB",
                    "description": long_text,
                }
            ],
            "html_text": long_text,
        },
        candidate_title=long_text,
    )

    payload = compact_candidate_payload(candidate)

    assert len(payload["candidate"]["candidate_title"]) == 300
    assert len(payload["evidence_summary"]["body_text_sample"]) == 500
    assert "html_text" not in payload["evidence_summary"]
    assert "authorization" not in payload["candidate"]["provider_provenance"]
    assert "headers" not in payload["candidate"]["provider_provenance"]
    jsonld = payload["evidence_summary"]["jsonld_products"][0]
    assert "description" not in jsonld
    assert len(jsonld["name"]) == 300


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
    assert [
        definition.label for definition in SOURCE_URL_AGENT_PROGRESS_STEP_DEFINITIONS
    ]
    assert (
        SOURCE_URL_AGENT_PROGRESS_STEP_LABELS["product_source_completed"]
        == "Product-source completed"
    )


def test_agent_records_durable_progress_counts_and_resolver_errors(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    _create_schema(database_url)
    registry = load_source_registry()
    clock = _Clock(datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc))

    with session_scope(database_url) as session:
        row = _catalog_product(session)
        create_queued_job(
            session,
            job_type=SOURCE_URL_AGENT_JOB_TYPE,
            payload={},
            job_id="job-source-agent",
        )
        mark_running(session, "job-source-agent")
        catalog_product_id = row.id

    product = _product(catalog_product_id=catalog_product_id)

    def resolver(_product, source):
        return SourceSearchResult(
            evidence=[],
            searched_queries=["MR25GB"],
            searched_urls=[
                f"https://{source.source_domain}/search?q=MR25GB&token=secret"
            ],
            errors=[
                f"https://{source.source_domain}/search?q=MR25GB&token=secret: timeout"
            ],
        )

    with SourceUrlAgentProgressReporter(
        "job-source-agent", heartbeat_interval_seconds=60, now=clock
    ) as reporter:
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
    assert persisted_progress["current_step"] in {
        "candidate_persistence_started",
        "candidate_persistence_completed",
        "run_completed",
    }
    assert progress["details"]["product_count"] == 1
    assert progress["details"]["source_count"] == 1
    assert progress["details"]["product_source_task_count"] == 1
    assert progress["details"]["completed_product_source_task_count"] == 1
    assert progress["details"]["candidate_count"] == 1
    assert progress["details"]["error_count"] == 1
    assert progress["details"]["persisted_candidate_count"] == 1
    assert progress["details"]["applied_high_confidence_url_count"] == 0
    completed = {step["step"]: step for step in progress["completed_steps"]}
    assert (
        completed["product_source_completed"]["details"][
            "completed_product_source_task_count"
        ]
        == 1
    )
    scoring_errors = completed["candidate_scoring_completed"]["errors"]
    assert scoring_errors
    assert "token=secret" not in str(scoring_errors)
    assert "token=%5Bredacted%5D" in str(scoring_errors)


def test_agent_persists_run_and_candidate_models_when_apply_high_confidence(
    tmp_path: Path,
) -> None:
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
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["MR25GB"],
                searched_urls=[],
                errors=[],
            )

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


def test_provider_auto_apply_gate_prevents_high_confidence_write(
    tmp_path: Path,
) -> None:
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
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["MR25GB"],
                searched_urls=[],
                errors=[],
            )

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
    assert (
        "source_url_write_skipped: provider_auto_apply_disabled:fake_review_only"
        in result.warnings
    )


def test_llm_default_disabled_does_not_call_evaluator_or_change_behavior(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ECOMMERCE_SOURCE_URL_LLM_ENABLED", "false")
    calls: list[str] = []
    monkeypatch.setattr(
        source_url_llm_evaluation,
        "SOURCE_URL_LLM_EVALUATOR",
        lambda candidate, _config: calls.append(candidate.source_name)
        or _same_product_llm(),
    )
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        evidence = _bestprice_review_evidence(product)

        def resolver(_product, _source):
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["MR25GB"],
                searched_urls=[],
                errors=[],
            )

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="bestprice",
                output_dir=tmp_path / "runs",
                dry_run=False,
                apply_high_confidence=False,
                llm_evaluate_candidates=True,
                llm_auto_apply_candidates=True,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidate = session.query(SourceUrlCandidate).one()

        assert session.query(SourceUrl).count() == 0
        assert stored_candidate.status == "needs_review"
        assert "llm_evaluation" not in stored_candidate.evidence_json

    assert calls == []
    assert result.summary["llm_evaluated_candidate_count"] == 0
    assert any(
        "ECOMMERCE_SOURCE_URL_LLM_ENABLED is false" in warning
        for warning in result.warnings
    )


def test_llm_auto_apply_flag_without_evaluation_flag_does_not_call_evaluator(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ECOMMERCE_SOURCE_URL_LLM_ENABLED", "true")
    calls: list[str] = []
    monkeypatch.setattr(
        source_url_llm_evaluation,
        "SOURCE_URL_LLM_EVALUATOR",
        lambda candidate, _config: calls.append(candidate.source_name)
        or _same_product_llm(),
    )
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        evidence = _bestprice_review_evidence(product)

        def resolver(_product, _source):
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["MR25GB"],
                searched_urls=[],
                errors=[],
            )

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="bestprice",
                output_dir=tmp_path / "runs",
                dry_run=False,
                apply_high_confidence=False,
                llm_evaluate_candidates=False,
                llm_auto_apply_candidates=True,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidate = session.query(SourceUrlCandidate).one()

        assert session.query(SourceUrl).count() == 0
        assert stored_candidate.status == "needs_review"
        assert "llm_evaluation" not in stored_candidate.evidence_json

    assert calls == []
    assert result.summary["llm_evaluated_candidate_count"] == 0
    assert any(
        "llm_auto_apply_candidates requested without llm_evaluate_candidates"
        in warning
        for warning in result.warnings
    )


def test_llm_promotes_bestprice_needs_review_candidate_to_source_url(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ECOMMERCE_SOURCE_URL_LLM_ENABLED", "true")
    monkeypatch.setattr(
        source_url_llm_evaluation,
        "SOURCE_URL_LLM_EVALUATOR",
        lambda _candidate, _config: _same_product_llm(),
    )
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        evidence = _bestprice_review_evidence(product)

        def resolver(_product, _source):
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=['site:bestprice.gr LG "MR25GB"'],
                searched_urls=[],
                errors=[],
            )

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="bestprice",
                output_dir=tmp_path / "runs",
                dry_run=False,
                apply_high_confidence=False,
                llm_evaluate_candidates=True,
                llm_auto_apply_candidates=True,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidate = session.query(SourceUrlCandidate).one()
        stored_url = session.query(SourceUrl).one()

        assert stored_candidate.status == "accepted"
        assert (
            stored_candidate.evidence_json["llm_evaluation"]["verdict"]
            == "same_product"
        )
        assert stored_url.source_name == "bestprice"
        assert stored_url.trust_level == "llm_high_confidence"

    assert result.summary["llm_evaluated_candidate_count"] == 1
    assert result.summary["llm_auto_applied_candidate_count"] == 1
    assert result.summary["llm_source_url_write_results"][0]["action"] == "created"


def test_llm_evaluation_without_auto_apply_keeps_candidate_in_review(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ECOMMERCE_SOURCE_URL_LLM_ENABLED", "true")
    monkeypatch.setattr(
        source_url_llm_evaluation,
        "SOURCE_URL_LLM_EVALUATOR",
        lambda _candidate, _config: _same_product_llm(),
    )
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        evidence = _bestprice_review_evidence(product)

        def resolver(_product, _source):
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["MR25GB"],
                searched_urls=[],
                errors=[],
            )

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="bestprice",
                output_dir=tmp_path / "runs",
                dry_run=False,
                apply_high_confidence=False,
                llm_evaluate_candidates=True,
                llm_auto_apply_candidates=False,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidate = session.query(SourceUrlCandidate).one()

        assert session.query(SourceUrl).count() == 0
        assert stored_candidate.status == "needs_review"
        assert (
            stored_candidate.evidence_json["llm_evaluation"][
                "apply_recommendation"
            ]
            == "auto_apply"
        )

    assert result.summary["llm_auto_applied_candidate_count"] == 0


def test_llm_cannot_apply_non_bestprice_candidate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ECOMMERCE_SOURCE_URL_LLM_ENABLED", "true")
    calls: list[str] = []

    def evaluator(candidate, config):
        del config
        calls.append(candidate.source_name)
        return _same_product_llm("https://www.skroutz.gr/s/123/LG-MR25GB.html")

    monkeypatch.setattr(
        source_url_llm_evaluation, "SOURCE_URL_LLM_EVALUATOR", evaluator
    )
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
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["MR25GB"],
                searched_urls=[],
                errors=[],
            )

        run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="skroutz",
                output_dir=tmp_path / "runs",
                dry_run=False,
                apply_high_confidence=False,
                llm_evaluate_candidates=True,
                llm_auto_apply_candidates=True,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        assert session.query(SourceUrl).count() == 0
        assert calls == []


def test_llm_cannot_apply_invalid_bestprice_url_shape(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ECOMMERCE_SOURCE_URL_LLM_ENABLED", "true")
    invalid_url = "https://www.bestprice.gr/search?q=MR25GB"
    monkeypatch.setattr(
        source_url_llm_evaluation,
        "SOURCE_URL_LLM_EVALUATOR",
        lambda _candidate, _config: _same_product_llm(invalid_url),
    )
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        evidence = _bestprice_review_evidence(product, url=invalid_url)

        def resolver(_product, _source):
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["MR25GB"],
                searched_urls=[],
                errors=[],
            )

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="bestprice",
                output_dir=tmp_path / "runs",
                dry_run=False,
                apply_high_confidence=False,
                llm_evaluate_candidates=True,
                llm_auto_apply_candidates=True,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidate = session.query(SourceUrlCandidate).one()

        assert session.query(SourceUrl).count() == 0
        assert stored_candidate.status == "needs_review"
        assert "not_bestprice_product_url" in stored_candidate.notes

    assert result.summary["llm_auto_applied_candidate_count"] == 0


def test_llm_cannot_apply_different_selected_bestprice_url(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ECOMMERCE_SOURCE_URL_LLM_ENABLED", "true")
    monkeypatch.setattr(
        source_url_llm_evaluation,
        "SOURCE_URL_LLM_EVALUATOR",
        lambda _candidate, _config: _same_product_llm(
            "https://www.bestprice.gr/item/222222/different-lg-remote.html"
        ),
    )
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        evidence = _bestprice_review_evidence(product)

        def resolver(_product, _source):
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["MR25GB"],
                searched_urls=[],
                errors=[],
            )

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="bestprice",
                output_dir=tmp_path / "runs",
                dry_run=False,
                apply_high_confidence=False,
                llm_evaluate_candidates=True,
                llm_auto_apply_candidates=True,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidate = session.query(SourceUrlCandidate).one()

        assert session.query(SourceUrl).count() == 0
        assert stored_candidate.status == "needs_review"
        assert "selected_url_not_candidate" in stored_candidate.notes

    assert result.summary["llm_auto_applied_candidate_count"] == 0


def test_llm_cannot_override_conflicting_manual_source_url(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ECOMMERCE_SOURCE_URL_LLM_ENABLED", "true")
    monkeypatch.setattr(
        source_url_llm_evaluation,
        "SOURCE_URL_LLM_EVALUATOR",
        lambda _candidate, _config: _same_product_llm(),
    )
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        manual = SourceUrl(
            catalog_product_id=row.id,
            catalog_source=row.catalog_source,
            model=row.model,
            mpn=row.mpn or "",
            manufacturer=row.manufacturer or "",
            source_name="bestprice",
            source_domain="www.bestprice.gr",
            url="https://www.bestprice.gr/item/111/manual.html",
            url_normalized="https://www.bestprice.gr/item/111/manual.html",
            status="active",
            url_type="manual",
            provenance="manual",
            trust_level="manual",
            failure_count=0,
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(manual)
        session.flush()
        product = _product(catalog_product_id=row.id)
        evidence = _bestprice_review_evidence(product)

        def resolver(_product, _source):
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["MR25GB"],
                searched_urls=[],
                errors=[],
            )

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="bestprice",
                output_dir=tmp_path / "runs",
                dry_run=False,
                apply_high_confidence=False,
                llm_evaluate_candidates=True,
                llm_auto_apply_candidates=True,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidates = session.query(SourceUrlCandidate).all()

        assert len(stored_candidates) == 1
        assert stored_candidates[0].status == "needs_review"
        assert session.query(SourceUrl).count() == 1
        assert result.summary["llm_source_url_write_results"][0]["reason"] == (
            "manual_source_url_exists"
        )


def test_llm_cannot_apply_below_auto_apply_threshold(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ECOMMERCE_SOURCE_URL_LLM_ENABLED", "true")

    def evaluator(_candidate, _config):
        return SourceUrlLLMEvaluation(
            verdict="same_product",
            confidence=Decimal("0.80"),
            apply_recommendation="auto_apply",
            reasons=["Likely matching product."],
            positive_evidence=["MR25GB"],
            negative_evidence=[],
            selected_candidate_url="https://www.bestprice.gr/item/987654/lg-mr25gb.html",
            warnings=[],
        )

    monkeypatch.setattr(
        source_url_llm_evaluation, "SOURCE_URL_LLM_EVALUATOR", evaluator
    )
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        evidence = _bestprice_review_evidence(product)

        def resolver(_product, _source):
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["MR25GB"],
                searched_urls=[],
                errors=[],
            )

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="bestprice",
                output_dir=tmp_path / "runs",
                dry_run=False,
                apply_high_confidence=False,
                llm_evaluate_candidates=True,
                llm_auto_apply_candidates=True,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidate = session.query(SourceUrlCandidate).one()

        assert session.query(SourceUrl).count() == 0
        assert stored_candidate.status == "needs_review"
        assert stored_candidate.evidence_json["llm_evaluation"]["confidence"] == "0.80"

    assert result.summary["llm_auto_applied_candidate_count"] == 0


def test_malformed_llm_output_does_not_write_source_url(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ECOMMERCE_SOURCE_URL_LLM_ENABLED", "true")

    def evaluator(_candidate, _config):
        raise SourceUrlLLMEvaluationError("bad schema")

    monkeypatch.setattr(
        source_url_llm_evaluation, "SOURCE_URL_LLM_EVALUATOR", evaluator
    )
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        evidence = _bestprice_review_evidence(product)

        def resolver(_product, _source):
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["MR25GB"],
                searched_urls=[],
                errors=[],
            )

        result = run_source_url_agent(
            products=[product],
            options=SourceUrlAgentOptions(
                mode="catalog",
                source="bestprice",
                output_dir=tmp_path / "runs",
                dry_run=False,
                apply_high_confidence=False,
                llm_evaluate_candidates=True,
                llm_auto_apply_candidates=True,
            ),
            registry=registry,
            session=session,
            resolver=resolver,
        )

        stored_candidate = session.query(SourceUrlCandidate).one()

        assert session.query(SourceUrl).count() == 0
        assert "llm_evaluation" not in stored_candidate.evidence_json

    assert result.summary["llm_malformed_response_count"] == 1
    assert any("llm_evaluation_failed" in warning for warning in result.warnings)


def test_agent_persists_high_confidence_needs_review_candidates_during_dry_run(
    tmp_path: Path,
) -> None:
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
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["LG MR25GB"],
                searched_urls=[],
                errors=[],
            )

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


def test_agent_discards_low_confidence_candidates_from_storage_and_artifacts(
    tmp_path: Path,
) -> None:
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
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["LG MR25GB"],
                searched_urls=[],
                errors=[],
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

        assert session.query(SourceUrlDiscoveryRun).count() == 1
        assert session.query(SourceUrlCandidate).count() == 0
        assert session.query(SourceUrl).count() == 0

    with result.artifacts.source_url_results.open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        assert list(csv.DictReader(handle)) == []
    assert result.summary["needs_review_count"] == 1
    assert result.summary["persisted_candidate_count"] == 0
    assert result.summary["discarded_low_confidence_candidate_count"] == 1


def test_agent_persists_matched_candidates_during_dry_run_without_source_url_write(
    tmp_path: Path,
) -> None:
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
            return SourceSearchResult(
                evidence=[evidence],
                searched_queries=["MR25GB"],
                searched_urls=[],
                errors=[],
            )

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


def test_agent_persists_terminal_error_candidates_for_review_filtering(
    tmp_path: Path,
) -> None:
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


def test_agent_persists_terminal_not_found_candidates_for_review_filtering(
    tmp_path: Path,
) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)

        def resolver(_product, _source):
            return SourceSearchResult(
                evidence=[], searched_queries=["MR25GB"], searched_urls=[], errors=[]
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

        assert stored_candidate.match_status == "not_found"
        assert stored_candidate.status == "not_found"
        assert stored_candidate.confidence_score == Decimal("0.0000")

    assert result.summary["not_found_count"] == 1
    assert result.summary["persisted_candidate_count"] == 1


def test_source_url_agent_csv_run_requires_database_for_direct_persistence(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("ECOMMERCE_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    input_path = tmp_path / "input.csv"
    input_path.write_text("model,mpn,name\n005606,MR25GB,LG Remote\n", encoding="utf-8")

    code = source_url_agent_job.main(
        ["run", "--input", str(input_path), "--source", "skroutz"]
    )

    assert code == 1
    assert "requires ECOMMERCE_DATABASE_URL" in capsys.readouterr().err


def test_source_url_agent_run_api_dry_run_from_catalog_persists_run_and_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(API_EXECUTE_DURABLE_JOBS_INLINE_ENV_VAR, "true")
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
            "llm_evaluate_candidates": True,
            "llm_auto_apply_candidates": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"]
    assert payload["dry_run"] is True
    assert payload["llm_evaluate_candidates"] is True
    assert payload["llm_auto_apply_candidates"] is True
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
        assert job.payload_json["request"]["llm_evaluate_candidates"] is True
        assert job.payload_json["request"]["llm_auto_apply_candidates"] is True
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


def test_source_url_agent_run_api_enqueues_only_when_api_inline_execution_disabled(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(API_EXECUTE_DURABLE_JOBS_INLINE_ENV_VAR, "false")
    client, database_url = _run_api_client(tmp_path, monkeypatch)

    def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("Source URL Agent job should not execute inline")

    monkeypatch.setattr(
        source_url_agent_run_routes, "execute_source_url_agent_job", fail_if_executed
    )
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
    assert payload["status"] == "queued"
    assert payload["summary"]["selected_count"] == 1
    assert payload["summary"]["task_total_count"] == 1

    with session_scope(database_url) as session:
        run = (
            session.query(SourceUrlDiscoveryRun)
            .filter_by(run_id=payload["run_id"])
            .one()
        )
        task = (
            session.query(SourceUrlDiscoveryTask)
            .filter_by(run_id=payload["run_id"])
            .one()
        )
        job = get_job_by_id(session, payload["run_id"])
        assert run.status == "queued"
        assert task.status == "queued"
        assert session.query(SourceUrlCandidate).count() == 0
        assert job.status == "queued"


def test_source_url_agent_worker_executes_queued_run_and_persists_progress(
    tmp_path: Path, monkeypatch
) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        source_url_agent_run_routes,
        "execute_source_url_agent_job",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        source_url_agent_job_handler, "SOURCE_URL_AGENT_JOB_RESOLVER", _fake_resolver
    )
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


def test_source_url_agent_worker_marks_failed_run_and_job_on_execution_error(
    tmp_path: Path, monkeypatch
) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        source_url_agent_run_routes,
        "execute_source_url_agent_job",
        lambda *_args, **_kwargs: None,
    )

    def failing_resolver(_product, _source):
        raise RuntimeError("resolver exploded")

    monkeypatch.setattr(
        source_url_agent_job_handler, "SOURCE_URL_AGENT_JOB_RESOLVER", failing_resolver
    )
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


def test_source_url_agent_background_execution_noops_when_worker_already_claimed_job(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        create_queued_job(
            session,
            job_type=SOURCE_URL_AGENT_JOB_TYPE,
            payload={
                "run_id": "job-source-agent",
                "request": {"source": "bestprice", "mode": "catalog"},
            },
            job_id="job-source-agent",
        )
        mark_running(session, "job-source-agent")

    def should_not_run(_product, _source):
        raise AssertionError(
            "running jobs should not be executed by an unclaimed background task"
        )

    job = source_url_agent_job_handler.execute_source_url_agent_job(
        "job-source-agent", resolver=should_not_run
    )

    assert job.status == "running"
    with session_scope(database_url) as session:
        persisted = get_job_by_id(session, "job-source-agent")
        assert persisted.status == "running"
        assert persisted.attempt_count == 1


def test_source_url_agent_run_api_lists_persisted_error_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)

    def error_resolver(product, source):
        return SourceSearchResult(
            evidence=[],
            searched_queries=[f"{product.manufacturer} {product.mpn}"],
            searched_urls=[f"https://{source.source_domain}/search?q={product.mpn}"],
            errors=[f"https://{source.source_domain}/search?q={product.mpn}: http_500"],
        )

    monkeypatch.setattr(
        source_url_agent_api_state, "SOURCE_URL_AGENT_API_RESOLVER", error_resolver
    )
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

    candidates = client.get(
        "/api/source-url-agent/candidates", params={"status": "error", "run_id": run_id}
    )

    assert candidates.status_code == 200
    payload = candidates.json()
    assert payload["total"] == 1
    assert payload["items"][0]["status"] == "error"
    assert payload["items"][0]["match_status"] == "error"
    assert "http_500" in payload["items"][0]["notes"]


def test_vendor_sources_agent_run_namespace_delegates_to_source_url_agent(
    tmp_path: Path, monkeypatch
) -> None:
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


def test_source_url_agent_run_api_accepts_selected_models(
    tmp_path: Path, monkeypatch
) -> None:
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
        candidate_models = {
            candidate.model for candidate in session.query(SourceUrlCandidate).all()
        }
        assert candidate_models == {"SELECT-1", "SELECT-2"}


def test_source_url_agent_run_api_enforces_bounded_default_limit(
    tmp_path: Path, monkeypatch
) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        source_url_agent_api_validation, "DEFAULT_API_MAX_PRODUCTS_PER_BATCH", 2
    )
    with session_scope(database_url) as session:
        for index in range(4):
            _catalog_product(session, model=f"MODEL-{index}", mpn=f"MPN-{index}")

    response = client.post(
        "/api/source-url-agent/runs", json={"source": "bestprice", "mode": "catalog"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["selected_count"] == 2
    with session_scope(database_url) as session:
        assert session.query(SourceUrlCandidate).count() == 2


def test_source_url_agent_run_artifact_endpoint_returns_safe_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    client, database_url = _run_api_client(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)

    run_response = client.post(
        "/api/source-url-agent/runs",
        json={
            "source": "bestprice",
            "mode": "catalog",
            "catalog_product_id": product.id,
            "limit": 1,
        },
    )
    run_id = run_response.json()["run_id"]
    artifact_response = client.get(f"/api/source-url-agent/runs/{run_id}/artifacts")

    assert artifact_response.status_code == 200
    payload = artifact_response.json()
    assert payload["run_id"] == run_id
    names = {item["name"] for item in payload["items"]}
    assert "source_url_run_summary.json" in names
    assert all(item["is_allowed"] for item in payload["items"])
    assert all(
        item["read_url"].startswith("/api/artifacts/read?path=")
        for item in payload["items"]
    )
