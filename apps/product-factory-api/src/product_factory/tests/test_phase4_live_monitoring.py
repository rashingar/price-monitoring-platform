from __future__ import annotations

import json
from pathlib import Path

from product_factory.seo_migration.cli import (
    _expected_after,
    _live_result_for_model,
    _structured_artifacts,
    _with_reviewed_live_expectations,
)
from product_factory.seo_migration.live_validation import (
    LIVE_CHECKS,
    validate_live_product,
)
from product_factory.seo_migration.monitoring import (
    FINDING_ORDER,
    build_monitoring_report,
)


PRODUCT_URL = "https://store.example.test/air-conditioner/model-x"


def _successful_html() -> str:
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Brand Model X Air Conditioner",
        "image": [
            "https://store.example.test/image/model-x-1.jpg",
            "https://store.example.test/image/model-x-2.jpg",
        ],
        "mpn": "MODEL-X",
        "gtin13": "5201234567890",
        "offers": {
            "@type": "Offer",
            "price": "799.00",
            "priceCurrency": "EUR",
            "availability": "https://schema.org/InStock",
        },
    }
    return f"""
    <html>
      <head>
        <title>Brand Model X Air Conditioner | eTranoulis</title>
        <meta name="description" content="Efficient Brand Model X air conditioner." />
        <link rel="canonical" href="{PRODUCT_URL}" />
        <script type="application/ld+json">{json.dumps(product)}</script>
      </head>
      <body>
        <div hidden><h1>Hidden heading</h1></div>
        <main>
          <h1>Brand Model X Air Conditioner</h1>
          <section><h2>Comfort with Model X</h2></section>
          <div class="product-gallery">
            <img src="/image/model-x-1.jpg" />
            <img src="/image/model-x-2.jpg" />
          </div>
          <div id="tab-description">
            <img src="/image/model-x-description.jpg" />
          </div>
          <a href="/air-conditioners">Air conditioners</a>
          <a href="https://other.example.test/outside">External</a>
        </main>
      </body>
    </html>
    """


def _expected_live_state() -> dict:
    return {
        "product_url": PRODUCT_URL,
        "meta_title": "Brand Model X Air Conditioner | eTranoulis",
        "meta_description": "Efficient Brand Model X air conditioner.",
        "name": "Brand Model X Air Conditioner",
        "description_heading": "Comfort with Model X",
        "description": '<img src="/image/model-x-description.jpg">',
        "image": "https://store.example.test/image/model-x-1.jpg",
        "additional_image": "https://store.example.test/image/model-x-2.jpg",
        "price": "799",
        "availability": "InStock",
        "mpn": "MODEL-X",
        "ean": "5201234567890",
        "internal_links": ["/air-conditioners"],
    }


def _find(report: dict, finding_id: str) -> dict:
    return next(item for item in report["findings"] if item["id"] == finding_id)


def test_live_validation_without_configured_url_marks_every_check_not_run() -> None:
    called = False

    def fetcher(_url: str, _timeout: float) -> dict:
        nonlocal called
        called = True
        raise AssertionError("fetcher must not run without a configured URL")

    report = validate_live_product({}, fetcher=fetcher)

    assert called is False
    assert report["status"] == "not_run"
    assert [item["id"] for item in report["checks"]] == [
        check_id for check_id, _ in LIVE_CHECKS
    ]
    assert {item["status"] for item in report["checks"]} == {"not_run"}
    assert report["coverage"] == {
        "total_checks": len(LIVE_CHECKS),
        "evaluated_checks": 0,
        "percentage": 0,
    }
    assert report["summary"]["not_run"] == len(LIVE_CHECKS)
    assert len(report["manual_validation_checklist"]) == len(LIVE_CHECKS)
    assert report["access"]["anti_bot_bypass_attempted"] is False
    assert report["access"]["googlebot_blocking_inferred"] is False


def test_live_validation_uses_mapping_fetcher_and_checks_complete_page() -> None:
    requested: list[tuple[str, float]] = []

    def fetcher(url: str, timeout: float) -> dict:
        requested.append((url, timeout))
        return {
            "status_code": 200,
            "requested_url": url,
            "final_url": PRODUCT_URL,
            "text": _successful_html(),
        }

    report = validate_live_product(
        _expected_live_state(),
        model="123456",
        fetcher=fetcher,
        timeout_seconds=500,
    )

    assert requested == [(PRODUCT_URL, 30.0)]
    assert report["model"] == "123456"
    assert report["status"] == "pass"
    assert report["access"]["status"] == "completed"
    assert report["coverage"]["percentage"] == 100
    assert report["summary"] == {
        "passed": len(LIVE_CHECKS),
        "warnings": 0,
        "failed": 0,
        "not_applicable": 0,
        "not_run": 0,
    }
    assert all(check["status"] == "pass" for check in report["checks"])
    assert report["access"]["authentication_attempted"] is False
    assert report["access"]["anti_bot_bypass_attempted"] is False


