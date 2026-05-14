import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models import Base  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.source_urls import SourceUrl, SourceUrlCandidate, SourceUrlDiscoveryRun  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.source_url_agent.agent import SourceUrlAgentOptions, run_source_url_agent  # noqa: E402
from ecommerce.source_url_agent.candidates import candidate_from_evidence, keep_candidate  # noqa: E402
from ecommerce.source_url_agent.composite import detect_composite_mismatch, extract_product_code_identifiers  # noqa: E402
from ecommerce.source_url_agent.evidence import extract_page_evidence  # noqa: E402
from ecommerce.source_url_agent.products import AgentProduct  # noqa: E402
from ecommerce.source_url_agent.scoring import score_candidate  # noqa: E402
from ecommerce.source_url_agent.search import SourceSearchResult  # noqa: E402
from ecommerce.source_url_agent.sources import load_source_registry  # noqa: E402


NOW = datetime(2026, 5, 3, 12, tzinfo=timezone.utc)


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _create_schema(database_url: str) -> None:
    Base.metadata.create_all(get_engine(database_url))


def _oven_product(**overrides) -> AgentProduct:
    values = {
        "catalog_product_id": None,
        "catalog_source": "sourceCata",
        "model": "123456",
        "mpn": "HBA514BS3",
        "name": "Bosch HBA514BS3 oven",
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


def _catalog_product(session, *, model: str = "123456", mpn: str = "HBA514BS3", name: str = "Bosch HBA514BS3 oven") -> CatalogProductRow:
    row = CatalogProductRow(
        catalog_source="sourceCata",
        model=model,
        mpn=mpn,
        name=name,
        category="Ovens",
        raw_category="Ovens",
        manufacturer="Bosch",
        status=1,
        active=True,
        imported_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def _html(title: str, *, mpn: str = "HBA514BS3", body: str = "") -> str:
    body_text = body or f"Brand Bosch MPN {mpn} {title}"
    return f"""
    <html>
      <head>
        <title>{title}</title>
        <link rel="canonical" href="https://www.skroutz.gr/s/123/Bosch-HBA514BS3.html" />
        <script type="application/ld+json">
        {{
          "@type": "Product",
          "name": "{title}",
          "brand": {{"name": "Bosch"}},
          "mpn": "{mpn}",
          "category": "Ovens"
        }}
        </script>
      </head>
      <body>{body_text}</body>
    </html>
    """


def _evidence(product: AgentProduct, title: str, *, mpn: str | None = None, body: str = ""):
    source = load_source_registry().get("skroutz")
    return extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.skroutz.gr/s/123/Bosch-HBA514BS3.html",
        final_url="https://www.skroutz.gr/s/123/Bosch-HBA514BS3.html",
        html_text=_html(title, mpn=mpn if mpn is not None else product.mpn, body=body),
    )


def _score(product: AgentProduct, title: str):
    source = load_source_registry().get("skroutz")
    evidence = _evidence(product, title)
    return score_candidate(product=product, source=source, evidence=evidence), evidence, source


def test_extract_product_code_identifiers_finds_extra_mpn_like_codes() -> None:
    assert extract_product_code_identifiers("Bosch HBA514BS3 + PKE61RBA2E") == ("HBA514BS3", "PKE61RBA2E")


def test_single_oven_rejects_candidate_with_ceramic_hob_phrase_and_extra_identifier() -> None:
    product = _oven_product()
    title = "Bosch \u03a6\u03bf\u03cd\u03c1\u03bd\u03bf\u03c2 \u0397\u03bb\u03b5\u03ba\u03c4\u03c1\u03b9\u03ba\u03cc\u03c2 \u0386\u03bd\u03c9 \u03a0\u03ac\u03b3\u03ba\u03bf\u03c5 HBA514BS3 \u03bc\u03b5 \u039a\u03b5\u03c1\u03b1\u03bc\u03b9\u03ba\u03ad\u03c2 \u0395\u03c3\u03c4\u03af\u03b5\u03c2 PKE61RBA2E"

    score, evidence, source = _score(product, title)
    candidate = candidate_from_evidence(
        run_id="run-1",
        product=product,
        source=source,
        evidence=evidence,
        score=score,
        expected_listing="listed",
        competing_candidates_count=0,
        searched_queries=["Bosch HBA514BS3"],
    )

    assert score.confidence_score == 0.0
    assert score.match_status == "not_found"
    assert score.match_method == "composite_product_mismatch"
    assert keep_candidate(candidate)
    assert candidate.evidence_json["composite"] == {
        "is_mismatch": True,
        "reason": "candidate_contains_composite_phrase",
        "markers": ["me keramikes esties", "expected_identifier_joined_with_extra_identifier"],
        "extra_identifiers": ["PKE61RBA2E"],
    }


def test_single_oven_rejects_candidate_with_plus_joined_extra_identifier() -> None:
    product = _oven_product()
    score, _, _ = _score(product, "Bosch HBA514BS3 + PKE61RBA2E")

    assert score.confidence_score == 0.0
    assert score.match_status == "not_found"
    assert score.match_method == "composite_product_mismatch"
    assert "PKE61RBA2E" in score.notes


@pytest.mark.parametrize(
    "title,marker",
    [
        ("Bosch HBA514BS3 \u03bc\u03b5 \u03b5\u03c3\u03c4\u03af\u03b5\u03c2", "me esties"),
        ("Bosch HBA514BS3 \u03bc\u03b5 \u03b5\u03c0\u03b1\u03b3\u03c9\u03b3\u03b9\u03ba\u03ad\u03c2 \u03b5\u03c3\u03c4\u03af\u03b5\u03c2", "me epagogikes esties"),
        ("Bosch HBA514BS3 \u03bc\u03b5 \u03b5\u03c0\u03b1\u03b3\u03c9\u03b3\u03b9\u03ba\u03ad\u03c2", "me epagogikes"),
        ("Bosch HBA514BS3 \u03bc\u03b5 \u03ba\u03b5\u03c1\u03b1\u03bc\u03b9\u03ba\u03ad\u03c2 \u03b5\u03c3\u03c4\u03af\u03b5\u03c2", "me keramikes esties"),
        ("Bosch HBA514BS3 \u03bc\u03b5 \u03ba\u03b5\u03c1\u03b1\u03bc\u03b9\u03ba\u03ad\u03c2", "me keramikes"),
        ("Bosch HBA514BS3 \u03bc\u03b5 \u039a\u03b5\u03c1\u03b1\u03bc\u03b9\u03ba\u03b5\u03c2 \u0395\u03c3\u03c4\u03b9\u03b5\u03c2", "me keramikes esties"),
        ("Bosch \u03c6\u03bf\u03cd\u03c1\u03bd\u03bf\u03c2 \u03bc\u03b5 \u03b5\u03c3\u03c4\u03af\u03b5\u03c2 HBA514BS3", "foyrnos me esties"),
        ("Bosch fournos me esties HBA514BS3", "fournos me esties"),
        ("Bosch HBA514BS3 \u03bc\u03b1\u03b6\u03af \u03bc\u03b5 PKE61RBA2E", "mazi me"),
    ],
)
def test_single_oven_rejects_greek_composite_phrase_variants(title: str, marker: str) -> None:
    product = _oven_product()
    score, evidence, _ = _score(product, title)
    result = detect_composite_mismatch(product, evidence)

    assert result.is_mismatch
    assert marker in result.markers
    assert score.confidence_score == 0.0
    assert score.match_method == "composite_product_mismatch"


@pytest.mark.parametrize(
    "title",
    [
        "Bosch HBA514BS3 & PKE61RBA2E",
        "Bosch HBA514BS3 \u03ba\u03b1\u03b9 PKE61RBA2E",
        "Bosch HBA514BS3 and PKE61RBA2E",
        "Bosch HBA514BS3 with PKE61RBA2E",
        "Bosch HBA514BS3 \u03bc\u03b5 PKE61RBA2E",
    ],
)
def test_single_oven_rejects_expected_identifier_connected_to_extra_identifier(title: str) -> None:
    product = _oven_product()
    score, evidence, _ = _score(product, title)
    result = detect_composite_mismatch(product, evidence)

    assert result.is_mismatch
    assert "expected_identifier_joined_with_extra_identifier" in result.markers
    assert result.extra_identifiers == ("PKE61RBA2E",)
    assert score.match_method == "composite_product_mismatch"


@pytest.mark.parametrize(
    "title",
    [
        "Bosch HBA514BS3 set PKE61RBA2E",
        "Bosch HBA514BS3 \u03c3\u03b5\u03c4 PKE61RBA2E",
        "Bosch HBA514BS3 bundle PKE61RBA2E",
        "Bosch HBA514BS3 \u03c0\u03b1\u03ba\u03ad\u03c4\u03bf PKE61RBA2E",
    ],
)
def test_single_oven_rejects_bundle_words_when_extra_identifier_exists(title: str) -> None:
    product = _oven_product()
    score, evidence, _ = _score(product, title)
    result = detect_composite_mismatch(product, evidence)

    assert result.is_mismatch
    assert result.extra_identifiers == ("PKE61RBA2E",)
    assert score.match_method == "composite_product_mismatch"


def test_valid_single_product_with_expected_mpn_and_brand_scores_as_before() -> None:
    product = _oven_product()
    score, _, _ = _score(product, "Bosch HBA514BS3 oven")

    assert score.confidence_score == 1.0
    assert score.match_status == "matched"
    assert score.match_method == "exact_mpn_and_brand"


def test_valid_catalog_composite_product_is_not_rejected() -> None:
    product = _oven_product(
        mpn="HBA514BS3 + PKE61RBA2E",
        name="Bosch HBA514BS3 + PKE61RBA2E oven and hob set",
    )
    title = "Bosch HBA514BS3 + PKE61RBA2E oven and hob set"
    score, evidence, _ = _score(product, title)
    result = detect_composite_mismatch(product, evidence)

    assert not result.is_mismatch
    assert score.match_method == "exact_mpn_and_brand"
    assert score.confidence_score == 1.0


def test_valid_catalog_composite_phrase_product_is_not_rejected() -> None:
    product = _oven_product(
        name="Bosch HBA514BS3 \u03c6\u03bf\u03cd\u03c1\u03bd\u03bf\u03c2 \u03bc\u03b5 \u03b5\u03c3\u03c4\u03af\u03b5\u03c2",
    )
    score, evidence, _ = _score(product, product.name)
    result = detect_composite_mismatch(product, evidence)

    assert not result.is_mismatch
    assert score.match_method == "exact_mpn_and_brand"
    assert score.confidence_score == 1.0


def test_source_url_agent_run_persists_composite_mismatch_candidate_for_operator_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    _create_schema(database_url)
    registry = load_source_registry()
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _oven_product(catalog_product_id=row.id)
        source = registry.get("skroutz")
        evidence = _evidence(product, "Bosch HBA514BS3 + PKE61RBA2E")

        def resolver(_product, _source):
            return SourceSearchResult(evidence=[evidence], searched_queries=["Bosch HBA514BS3"], searched_urls=[], errors=[])

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

        assert session.query(SourceUrlDiscoveryRun).count() == 1
        stored_candidate = session.query(SourceUrlCandidate).one()
        assert session.query(SourceUrl).count() == 0
        assert stored_candidate.match_status == "not_found"
        assert stored_candidate.match_method == "composite_product_mismatch"
        assert stored_candidate.evidence_json["composite"]["extra_identifiers"] == ["PKE61RBA2E"]

    assert result.candidates[0].confidence_score == 0.0
    assert result.candidates[0].match_method == "composite_product_mismatch"
    assert result.summary["persisted_candidate_count"] == 1
    assert result.summary["discarded_low_confidence_candidate_count"] == 0
    with result.artifacts.source_url_results.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["match_method"] == "composite_product_mismatch"
    assert "PKE61RBA2E" in rows[0]["notes"]
