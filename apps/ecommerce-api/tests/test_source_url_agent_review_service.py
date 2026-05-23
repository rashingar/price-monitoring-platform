import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.source_urls import SourceUrl, SourceUrlCandidate  # noqa: E402
from ecommerce.db.repositories.source_urls import create_or_update_manual_source_url  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.source_url_agent.review_service import (  # noqa: E402
    InvalidSourceUrlCandidateReviewError,
    SourceUrlCandidatePromotionError,
    SourceUrlCandidateReviewCommand,
    review_source_url_agent_candidate,
)

NOW = datetime(2026, 5, 3, 12, tzinfo=timezone.utc)
REVIEWED_AT = datetime(2026, 5, 4, 8, 30, tzinfo=timezone.utc)


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _database(tmp_path: Path, monkeypatch) -> str:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    Base.metadata.create_all(get_engine(database_url))
    return database_url


def _catalog_product(
    session, *, model: str = "005606", mpn: str = "MR25GB"
) -> CatalogProductRow:
    row = CatalogProductRow(
        catalog_source="sourceCata",
        model=model,
        mpn=mpn,
        name=f"Product {model}",
        category="TV Control",
        raw_category="TV Control",
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


def _candidate(
    session,
    product: CatalogProductRow | None,
    *,
    url: str | None = "https://www.bestprice.gr/item/1/lg-remote.html",
    notes: str | None = "initial note",
) -> SourceUrlCandidate:
    row = SourceUrlCandidate(
        run_id="run-1",
        catalog_product_id=product.id if product is not None else None,
        catalog_source=product.catalog_source if product is not None else "sourceCata",
        model=product.model if product is not None else "005606",
        mpn=product.mpn if product is not None else "MR25GB",
        manufacturer=product.manufacturer if product is not None else "LG",
        product_name=product.name if product is not None else "Product 005606",
        category=product.category if product is not None else "TV Control",
        own_price=Decimal("19.00"),
        source_name="bestprice",
        source_domain="www.bestprice.gr",
        source_type="marketplace",
        expected_listing="listed",
        candidate_url=url,
        canonical_url=url,
        candidate_title="LG Remote",
        candidate_price=Decimal("18.50"),
        match_status="needs_review",
        confidence_score=Decimal("0.6000"),
        match_method="exact_mpn_and_brand",
        evidence_json={"mpn": {"found": True, "fragment": "MR25GB"}},
        competing_candidates_count=1,
        searched_queries_json=["LG MR25GB"],
        status="needs_review",
        notes=notes,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(row)
    session.flush()
    return row


def test_accept_candidate_promotes_candidate_url(tmp_path: Path, monkeypatch) -> None:
    database_url = _database(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)
        result = review_source_url_agent_candidate(
            session,
            candidate.id,
            SourceUrlCandidateReviewCommand(
                decision="accept", reviewed_by="tester", reviewed_at=REVIEWED_AT
            ),
        )

        assert result.candidate.status == "accepted"
        assert result.source_url_promotion is not None
        assert result.source_url_promotion.action == "created"

    with session_scope(database_url) as session:
        stored = session.query(SourceUrl).one()
        assert stored.url == "https://www.bestprice.gr/item/1/lg-remote.html"
        assert stored.provenance == "discovery"


def test_accept_candidate_preserves_existing_manual_source_url_provenance(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _database(tmp_path, monkeypatch)
    candidate_url = "https://www.bestprice.gr/item/1/lg-remote.html"
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        create_or_update_manual_source_url(
            session,
            int(product.id),
            {
                "url": candidate_url,
                "source_name": "bestprice",
                "url_type": "manual",
                "trust_level": "manual",
                "added_by": "operator",
            },
        )
        candidate = _candidate(session, product, url=candidate_url)
        result = review_source_url_agent_candidate(
            session,
            candidate.id,
            SourceUrlCandidateReviewCommand(
                decision="accept", reviewed_by="tester", reviewed_at=REVIEWED_AT
            ),
        )

        assert result.candidate.status == "accepted"
        assert result.source_url_promotion is not None
        assert result.source_url_promotion.action in {"duplicate", "updated"}

    with session_scope(database_url) as session:
        stored = session.query(SourceUrl).one()
        assert stored.url == candidate_url
        assert stored.url_type == "manual"
        assert stored.provenance == "manual"


def test_accept_candidate_with_reviewed_url_promotes_reviewed_url(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _database(tmp_path, monkeypatch)
    reviewed_url = "https://www.bestprice.gr/item/2/reviewed.html"
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)
        result = review_source_url_agent_candidate(
            session,
            candidate.id,
            SourceUrlCandidateReviewCommand(
                decision="accept", reviewed_url=reviewed_url, reviewed_at=REVIEWED_AT
            ),
        )

        assert result.source_url_promotion is not None
        assert result.source_url_promotion.row is not None
        assert result.source_url_promotion.row.url == reviewed_url


def test_replace_url_requires_reviewed_url(tmp_path: Path, monkeypatch) -> None:
    database_url = _database(tmp_path, monkeypatch)
    with pytest.raises(
        InvalidSourceUrlCandidateReviewError,
        match="reviewed_url is required for replace_url.",
    ):
        with session_scope(database_url) as session:
            product = _catalog_product(session)
            candidate = _candidate(session, product)
            review_source_url_agent_candidate(
                session,
                candidate.id,
                SourceUrlCandidateReviewCommand(
                    decision="replace_url", reviewed_at=REVIEWED_AT
                ),
            )


def test_replace_url_promotes_reviewed_url(tmp_path: Path, monkeypatch) -> None:
    database_url = _database(tmp_path, monkeypatch)
    reviewed_url = "https://www.bestprice.gr/item/2/replacement.html"
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)
        result = review_source_url_agent_candidate(
            session,
            candidate.id,
            SourceUrlCandidateReviewCommand(
                decision="replace_url",
                reviewed_url=reviewed_url,
                reviewed_at=REVIEWED_AT,
            ),
        )

        assert result.candidate.status == "accepted"

    with session_scope(database_url) as session:
        stored = session.query(SourceUrl).one()
        assert stored.url == reviewed_url


def test_reject_does_not_promote_source_url(tmp_path: Path, monkeypatch) -> None:
    database_url = _database(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)
        result = review_source_url_agent_candidate(
            session,
            candidate.id,
            SourceUrlCandidateReviewCommand(decision="reject", reviewed_at=REVIEWED_AT),
        )

        assert result.candidate.status == "rejected"
        assert result.source_url_promotion is None

    with session_scope(database_url) as session:
        assert session.query(SourceUrl).count() == 0


def test_reviewed_by_defaults_to_operator(tmp_path: Path, monkeypatch) -> None:
    database_url = _database(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)
        result = review_source_url_agent_candidate(
            session,
            candidate.id,
            SourceUrlCandidateReviewCommand(
                decision="reject", reviewed_by=" ", reviewed_at=REVIEWED_AT
            ),
        )

        assert result.candidate.reviewed_by == "operator"


def test_review_notes_are_appended(tmp_path: Path, monkeypatch) -> None:
    database_url = _database(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product, notes="initial note")
        result = review_source_url_agent_candidate(
            session,
            candidate.id,
            SourceUrlCandidateReviewCommand(
                decision="reject",
                review_notes="not a match",
                reviewed_by="tester",
                reviewed_at=REVIEWED_AT,
            ),
        )

        assert (
            result.candidate.notes
            == f"initial note\nReview reject by tester at {REVIEWED_AT.isoformat()}: not a match"
        )
        assert result.candidate.updated_at == REVIEWED_AT


def test_missing_catalog_product_id_blocks_promotion(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _database(tmp_path, monkeypatch)
    with pytest.raises(
        SourceUrlCandidatePromotionError,
        match="catalog_product_id is required to promote a source URL.",
    ):
        with session_scope(database_url) as session:
            candidate = _candidate(session, None)
            review_source_url_agent_candidate(
                session,
                candidate.id,
                SourceUrlCandidateReviewCommand(
                    decision="accept", reviewed_at=REVIEWED_AT
                ),
            )


def test_missing_promoted_url_blocks_promotion(tmp_path: Path, monkeypatch) -> None:
    database_url = _database(tmp_path, monkeypatch)
    with pytest.raises(
        SourceUrlCandidatePromotionError,
        match="candidate_url is required to promote a source URL.",
    ):
        with session_scope(database_url) as session:
            product = _catalog_product(session)
            candidate = _candidate(session, product, url=None)
            review_source_url_agent_candidate(
                session,
                candidate.id,
                SourceUrlCandidateReviewCommand(
                    decision="accept", reviewed_at=REVIEWED_AT
                ),
            )


def test_promotion_uses_manual_trust_level_and_discovered_url_type(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _database(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)
        review_source_url_agent_candidate(
            session,
            candidate.id,
            SourceUrlCandidateReviewCommand(decision="accept", reviewed_at=REVIEWED_AT),
        )

    with session_scope(database_url) as session:
        stored = session.query(SourceUrl).one()
        assert stored.trust_level == "manual"
        assert stored.url_type == "discovered"


def test_promotion_uses_review_timestamp_for_last_seen_and_success(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _database(tmp_path, monkeypatch)
    with session_scope(database_url) as session:
        product = _catalog_product(session)
        candidate = _candidate(session, product)
        review_source_url_agent_candidate(
            session,
            candidate.id,
            SourceUrlCandidateReviewCommand(decision="accept", reviewed_at=REVIEWED_AT),
        )

    with session_scope(database_url) as session:
        stored = session.query(SourceUrl).one()
        assert stored.last_seen_at.replace(tzinfo=timezone.utc) == REVIEWED_AT
        assert stored.last_success_at.replace(tzinfo=timezone.utc) == REVIEWED_AT
        assert f"reviewed_at={REVIEWED_AT.isoformat()}" in stored.notes