def test_live_validation_accepts_snapshot_additional_image_lists() -> None:
    expected = _expected_live_state()
    expected.pop("additional_image")
    expected["additional_images"] = [
        "https://store.example.test/image/model-x-2.jpg"
    ]

    report = validate_live_product(
        expected,
        model="123456",
        fetcher=lambda url, _timeout: {
            "status_code": 200,
            "requested_url": url,
            "final_url": PRODUCT_URL,
            "text": _successful_html(),
        },
    )

    gallery = next(
        check for check in report["checks"] if check["id"] == "live.gallery_order"
    )
    assert gallery["status"] == "pass"


def test_live_validation_request_failure_is_not_run_without_crawler_inference() -> None:
    def unavailable(_url: str, _timeout: float) -> dict:
        raise TimeoutError("private target detail must not be copied")

    report = validate_live_product(
        {"product_url": PRODUCT_URL}, fetcher=unavailable
    )

    assert {check["status"] for check in report["checks"]} == {"not_run"}
    assert report["coverage"]["percentage"] == 0
    assert report["access"]["status"] == "unavailable"
    assert report["access"]["error_code"] == "live_access_unavailable"
    assert report["access"]["error_type"] == "TimeoutError"
    assert report["access"]["googlebot_blocking_inferred"] is False
    assert "private target detail" not in json.dumps(report)


def test_live_validation_http_failure_evaluates_only_http_check() -> None:
    report = validate_live_product(
        {"product_url": PRODUCT_URL},
        fetcher=lambda url, _timeout: {
            "status_code": 503,
            "requested_url": url,
            "final_url": url,
            "text": "unavailable",
        },
    )

    assert report["checks"][0]["status"] == "fail"
    assert all(check["status"] == "not_run" for check in report["checks"][1:])
    assert report["coverage"]["evaluated_checks"] == 1
    assert report["coverage"]["percentage"] == 7


def test_monitoring_report_is_deterministic_and_covers_required_regressions() -> None:
    payload = {
        "migration_run_id": "migration-001",
        "model": "123456",
        "applied": True,
        "before": {
            "model": "123456",
            "seo_keyword": "locked-old-slug",
            "product_url": "https://store.example.test/locked-old-slug",
            "image": "catalog/01_main/123456/legacy-1.jpg",
            "additional_image": "catalog/01_main/123456/legacy-2.jpg",
        },
        "after": {
            "model": "123456",
            "seo_keyword": "unexpected-new-slug",
            "product_url": "https://store.example.test/unexpected-new-slug",
            "image": "catalog/01_main/123456/new-1.jpg",
            "additional_image": "catalog/01_main/123456/new-2.jpg",
            "mpn": "",
            "price": "100.00",
            "availability": "InStock",
        },
        "expected_after": {
            "seo_keyword": "locked-old-slug",
            "product_url": "https://store.example.test/locked-old-slug",
            "image": "catalog/01_main/123456/legacy-1.jpg",
            "additional_image": "catalog/01_main/123456/legacy-2.jpg",
        },
        "approval": {
            "approved_slug_change": False,
            "approved_image_path_change": False,
        },
        "baseline_seo_health": {"score": 90},
        "seo_health": {
            "score": 70,
            "summary": {"blocking_failures": 1},
            "checks": [
                {
                    "id": "seo_keyword.valid_and_stable",
                    "status": "fail",
                    "blocks_publish": True,
                }
            ],
        },
        "structured_data": {
            "@type": "Product",
            "offers": {"price": "99.00", "availability": "OutOfStock"},
        },
        "structured_artifacts": {
            "product_structured_data": {"available": False}
        },
        "baseline_metrics": {"duplicate_content_count": 1},
        "metrics": {"duplicate_content_count": 3},
        "live_validation": {
            "coverage": {"percentage": 100},
            "checks": [
                {"id": "live.canonical_url", "status": "fail"},
                {"id": "live.title", "status": "pass"},
            ],
        },
        "rollback_manifest": {},
    }

    first = build_monitoring_report(payload)
    second = build_monitoring_report(payload)

    assert first == second
    assert [finding["id"] for finding in first["findings"]] == list(FINDING_ORDER)
    assert first["status"] == "fail"
    assert first["summary"]["blocking_findings"] == 4
    assert _find(first, "seo_health.blocking_failures")["status"] == "fail"
    assert _find(first, "seo_health.score_regression")["status"] == "warn"
    assert _find(first, "rollout.unexpected_slug_change")["blocking"] is True
    assert _find(first, "rollout.image_path_regression")["blocking"] is True
    assert _find(first, "identifiers.missing")["evidence"] == ["mpn_missing"]
    assert _find(first, "structured_data.price_schema_mismatch")["status"] == "fail"
    assert _find(first, "structured_data.artifact_availability")["status"] == "fail"
    assert _find(first, "content.duplicate_increase")["status"] == "warn"
    assert _find(first, "rollout.live_validation")["evidence"] == [
        "live.canonical_url"
    ]
    assert _find(first, "rollout.rollback_availability")["blocking"] is True


