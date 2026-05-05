import csv
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pricefetcher.db.models import Base, CatalogProductRow, SourceUrl, SourceUrlCandidate, SourceUrlDiscoveryRun  # noqa: E402
from pricefetcher.db.session import get_engine, session_scope  # noqa: E402
from pricefetcher.jobs import source_url_agent as source_url_agent_job  # noqa: E402
from pricefetcher.source_urls import normalize_source_url  # noqa: E402
from pricefetcher.source_url_agent.agent import SourceUrlAgentOptions, run_source_url_agent  # noqa: E402
from pricefetcher.source_url_agent.artifacts import write_run_artifacts  # noqa: E402
from pricefetcher.source_url_agent.browser import _blocked_or_captcha  # noqa: E402
from pricefetcher.source_url_agent.candidate_transfer import export_source_url_candidates, import_source_url_candidates  # noqa: E402
from pricefetcher.source_url_agent.candidates import candidate_from_evidence  # noqa: E402
from pricefetcher.source_url_agent.evidence import error_evidence, extract_page_evidence  # noqa: E402
from pricefetcher.source_url_agent.persistence import (  # noqa: E402
    apply_high_confidence_source_urls,
    write_candidate_source_url,
)
from pricefetcher.source_url_agent.products import AgentProduct, read_products_from_csv  # noqa: E402
from pricefetcher.source_url_agent.review import apply_review_csv  # noqa: E402
from pricefetcher.source_url_agent.scoring import score_candidate  # noqa: E402
from pricefetcher.source_url_agent.search import SourceSearchResult, generate_search_queries  # noqa: E402
from pricefetcher.source_url_agent.sources import load_source_registry  # noqa: E402


NOW = datetime(2026, 5, 3, 12, tzinfo=timezone.utc)


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'pricefetcher.db'}"


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


def test_review_urls_are_not_product_urls() -> None:
    source = load_source_registry().get("bestprice")

    assert source.is_product_url("https://www.bestprice.gr/item/2160770054/tesla-43e655bus.html")
    assert not source.is_product_url("https://www.bestprice.gr/item/2160770054/tesla-43e655bus/review")
    assert not source.is_product_url("https://www.bestprice.gr/item/2160770054/tesla-43e655bus/review?sku=1")


def test_source_registry_accepts_only_locked_product_url_shapes() -> None:
    registry = load_source_registry()

    assert registry.get("skroutz").is_product_url(
        "https://www.skroutz.gr/s/49743700/Bosch-HBG7241B1-Fournos-ano-Pagou-71lt-P59-4ek-Mayros.html"
    )
    assert not registry.get("skroutz").is_product_url("https://www.skroutz.gr/c/1607/fournoi.html")

    assert registry.get("bestprice").is_product_url(
        "https://www.bestprice.gr/item/2160770054/tesla-43e655bus-smart-tileorasi-43-4k-uhd-dled-hdr.html"
    )
    assert not registry.get("bestprice").is_product_url("https://www.bestprice.gr/category/999/tileoraseis.html")

    assert registry.get("kotsovolos").is_product_url(
        "https://www.kotsovolos.gr/household-appliances/fridges/fridge-freezers/328817-lg-gbbsj20epy"
    )
    assert not registry.get("kotsovolos").is_product_url("https://www.kotsovolos.gr/household-appliances/fridges/fridge-freezers")

    assert registry.get("electronet").is_product_url(
        "https://www.electronet.gr/oikiakes-syskeyes/psygeia-katapsyktes/psygeiokatapsyktes/psygeiokatapsyktis-lg-gbbsj20dep-anthraki-d"
    )
    assert not registry.get("electronet").is_product_url("https://www.electronet.gr/oikiakes-syskeyes/psygeia-katapsyktes")

    assert registry.get("public").is_product_url(
        "https://www.public.gr/product/oikiakes-syskeyes/psygeia/psygeiokatapsiktes/lg-gbb566pzhmn-total-no-frost-462-lt-asimi-psugeiokatapsuktis/1557191"
    )
    assert not registry.get("public").is_product_url("https://www.public.gr/oikiakes-syskeyes/psygeia/psygeiokatapsiktes/lg-gbb566pzhmn")

    assert registry.get("plaisio").is_product_url(
        "https://www.plaisio.gr/product/mikres-oikiakes-siskeves/kathariotita/skoupes-sfouggaristres/rowenta-skoupa-sfouggaristra-x-clean-4-wet-and-dry-gz5035wo_4756177"
    )
    assert not registry.get("plaisio").is_product_url(
        "https://www.plaisio.gr/mikres-oikiakes-siskeves/kathariotita/skoupes-sfouggaristres/rowenta-skoupa-sfouggaristra-x-clean-4-wet-and-dry-gz5035wo_4756177"
    )


