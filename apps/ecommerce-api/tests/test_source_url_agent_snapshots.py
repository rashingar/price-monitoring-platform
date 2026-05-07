import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.source_urls import normalize_source_url  # noqa: E402
from ecommerce.source_url_agent.browser import _blocked_or_captcha  # noqa: E402
from ecommerce.source_url_agent.candidates import SourceUrlAgentCandidate, candidate_from_evidence  # noqa: E402
from ecommerce.source_url_agent.evidence import PageEvidence, error_evidence, extract_page_evidence  # noqa: E402
from ecommerce.source_url_agent.products import AgentProduct  # noqa: E402
from ecommerce.source_url_agent.scoring import CandidateScore, score_candidate  # noqa: E402
from ecommerce.source_url_agent.search import generate_search_queries  # noqa: E402
from ecommerce.source_url_agent.sources import load_source_registry  # noqa: E402


FIXED_CHECKED_AT = datetime(2026, 5, 3, 12, tzinfo=timezone.utc)


def _assert_snapshot(fixtures_root: Path, parts: tuple[str, ...], payload: dict[str, Any]) -> None:
    expected_path = fixtures_root / "golden_snapshots" / Path(*parts)
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert payload == expected


def _product(**overrides) -> AgentProduct:
    values = {
        "catalog_product_id": 5606,
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


def _valid_evidence(product: AgentProduct | None = None) -> PageEvidence:
    product = product or _product()
    source = load_source_registry().get("skroutz")
    return extract_page_evidence(
        product=product,
        source=source,
        requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        html_text=_html(),
    )


def _score_payload(score: CandidateScore) -> dict[str, Any]:
    return {
        "confidence_score": score.confidence_score,
        "match_status": score.match_status,
        "match_method": score.match_method,
        "notes": score.notes,
    }


def _candidate_payload(candidate: SourceUrlAgentCandidate) -> dict[str, Any]:
    normalized = replace(candidate, checked_at=FIXED_CHECKED_AT)
    return {
        "run_id": normalized.run_id,
        "model": normalized.product.model,
        "mpn": normalized.product.mpn,
        "manufacturer": normalized.product.manufacturer,
        "source_name": normalized.source_name,
        "source_domain": normalized.source_domain,
        "source_type": normalized.source_type,
        "expected_listing": normalized.expected_listing,
        "candidate_url": normalized.candidate_url,
        "canonical_url": normalized.canonical_url,
        "candidate_title": normalized.candidate_title,
        "candidate_price": str(normalized.candidate_price) if normalized.candidate_price is not None else "",
        "match_status": normalized.match_status,
        "confidence_score": normalized.confidence_score,
        "match_method": normalized.match_method,
        "status": normalized.status,
        "notes": normalized.notes,
        "checked_at": normalized.checked_at.isoformat(),
        "competing_candidates_count": normalized.competing_candidates_count,
        "searched_queries": normalized.searched_queries,
        "evidence_json": normalized.evidence_json,
        "artifact_row": normalized.to_artifact_row(include_review_columns=True),
    }


def _candidate_for(
    *,
    product: AgentProduct,
    source_name: str,
    evidence: PageEvidence,
    score: CandidateScore,
    status: str,
    competing_candidates_count: int = 0,
) -> SourceUrlAgentCandidate:
    source = load_source_registry().get(source_name)
    return candidate_from_evidence(
        run_id="snapshot-run",
        product=product,
        source=source,
        evidence=evidence,
        score=score,
        expected_listing="listed",
        competing_candidates_count=competing_candidates_count,
        searched_queries=[f"{product.manufacturer} {product.mpn}"],
        status=status,
    )


def test_source_url_agent_evidence_snapshots(fixtures_root: Path) -> None:
    product = _product()
    registry = load_source_registry()

    valid = _valid_evidence(product)
    bestprice = registry.get("bestprice")
    review_canonical = extract_page_evidence(
        product=product,
        source=bestprice,
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
    electronet = registry.get("electronet")
    review_title_markers = {
        title: extract_page_evidence(
            product=product,
            source=electronet,
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
        ).to_json()
        for title in ("LG MR25GB Review", "Αξιολόγησε LG MR25GB", "Αξιολογήστε LG MR25GB")
    }
    marketplace_body_only = extract_page_evidence(
        product=product,
        source=bestprice,
        requested_url="https://www.bestprice.gr/item/999/jbl-partybox.html",
        final_url="https://www.bestprice.gr/item/999/jbl-partybox.html",
        html_text="""
        <html>
          <head>
            <title>JBL Partybox Encore 2 | BestPrice.gr</title>
            <link rel="canonical" href="https://www.bestprice.gr/item/999/jbl-partybox.html" />
          </head>
          <body>Related searches LG MR25GB Magic Remote</body>
        </html>
        """,
    )
    cloudflare_html = """
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
    cloudflare = extract_page_evidence(
        product=product,
        source=registry.get("skroutz"),
        requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        html_text=cloudflare_html,
    )

    payload = {
        "valid_product_exact_mpn_brand": valid.to_json(),
        "review_canonical_rejected": review_canonical.to_json(),
        "review_title_markers_rejected": review_title_markers,
        "marketplace_body_only_mpn": marketplace_body_only.to_json(),
        "cloudflare_analytics_script": {
            "blocked_detector": _blocked_or_captcha(
                "LG MR25GB Magic Remote Control | Skroutz.gr",
                "LG MR25GB Magic Remote Control",
                cloudflare_html,
            ),
            "evidence": cloudflare.to_json(),
        },
    }

    _assert_snapshot(fixtures_root, ("source_url_agent", "evidence", "evidence.expected.json"), payload)


def test_source_url_agent_scoring_snapshots(fixtures_root: Path) -> None:
    registry = load_source_registry()
    product = _product()
    skroutz = registry.get("skroutz")
    electronet = registry.get("electronet")
    bestprice = registry.get("bestprice")

    valid = _valid_evidence(product)
    exact_at_threshold_product = _product(price=Decimal("10.00"))
    exact_at_threshold = extract_page_evidence(
        product=exact_at_threshold_product,
        source=skroutz,
        requested_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        final_url="https://www.skroutz.gr/s/123/LG-MR25GB.html",
        html_text=_html(),
    )
    without_brand_product = _product(manufacturer="Sony")
    without_brand = extract_page_evidence(
        product=without_brand_product,
        source=electronet,
        requested_url="https://www.electronet.gr/product/lg-magic-remote",
        final_url="https://www.electronet.gr/product/lg-magic-remote",
        html_text=_html(),
    )
    title_only_product = _product(mpn="XYZ-999", name="LG Magic Remote Control")
    title_only = extract_page_evidence(
        product=title_only_product,
        source=electronet,
        requested_url="https://www.electronet.gr/product/lg-magic-remote",
        final_url="https://www.electronet.gr/product/lg-magic-remote",
        html_text=_html(include_mpn=False, title="LG Magic Remote Control"),
    )
    body_only = extract_page_evidence(
        product=product,
        source=bestprice,
        requested_url="https://www.bestprice.gr/item/999/jbl-partybox.html",
        final_url="https://www.bestprice.gr/item/999/jbl-partybox.html",
        html_text="""
        <html>
          <head>
            <title>JBL Partybox Encore 2 | BestPrice.gr</title>
            <link rel="canonical" href="https://www.bestprice.gr/item/999/jbl-partybox.html" />
          </head>
          <body>Related searches LG MR25GB Magic Remote</body>
        </html>
        """,
    )
    blocked_valid = error_evidence(
        product=product,
        requested_url="https://www.skroutz.gr/s/49743700/Bosch-HBG7241B1-Fournos-ano-Pagou-71lt-P59-4ek-Mayros.html",
        final_url="https://www.skroutz.gr/s/49743700/Bosch-HBG7241B1-Fournos-ano-Pagou-71lt-P59-4ek-Mayros.html",
        error_code="blocked_or_captcha",
        error_message="Blocked page or CAPTCHA marker detected.",
    )
    blocked_non_product = error_evidence(
        product=product,
        requested_url="https://www.skroutz.gr/search?keyphrase=LG+MR25GB",
        final_url="https://www.skroutz.gr/search?keyphrase=LG+MR25GB",
        error_code="blocked_or_captcha",
        error_message="Blocked page or CAPTCHA marker detected.",
    )

    payload = {
        "high_confidence_exact_mpn_brand": _score_payload(score_candidate(product=product, source=skroutz, evidence=valid)),
        "exact_mpn_brand_at_threshold_needs_review": _score_payload(
            score_candidate(product=exact_at_threshold_product, source=skroutz, evidence=exact_at_threshold)
        ),
        "exact_mpn_without_brand_needs_review": _score_payload(
            score_candidate(product=without_brand_product, source=electronet, evidence=without_brand)
        ),
        "title_only_forced_needs_review": _score_payload(
            score_candidate(product=title_only_product, source=electronet, evidence=title_only)
        ),
        "multiple_plausible_candidates_needs_review": _score_payload(
            score_candidate(product=product, source=skroutz, evidence=valid, competing_candidates_count=2)
        ),
        "marketplace_body_only_mpn_not_high_confidence": _score_payload(
            score_candidate(product=product, source=bestprice, evidence=body_only)
        ),
        "blocked_valid_product_url_kept_for_review": _score_payload(
            score_candidate(product=product, source=skroutz, evidence=blocked_valid)
        ),
        "blocked_non_product_url_remains_error": _score_payload(
            score_candidate(product=product, source=skroutz, evidence=blocked_non_product)
        ),
    }

    _assert_snapshot(fixtures_root, ("source_url_agent", "scoring", "scoring.expected.json"), payload)


def test_source_url_agent_candidate_shape_snapshots(fixtures_root: Path) -> None:
    registry = load_source_registry()
    product = _product()
    source = registry.get("skroutz")
    valid = _valid_evidence(product)
    high_score = score_candidate(product=product, source=source, evidence=valid)

    review_product = _product(manufacturer="Sony")
    review_source = registry.get("electronet")
    review_evidence = extract_page_evidence(
        product=review_product,
        source=review_source,
        requested_url="https://www.electronet.gr/product/lg-magic-remote",
        final_url="https://www.electronet.gr/product/lg-magic-remote",
        html_text=_html(),
    )
    review_score = score_candidate(product=review_product, source=review_source, evidence=review_evidence)

    error_evidence_item = error_evidence(
        product=product,
        requested_url="https://www.skroutz.gr/search?keyphrase=LG+MR25GB",
        final_url="https://www.skroutz.gr/search?keyphrase=LG+MR25GB",
        error_code="blocked_or_captcha",
        error_message="Blocked page or CAPTCHA marker detected.",
    )
    error_score = score_candidate(product=product, source=source, evidence=error_evidence_item)

    payload = {
        "high_confidence_match": _candidate_payload(
            _candidate_for(product=product, source_name="skroutz", evidence=valid, score=high_score, status="pending")
        ),
        "needs_review": _candidate_payload(
            _candidate_for(
                product=review_product,
                source_name="electronet",
                evidence=review_evidence,
                score=review_score,
                status="needs_review",
            )
        ),
        "error": _candidate_payload(
            _candidate_for(product=product, source_name="skroutz", evidence=error_evidence_item, score=error_score, status="error")
        ),
    }

    _assert_snapshot(fixtures_root, ("source_url_agent", "candidates", "candidates.expected.json"), payload)


def test_source_url_agent_registry_url_shape_snapshot(fixtures_root: Path) -> None:
    registry = load_source_registry()
    cases = {
        "skroutz": {
            "valid_product_url": "https://www.skroutz.gr/s/49743700/Bosch-HBG7241B1-Fournos-ano-Pagou-71lt-P59-4ek-Mayros.html",
            "invalid_listing_url": "https://www.skroutz.gr/c/1607/fournoi.html",
        },
        "bestprice": {
            "valid_product_url": "https://www.bestprice.gr/item/2160770054/tesla-43e655bus-smart-tileorasi-43-4k-uhd-dled-hdr.html",
            "invalid_listing_url": "https://www.bestprice.gr/category/999/tileoraseis.html",
        },
        "electronet": {
            "valid_product_url": "https://www.electronet.gr/oikiakes-syskeyes/psygeia-katapsyktes/psygeiokatapsyktes/psygeiokatapsyktis-lg-gbbsj20dep-anthraki-d",
            "invalid_listing_url": "https://www.electronet.gr/oikiakes-syskeyes/psygeia-katapsyktes",
        },
        "kotsovolos": {
            "valid_product_url": "https://www.kotsovolos.gr/household-appliances/fridges/fridge-freezers/328817-lg-gbbsj20epy",
            "invalid_listing_url": "https://www.kotsovolos.gr/household-appliances/fridges/fridge-freezers",
        },
        "public": {
            "valid_product_url": "https://www.public.gr/product/oikiakes-syskeyes/psygeia/psygeiokatapsiktes/lg-gbb566pzhmn-total-no-frost-462-lt-asimi-psugeiokatapsuktis/1557191",
            "invalid_listing_url": "https://www.public.gr/oikiakes-syskeyes/psygeia/psygeiokatapsiktes/lg-gbb566pzhmn",
        },
        "plaisio": {
            "valid_product_url": "https://www.plaisio.gr/product/mikres-oikiakes-siskeves/kathariotita/skoupes-sfouggaristres/rowenta-skoupa-sfouggaristra-x-clean-4-wet-and-dry-gz5035wo_4756177",
            "invalid_listing_url": "https://www.plaisio.gr/mikres-oikiakes-siskeves/kathariotita/skoupes-sfouggaristres/rowenta-skoupa-sfouggaristra-x-clean-4-wet-and-dry-gz5035wo_4756177",
        },
    }
    payload = {
        source_name: {
            "source_type": registry.get(source_name).source_type,
            "source_domain": registry.get(source_name).source_domain,
            "valid_product_url_accepted": registry.get(source_name).is_product_url(urls["valid_product_url"]),
            "invalid_listing_url_rejected": not registry.get(source_name).is_product_url(urls["invalid_listing_url"]),
        }
        for source_name, urls in cases.items()
    }

    _assert_snapshot(fixtures_root, ("source_url_agent", "registry", "url_shapes.expected.json"), payload)


def test_source_url_agent_search_query_and_normalization_snapshot(fixtures_root: Path) -> None:
    product = _product(name="Long catalog title should not be part of source discovery query")
    source = load_source_registry().get("skroutz")
    payload = {
        "search_queries": generate_search_queries(product, source),
        "normalized_url": normalize_source_url("HTTPS://WWW.Skroutz.GR/s/123?utm_source=x&sku=abc#reviews"),
        "normalization_keeps_meaningful_query": normalize_source_url(
            "https://www.bestprice.gr/item/1/lg.html?sku=abc&utm_campaign=drop&variant=black#reviews"
        ),
    }

    _assert_snapshot(fixtures_root, ("source_url_agent", "search_queries", "search_queries.expected.json"), payload)