def test_monitoring_keeps_missing_gtin_report_only_for_mpn_only_contract() -> None:
    live = {
        "coverage": {"percentage": 100},
        "checks": [{"id": check_id, "status": "pass"} for check_id, _ in LIVE_CHECKS],
    }
    payload = {
        "dry_run": True,
        "before": {
            "seo_keyword": "stable-slug",
            "product_url": PRODUCT_URL,
            "image": "catalog/01_main/123456/stable-1.jpg",
            "duplicate_content_count": 1,
        },
        "after": {
            "model": "123456",
            "seo_keyword": "stable-slug",
            "product_url": PRODUCT_URL,
            "image": "catalog/01_main/123456/stable-1.jpg",
            "mpn": "MODEL-X",
            "price": "799",
            "availability": "InStock",
            "duplicate_content_count": 1,
        },
        "baseline_seo_health": {"score": 85, "checks": []},
        "seo_health": {
            "score": 88,
            "summary": {"blocking_failures": 0},
            "checks": [],
        },
        "structured_data": {
            "@type": "Product",
            "offers": {
                "price": "799.00",
                "availability": "https://schema.org/InStock",
            },
        },
        "structured_artifacts": {
            "product_structured_data": {"available": True}
        },
        "baseline_metrics": {"duplicate_content_count": 1},
        "metrics": {"duplicate_content_count": 1},
        "live_validation": live,
    }

    report = build_monitoring_report(payload)
    identifiers = _find(report, "identifiers.missing")

    assert identifiers["status"] == "warn"
    assert identifiers["blocking"] is False
    assert identifiers["evidence"] == [
        "gtin_missing_report_only",
        "identifier_contract:mpn_only",
    ]
    assert _find(report, "structured_data.price_schema_mismatch")["status"] == "pass"
    assert _find(report, "rollout.rollback_availability")["status"] == "not_applicable"
    assert report["status"] == "warn"


def test_local_structured_artifact_does_not_prove_production_availability(
    tmp_path: Path,
) -> None:
    model = "123456"
    artifact_dir = tmp_path / "apply" / "artifacts" / model
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "structured_data_manifest.json").write_text(
        json.dumps({"@type": "Product", "offers": {"price": "799"}}),
        encoding="utf-8",
    )
    product_plan = {
        "fields": [
            {
                "field": "structured_data_manifest",
                "candidate_value": {
                    "@type": "Product",
                    "offers": {"price": "799"},
                },
            }
        ]
    }

    artifacts = _structured_artifacts(
        tmp_path,
        model,
        product_plan=product_plan,
        live_validation={
            "checks": [
                {
                    "id": "live.product_structured_data",
                    "status": "not_run",
                    "observed": None,
                }
            ]
        },
    )
    report = build_monitoring_report(
        {
            "after": {"model": model, "mpn": "MODEL-X", "price": "799"},
            "structured_artifacts": artifacts,
        }
    )

    assert artifacts["candidate"]["available"] is True
    assert artifacts["staged"]["available"] is True
    assert artifacts["production"]["status"] == "not_run"
    assert _find(report, "structured_data.artifact_availability")["status"] == "not_run"
    assert _find(report, "structured_data.price_schema_mismatch")["status"] == "not_run"


