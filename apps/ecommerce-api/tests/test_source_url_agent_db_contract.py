import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.db.models import Base, CatalogProductRow, SourceUrl, SourceUrlCandidate, SourceUrlDiscoveryRun  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.source_url_agent.candidate_transfer import (  # noqa: E402
    export_source_url_candidates,
    export_source_url_transfer,
    import_source_url_candidates,
    import_source_url_transfer,
)
from ecommerce.source_url_agent.candidates import candidate_from_evidence  # noqa: E402
from ecommerce.source_url_agent.evidence import extract_page_evidence  # noqa: E402
from ecommerce.source_url_agent.persistence import (  # noqa: E402
    apply_high_confidence_source_urls,
    persist_candidate_rows,
    write_candidate_source_url,
)
from ecommerce.source_url_agent.products import AgentProduct  # noqa: E402
from ecommerce.source_url_agent.review import apply_review_csv  # noqa: E402
from ecommerce.source_url_agent.scoring import score_candidate  # noqa: E402
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


def test_source_urls_upsert_dry_run_and_apply_behavior(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        candidate = _candidate(product)

        dry = write_candidate_source_url(session, candidate, trust_level="high_confidence", apply=False)
        assert dry.action == "created"
        assert session.query(SourceUrl).count() == 0

        applied = write_candidate_source_url(session, candidate, trust_level="high_confidence", apply=True)
        stored = session.query(SourceUrl).one()

    assert applied.action == "created"
    assert stored.url_type == "discovered"
    assert stored.trust_level == "high_confidence"
    assert stored.status == "active"


def test_apply_high_confidence_requires_confidence_above_threshold(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id, price=Decimal("10.00"))
        source = load_source_registry().get("skroutz")
        evidence = extract_page_evidence(
            product=product,
            source=source,
            requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
            final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
            html_text=_html(),
        )
        score = score_candidate(product=product, source=source, evidence=evidence)
        candidate = candidate_from_evidence(
            run_id="run-1",
            product=product,
            source=source,
            evidence=evidence,
            score=score,
            expected_listing="listed",
            competing_candidates_count=0,
            searched_queries=["LG MR25GB"],
            status="needs_review",
        )

        results = apply_high_confidence_source_urls(session, [candidate], apply=True)

        assert results == []
        assert candidate.status == "needs_review"
        assert session.query(SourceUrl).count() == 0


def test_review_csv_apply_accept_and_replace_url(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    review_dir = tmp_path / "run-1"
    review_dir.mkdir()
    review_file = review_dir / "needs_review_source_urls_reviewed.csv"
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        review_file.write_text(
            "model,catalog_product_id,catalog_name,mpn,manufacturer,category,own_price,source_name,source_domain,source_type,"
            "expected_listing,candidate_url,canonical_url,candidate_title,candidate_price,match_status,confidence_score,match_method,"
            "evidence_mpn,evidence_brand,evidence_model,evidence_category,evidence_price,competing_candidates_count,searched_queries,"
            "notes,checked_at,review_decision,reviewed_url,review_notes,reviewed_by,reviewed_at\n"
            f"005606,{row.id},Product,MR25GB,LG,TV Control,19.00,skroutz,www.skroutz.gr,marketplace,listed,"
            "https://www.skroutz.gr/s/123,https://www.skroutz.gr/s/123,LG Remote,19.00,needs_review,0.7500,name_and_brand,"
            "missing,found:LG,missing,found:tv,compatible,1,MR25GB,,2026-05-03T12:00:00+00:00,"
            "accept,,approved,tester,2026-05-03T12:00:00+00:00\n",
            encoding="utf-8",
        )

        dry = apply_review_csv(session, review_file=review_file, apply=False)
        assert session.query(SourceUrl).count() == 0

        applied = apply_review_csv(session, review_file=review_file, apply=True)
        stored = session.query(SourceUrl).one()

    assert dry.counters["accepted_count"] == 1
    assert applied.counters["accepted_count"] == 1
    assert stored.trust_level == "manual"
    assert stored.url_type == "discovered"


def test_candidate_rows_persist_deterministic_shape(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    with session_scope(database_url) as session:
        row = _catalog_product(session)
        product = _product(catalog_product_id=row.id)
        candidate = _candidate(product)

        rows = persist_candidate_rows(session, [candidate])
        stored = rows[0]

        assert session.query(SourceUrlCandidate).count() == 1
        assert stored.run_id == "run-1"
        assert stored.catalog_product_id == row.id
        assert stored.candidate_url == "https://www.skroutz.gr/s/123/LG-MR25GB.html"
        assert stored.match_status == "matched"
        assert stored.status == "pending"
        assert stored.evidence_json["mpn"]["expected"] == "MR25GB"


def test_source_url_candidate_export_import_relinks_catalog_product(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    source_database_url = _sqlite_url(source_dir)
    target_database_url = _sqlite_url(target_dir)
    _create_schema(source_database_url)
    _create_schema(target_database_url)
    export_path = tmp_path / "source-url-candidates.json"

    with session_scope(source_database_url) as session:
        product = _catalog_product(session)
        session.add(
            SourceUrlDiscoveryRun(
                run_id="run-transfer",
                source_name="skroutz",
                mode="catalog",
                status="completed",
                selected_count=1,
                candidate_count=1,
                matched_count=0,
                needs_review_count=1,
                not_found_count=0,
                error_count=0,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            SourceUrlCandidate(
                run_id="run-transfer",
                catalog_product_id=product.id,
                catalog_source=product.catalog_source,
                model=product.model,
                mpn=product.mpn,
                manufacturer=product.manufacturer,
                product_name=product.name,
                category=product.category,
                own_price=Decimal("19.00"),
                source_name="skroutz",
                source_domain="www.skroutz.gr",
                source_type="marketplace",
                expected_listing="listed",
                candidate_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
                canonical_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
                candidate_title="LG MR25GB",
                candidate_price=Decimal("18.50"),
                match_status="needs_review",
                confidence_score=Decimal("0.8000"),
                match_method="manual_review_required",
                evidence_json={"mpn": {"found": True}},
                competing_candidates_count=1,
                searched_queries_json=["LG MR25GB"],
                status="needs_review",
                notes="needs operator decision",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        export_result = export_source_url_candidates(session, export_path)

    with session_scope(target_database_url) as session:
        target_product = _catalog_product(session)
        dry_result = import_source_url_candidates(session, export_path, apply=False)
        assert session.query(SourceUrlCandidate).count() == 0

        applied_result = import_source_url_candidates(session, export_path, apply=True)
        imported = session.query(SourceUrlCandidate).one()
        assert imported.catalog_product_id == target_product.id
        assert imported.candidate_url == "https://www.skroutz.gr/s/123/LG-MR25GB.html"

        second_apply = import_source_url_candidates(session, export_path, apply=True)
        assert session.query(SourceUrlCandidate).count() == 1

    assert export_result.counters["candidate_count"] == 1
    assert dry_result.counters["created_candidate_count"] == 1
    assert applied_result.counters["created_candidate_count"] == 1
    assert second_apply.counters["updated_candidate_count"] == 1


def test_source_url_transfer_exports_sources_and_candidates(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    source_database_url = _sqlite_url(source_dir)
    target_database_url = _sqlite_url(target_dir)
    _create_schema(source_database_url)
    _create_schema(target_database_url)
    export_path = tmp_path / "source-url-transfer.json"

    with session_scope(source_database_url) as session:
        product = _catalog_product(session)
        session.add(
            SourceUrl(
                catalog_product_id=product.id,
                catalog_source=product.catalog_source,
                model=product.model,
                mpn=product.mpn,
                manufacturer=product.manufacturer,
                source_name="skroutz",
                source_domain="www.skroutz.gr",
                url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
                url_normalized="https://www.skroutz.gr/s/123/LG-MR25GB.html",
                status="active",
                url_type="manual",
                trust_level="manual",
                added_by="tester",
                notes="portable",
                failure_count=0,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            SourceUrlCandidate(
                run_id="run-transfer",
                catalog_product_id=product.id,
                catalog_source=product.catalog_source,
                model=product.model,
                mpn=product.mpn,
                manufacturer=product.manufacturer,
                product_name=product.name,
                category=product.category,
                own_price=Decimal("19.00"),
                source_name="skroutz",
                source_domain="www.skroutz.gr",
                source_type="marketplace",
                candidate_url="https://www.skroutz.gr/s/124/LG-MR25GB.html",
                canonical_url="https://www.skroutz.gr/s/124/LG-MR25GB.html",
                candidate_title="LG MR25GB",
                match_status="needs_review",
                confidence_score=Decimal("0.7000"),
                match_method="manual_review_required",
                competing_candidates_count=1,
                status="needs_review",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        export_result = export_source_url_transfer(session, export_path)

    with session_scope(target_database_url) as session:
        target_product = _catalog_product(session)
        dry_result = import_source_url_transfer(session, export_path, apply=False)
        assert session.query(SourceUrl).count() == 0
        assert session.query(SourceUrlCandidate).count() == 0

        applied_result = import_source_url_transfer(session, export_path, apply=True)
        imported_source_url = session.query(SourceUrl).one()
        imported_candidate = session.query(SourceUrlCandidate).one()

        assert imported_source_url.catalog_product_id == target_product.id
        assert imported_source_url.url == "https://www.skroutz.gr/s/123/LG-MR25GB.html"
        assert imported_source_url.trust_level == "manual"
        assert imported_candidate.catalog_product_id == target_product.id
        assert imported_candidate.candidate_url == "https://www.skroutz.gr/s/124/LG-MR25GB.html"

        second_apply = import_source_url_transfer(session, export_path, apply=True)
        assert session.query(SourceUrl).count() == 1
        assert session.query(SourceUrlCandidate).count() == 1

    assert export_result.counters["source_url_count"] == 1
    assert export_result.counters["candidate_count"] == 1
    assert dry_result.counters["created_source_url_count"] == 1
    assert dry_result.counters["created_candidate_count"] == 1
    assert applied_result.counters["created_source_url_count"] == 1
    assert applied_result.counters["created_candidate_count"] == 1
    assert second_apply.counters["updated_source_url_count"] == 1
    assert second_apply.counters["updated_candidate_count"] == 1