def test_non_product_url_markers_are_rejected() -> None:
    source = load_source_registry().get("public")

    assert not source.is_product_url(
        "https://www.public.gr/product/oikiakes-syskeyes/psygeia/psygeiokatapsiktes/lg-gbb566pzhmn-total-no-frost-462-lt-asimi-psugeiokatapsuktis/1557191?promo=true"
    )
    assert not source.is_product_url(
        "https://www.public.gr/product/oikiakes-syskeyes/psygeia/psygeiokatapsiktes/campaign-lg-gbb566pzhmn/1557191"
    )
    assert not source.is_product_url(
        "https://www.public.gr/product/oikiakes-syskeyes/psygeia/psygeiokatapsiktes/banner-lg-gbb566pzhmn/1557191"
    )
    assert not source.is_product_url(
        "https://www.public.gr/product/oikiakes-syskeyes/psygeia/psygeiokatapsiktes/lg-gbb566pzhmn-collection/1557191"
    )


def test_generate_search_queries_uses_only_manufacturer_plus_mpn() -> None:
    product = _product()
    source = load_source_registry().get("skroutz")

    queries = generate_search_queries(product, source)

    assert queries == ["LG MR25GB"]


def test_source_url_normalization_removes_tracking_and_fragment() -> None:
    normalized = normalize_source_url("HTTPS://WWW.Skroutz.GR/s/123?utm_source=x&sku=abc#reviews")

    assert normalized == "https://www.skroutz.gr/s/123?sku=abc"


def test_evidence_extraction_from_fake_html() -> None:
    product = _product()
    source = load_source_registry().get("skroutz")

    evidence = extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        html_text=_html(),
    )

    assert evidence.canonical_url == "https://www.skroutz.gr/s/123/LG-MR25GB.html"
    assert evidence.exact_mpn_found is True
    assert evidence.brand_found is True
    assert evidence.candidate_price is not None


def test_review_canonical_url_is_rejected_as_not_product_page() -> None:
    product = _product()
    source = load_source_registry().get("bestprice")
    evidence = extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.bestprice.gr/item/2160770054/tesla-43e655bus.html",
        final_url="https://www.bestprice.gr/item/2160770054/tesla-43e655bus.html",
        html_text="""
        <html>
          <head>
            <title>LG MR25GB Magic Remote Control</title>
            <link rel="canonical" href="https://www.bestprice.gr/item/2160770054/tesla-43e655bus/review" />
          </head>
          <body>LG MR25GB Magic Remote Control</body>
        </html>
        """,
    )

    score = score_candidate(product=product, source=source, evidence=evidence)

    assert evidence.error_code == "not_public_product_page"
    assert "canonical_url_ends_with_review" in evidence.error_message
    assert score.match_status == "error"
    assert score.confidence_score == 0.0


def test_review_title_markers_are_rejected_as_not_product_pages() -> None:
    product = _product()
    source = load_source_registry().get("electronet")
    for title in ("LG MR25GB Review", "Αξιολόγησε LG MR25GB", "Αξιολογήστε LG MR25GB"):
        evidence = extract_page_evidence(
            product=product,
            source=source,
            requested_url="https://www.electronet.gr/product/lg-magic-remote",
            final_url="https://www.electronet.gr/product/lg-magic-remote",
            html_text=f"""
            <html>
              <head>
                <title>{title}</title>
                <link rel="canonical" href="https://www.electronet.gr/product/lg-magic-remote" />
              </head>
              <body>LG MR25GB Magic Remote Control</body>
            </html>
            """,
        )

        score = score_candidate(product=product, source=source, evidence=evidence)

        assert evidence.error_code == "not_public_product_page"
        assert "title_contains_review_marker" in evidence.error_message
        assert score.match_status == "error"


def test_scoring_high_confidence_exact_mpn_match() -> None:
    product = _product()
    source = load_source_registry().get("skroutz")
    evidence = extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        html_text=_html(),
    )

    score = score_candidate(product=product, source=source, evidence=evidence)

    assert score.match_status == "matched"
    assert score.confidence_score == 1.0
    assert score.match_method == "exact_mpn_and_brand"


def test_scoring_exact_mpn_and_brand_at_threshold_needs_review() -> None:
    product = _product(price=Decimal("10.00"))
    source = load_source_registry().get("skroutz")
    evidence = extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        html_text=_html(),
    )

    score = score_candidate(product=product, source=source, evidence=evidence)

    assert score.match_method == "exact_mpn_and_brand"
    assert score.confidence_score == 0.9
    assert score.match_status == "needs_review"


def test_scoring_drops_exact_mpn_without_brand_method() -> None:
    product = _product(manufacturer="Sony")
    source = load_source_registry().get("electronet")
    evidence = extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.electronet.gr/product/lg-magic-remote",
        final_url="https://www.electronet.gr/product/lg-magic-remote",
        html_text=_html(),
    )

    score = score_candidate(product=product, source=source, evidence=evidence)

    assert evidence.exact_mpn_found is True
    assert evidence.brand_found is False
    assert score.match_status == "needs_review"
    assert score.match_method == "manual_review_required"