def test_monitoring_uses_live_jsonld_observations_for_offer_validation(
    tmp_path: Path,
) -> None:
    model = "123456"
    artifacts = _structured_artifacts(
        tmp_path,
        model,
        product_plan={"fields": []},
        live_validation={
            "checks": [
                {
                    "id": "live.product_structured_data",
                    "status": "pass",
                    "observed": True,
                },
                {"id": "live.offer_price", "status": "pass", "observed": "799.00"},
                {
                    "id": "live.availability",
                    "status": "pass",
                    "observed": "InStock",
                },
            ]
        },
    )
    report = build_monitoring_report(
        {
            "after": {
                "model": model,
                "mpn": "MODEL-X",
                "price": "799",
                "availability": "InStock",
            },
            "structured_artifacts": artifacts,
        }
    )

    assert artifacts["staged"]["available"] is False
    assert artifacts["production"]["source"] == "live_jsonld_validation"
    assert _find(report, "structured_data.artifact_availability")["status"] == "pass"
    assert _find(report, "structured_data.price_schema_mismatch")["status"] == "pass"


def test_expected_image_description_uses_apply_effective_rollback_value() -> None:
    expected = _expected_after(
        {"description": "legacy description"},
        {
            "fields": [
                {
                    "field": "gallery_image_candidate",
                    "candidate_value": [
                        {"candidate_path": "catalog/01_main/123456/new-1.jpg"}
                    ],
                }
            ]
        },
        {"approved_fields": [], "approved_image_path_change": True},
        rollback_manifest={
            "operations": [
                {
                    "model": "123456",
                    "field": "gallery_image_candidate",
                    "effective_expected_applied_description": (
                        "approved description with catalog/01_main/123456/new-1.jpg"
                    ),
                }
            ]
        },
        model="123456",
    )

    assert expected["description"] == (
        "approved description with catalog/01_main/123456/new-1.jpg"
    )


def test_protected_price_drift_is_a_blocking_unapproved_change() -> None:
    report = build_monitoring_report(
        {
            "before": {"model": "123456", "price": "799.00"},
            "after": {"model": "123456", "price": "749.00", "mpn": "MODEL-X"},
            "expected_after": {"model": "123456", "price": "799.00"},
        }
    )
    finding = _find(report, "rollout.unapproved_field_change")

    assert finding["status"] == "fail"
    assert finding["blocking"] is True
    assert "protected_field_changed:price" in finding["evidence"]


def test_monitor_prefers_only_a_newer_standalone_live_result(tmp_path: Path) -> None:
    model = "123456"
    standalone_path = tmp_path / "live_validation" / f"{model}.json"
    standalone_path.parent.mkdir(parents=True)
    embedded = {
        "generated_at": "2026-07-12T11:00:00Z",
        "status": "pass",
        "checks": [{"id": "live.http_success", "status": "pass"}],
    }
    apply_result = {
        "products": [{"model": model, "live_validation": embedded}]
    }
    older = {
        "generated_at": "2026-07-12T10:00:00Z",
        "status": "fail",
        "checks": [{"id": "live.http_success", "status": "fail"}],
    }
    standalone_path.write_text(json.dumps(older), encoding="utf-8")

    assert _live_result_for_model(apply_result, model, run_dir=tmp_path) == embedded

    newer = {**older, "generated_at": "2026-07-12T12:00:00Z"}
    standalone_path.write_text(json.dumps(newer), encoding="utf-8")
    assert _live_result_for_model(apply_result, model, run_dir=tmp_path) == newer


def test_reviewed_phase2_links_and_heading_feed_live_expectations() -> None:
    expected = _with_reviewed_live_expectations(
        {"model": "123456", "description": "<p>No heading here</p>"},
        {
            "seo_health_input": {
                "phase2": {
                    "description_heading": "Product highlights",
                    "internal_links": {
                        "canonical_category": "/air-conditioners",
                        "related_products": ["100001"],
                    },
                }
            }
        },
        catalog_products={
            "100001": {
                "canonical_url": "https://store.example.test/related-product"
            }
        },
        approval={"approved_fields": ["description", "related_products"]},
    )

    assert expected["description_heading"] == "Product highlights"
    assert expected["internal_links"]["canonical_category"] == "/air-conditioners"
    assert expected["internal_links"]["related_products"] == [
        "https://store.example.test/related-product"
    ]

    meta_only = _with_reviewed_live_expectations(
        {"model": "123456"},
        {
            "seo_health_input": {
                "phase2": {
                    "description_heading": "Unpublished heading",
                    "internal_links": {"canonical_category": "/unpublished"},
                }
            }
        },
        approval={"approved_fields": ["meta_title"]},
    )
    assert "description_heading" not in meta_only
    assert "internal_links" not in meta_only