def test_title_only_match_forced_to_needs_review() -> None:
    product = _product(mpn="XYZ-999", name="LG Magic Remote Control")
    source = load_source_registry().get("electronet")
    evidence = extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.electronet.gr/product/lg-magic-remote",
        final_url="https://www.electronet.gr/product/lg-magic-remote",
        html_text=_html(include_mpn=False, title="LG Magic Remote Control"),
    )

    score = score_candidate(product=product, source=source, evidence=evidence)

    assert evidence.title_only is True
    assert score.match_status == "needs_review"
    assert score.confidence_score <= 0.50


def test_multiple_plausible_candidates_forced_to_needs_review() -> None:
    product = _product()
    source = load_source_registry().get("skroutz")
    evidence = extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        html_text=_html(),
    )

    score = score_candidate(product=product, source=source, evidence=evidence, competing_candidates_count=2)

    assert score.match_status == "needs_review"
    assert "plausible candidates" in score.notes


def test_marketplace_body_only_mpn_evidence_is_not_high_confidence() -> None:
    product = _product()
    source = load_source_registry().get("bestprice")
    html = """
    <html>
      <head>
        <title>JBL Partybox Encore 2 | BestPrice.gr</title>
        <link rel="canonical" href="https://www.bestprice.gr/item/999/jbl-partybox.html" />
      </head>
      <body>Related searches LG MR25GB Magic Remote</body>
    </html>
    """
    evidence = extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.bestprice.gr/item/999/jbl-partybox.html",
        final_url="https://www.bestprice.gr/item/999/jbl-partybox.html",
        html_text=html,
    )

    score = score_candidate(product=product, source=source, evidence=evidence)

    assert evidence.exact_mpn_source == "body"
    assert score.match_status == "needs_review"
    assert score.confidence_score <= 0.60


def test_blocked_valid_product_url_is_kept_for_review() -> None:
    product = _product()
    source = load_source_registry().get("skroutz")
    evidence = error_evidence(
        product=product,
        requested_url="https://www.skroutz.gr/s/49743700/Bosch-HBG7241B1-Fournos-ano-Pagou-71lt-P59-4ek-Mayros.html",
        final_url="https://www.skroutz.gr/s/49743700/Bosch-HBG7241B1-Fournos-ano-Pagou-71lt-P59-4ek-Mayros.html",
        error_code="blocked_or_captcha",
        error_message="Blocked page or CAPTCHA marker detected.",
    )

    score = score_candidate(product=product, source=source, evidence=evidence)

    assert score.match_status == "needs_review"
    assert score.confidence_score == 0.80
    assert score.match_method == "blocked_product_url"


def test_blocked_non_product_url_stays_error() -> None:
    product = _product()
    source = load_source_registry().get("skroutz")
    evidence = error_evidence(
        product=product,
        requested_url="https://www.skroutz.gr/search?keyphrase=LG+MR25GB",
        final_url="https://www.skroutz.gr/search?keyphrase=LG+MR25GB",
        error_code="blocked_or_captcha",
        error_message="Blocked page or CAPTCHA marker detected.",
    )

    score = score_candidate(product=product, source=source, evidence=evidence)

    assert score.match_status == "error"
    assert score.confidence_score == 0.0


def test_cloudflare_analytics_script_is_not_treated_as_blocked_page() -> None:
    product = _product()
    source = load_source_registry().get("skroutz")
    html = """
    <html>
      <head>
        <title>LG MR25GB Magic Remote Control | Skroutz.gr</title>
        <link rel="canonical" href="https://www.skroutz.gr/s/123/LG-MR25GB.html" />
        <script defer src="https://static.cloudflareinsights.com/beacon.min.js"></script>
        <script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>
        <script type="application/ld+json">
        {
          "@type": "Product",
          "name": "LG MR25GB Magic Remote Control",
          "brand": {"name": "LG"},
          "mpn": "MR25GB",
          "category": "TV Control"
        }
        </script>
      </head>
      <body>LG MR25GB Magic Remote Control TV Control</body>
    </html>
    """

    assert _blocked_or_captcha("LG MR25GB Magic Remote Control | Skroutz.gr", "LG MR25GB Magic Remote Control", html) is False

    evidence = extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        html_text=html,
    )

    assert evidence.blocked_or_captcha is False
    assert evidence.exact_mpn_found is True


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


def test_source_url_agent_csv_run_requires_database_for_direct_persistence(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("PRICEFETCHER_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    input_path = tmp_path / "input.csv"
    input_path.write_text("model,mpn,name\n005606,MR25GB,LG Remote\n", encoding="utf-8")

    code = source_url_agent_job.main(["run", "--input", str(input_path), "--source", "skroutz"])

    assert code == 1
    assert "requires PRICEFETCHER_DATABASE_URL" in capsys.readouterr().err
