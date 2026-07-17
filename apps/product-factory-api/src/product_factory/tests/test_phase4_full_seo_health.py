from __future__ import annotations

import json
from pathlib import Path

from product_factory.seo_health import (
    CHECK_WEIGHTS,
    FULL_PROFILE_CHECK_WEIGHTS,
    evaluate_seo_health,
    validate_seo_health_contract,
)


EXPECTED_FULL_PROFILE = (
    ("identity.completeness", 1, 8),
    ("identity.series_and_models", 1, 6),
    ("identity.capabilities_consistent", 1, 4),
    ("meta_title.quality", 1, 8),
    ("meta_description.quality", 1, 8),
    ("seo_keyword.valid_and_stable", 1, 8),
    ("contract.deterministic_ownership", 1, 3),
    ("images.gallery_filename_policy", 2, 5),
    ("images.path_sequence_and_format", 2, 4),
    ("images.alt_quality", 2, 4),
    ("content.heading_structure", 2, 2),
    ("internal_linking.related_and_category", 2, 3),
    ("content.catalog_uniqueness", 2, 2),
    ("identifiers.validity_and_provenance", 3, 5),
    ("structured_data.product_completeness", 3, 5),
    ("structured_data.offer_consistency", 3, 5),
    ("merchant.validation", 3, 5),
    ("rollout.migration_safety", 4, 5),
    ("rollout.redirect_and_canonical_coverage", 4, 4),
    ("rollout.production_validation", 4, 3),
    ("rollout.monitoring_and_rollback", 4, 3),
)


def _inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    row: dict[str, object] = {
        "model": "123456",
        "mpn": "ABC",
        "name": "Midea ABC Προϊόν",
        "description": "<p>Μια διακριτή περιγραφή προϊόντος.</p>",
        "meta_title": "Midea ABC Προϊόν | eTranoulis",
        "meta_description": "Midea ABC προϊόν με αξιόπιστη και ολοκληρωμένη περιγραφή.",
        "seo_keyword": "midea-abc-proion",
        "product_url": "https://www.etranoulis.gr/midea-abc-proion",
        "image": "catalog/01_main/123456/midea-abc-proion-1.jpg",
        "additional_image": "",
        "manufacturer": "Midea",
        "category": "Προϊόντα",
        "price": "100",
        "quantity": "1",
        "status": "1",
    }
    identity = {
        "internal_model": "123456",
        "brand": "Midea",
        "mpn": "ABC",
        "mpn_status": "verified",
        "mpn_scope": "single_unit",
        "primary_model": "ABC",
        "set_model": "",
        "component_models": [],
        "commercial_series": "",
        "family_key": "generic",
        "source": "manufacturer",
        "warnings": [],
    }
    deterministic = {
        "brand": "Midea",
        "mpn": "ABC",
        "category_phrase": "Προϊόν",
        "seo_keyword_candidate": "midea-abc-proion",
        "published_seo_keyword": "",
        "seo_identity": {"primary_model": "ABC"},
        "product_identity": identity,
    }
    phase2 = {
        "image_assets": [
            {
                "position": 1,
                "role": "main",
                "filename_candidate": "midea-abc-proion-1.jpg",
                "public_path": "catalog/01_main/123456/midea-abc-proion-1.jpg",
                "jpeg_valid": True,
                "alt": "Midea ABC Προϊόν",
            }
        ],
        "sections": [{"image_alt_confidence": "high"}],
        "description_heading": "Χαρακτηριστικά Midea ABC",
        "internal_links": {
            "canonical_category": "/proionta",
            "related_products": ["123457"],
        },
        "catalog_available": True,
        "catalog_similarity": {
            "intro": {"score": 0.1},
            "meta_description": {"score": 0.1},
        },
    }
    structured_data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": row["name"],
        "description": "Μια διακριτή περιγραφή προϊόντος.",
        "sku": row["model"],
        "mpn": row["mpn"],
        "brand": {"@type": "Brand", "name": "Midea"},
        "image": ["https://www.etranoulis.gr/image/catalog/01_main/123456/midea-abc-proion-1.jpg"],
        "category": row["category"],
        "url": row["product_url"],
        "offers": {
            "@type": "Offer",
            "priceCurrency": "EUR",
            "price": "100",
            "availability": "https://schema.org/InStock",
            "url": row["product_url"],
        },
    }
    feed = {
        "id": row["model"],
        "title": row["name"],
        "description": row["meta_description"],
        "link": row["product_url"],
        "image_link": structured_data["image"][0],
        "additional_image_links": [],
        "brand": "Midea",
        "mpn": "ABC",
        "identifier_mode": "mpn_only",
        "condition": "new",
        "product_type": row["category"],
        "price": {"value": "100", "currency": "EUR"},
        "availability": "in_stock",
        "source_provenance": {
            "mpn": "manufacturer",
            "price": "snapshot",
            "availability": "snapshot",
        },
    }
    phase3 = {
        "identity": identity,
        "structured_data_enabled": True,
        "product_feed_enabled": True,
        "structured_data": structured_data,
        "feed": feed,
        "errors": [],
    }
    return row, deterministic, phase2, phase3


def _passing_phase4() -> dict[str, object]:
    return {
        check_id: {
            "status": "pass",
            "blocks_publish": False,
            "message": "verified",
            "observed": True,
            "expected": True,
            "subchecks": [
                {
                    "id": f"{check_id}.verified",
                    "status": "pass",
                    "message": "verified",
                    "observed": True,
                    "expected": True,
                }
            ],
        }
        for check_id, phase, _ in EXPECTED_FULL_PROFILE
        if phase == 4
    }


def test_full_profile_has_exact_grouped_weights_and_preserves_phase1_contract() -> None:
    row, deterministic, phase2, phase3 = _inputs()

    phase1 = evaluate_seo_health(
        model="123456", row=row, deterministic_product=deterministic
    )
    assert len(phase1["checks"]) == len(CHECK_WEIGHTS) == 29
    assert {check["id"]: check["weight"] for check in phase1["checks"]} == {
        check_id: weight for check_id, _, weight in CHECK_WEIGHTS
    }

    full = evaluate_seo_health(
        model="123456",
        row=row,
        deterministic_product=deterministic,
        profile="full",
        phase2=phase2,
        phase3=phase3,
        phase4=_passing_phase4(),
    )
    observed = tuple(
        (check["id"], check["phase"], check["weight"])
        for check in full["checks"]
    )
    assert FULL_PROFILE_CHECK_WEIGHTS == EXPECTED_FULL_PROFILE
    assert observed == EXPECTED_FULL_PROFILE
    assert len(full["checks"]) == 21
    assert sum(check["weight"] for check in full["checks"]) == 100
    assert {
        phase: sum(check["weight"] for check in full["checks"] if check["phase"] == phase)
        for phase in (1, 2, 3, 4)
    } == {1: 45, 2: 20, 3: 20, 4: 15}
    assert full["coverage"]["percentage"] == 100
    assert validate_seo_health_contract(full) == []


def test_full_profile_surfaces_each_attention_subcheck_and_not_run_lowers_coverage() -> None:
    row, deterministic, phase2, phase3 = _inputs()
    phase4 = _passing_phase4()
    phase4["rollout.migration_safety"] = {
        "status": "fail",
        "blocks_publish": True,
        "message": "migration preconditions failed",
        "subchecks": [
            {
                "id": "snapshot.hash_matches",
                "status": "fail",
                "blocks_publish": True,
                "message": "snapshot is stale",
                "observed": "old",
                "expected": "current",
            },
            {
                "id": "approval.scope_complete",
                "status": "warn",
                "message": "one optional field was not reviewed",
                "observed": False,
                "expected": True,
            },
            {"id": "rollback.available", "status": "pass"},
        ],
    }
    phase4["rollout.production_validation"] = {
        "status": "not_run",
        "blocks_publish": False,
        "message": "live access is unavailable",
        "subchecks": [
            {
                "id": "live.http_success",
                "status": "not_run",
                "message": "live access is unavailable",
                "observed": None,
                "expected": 200,
            }
        ],
    }

    report = evaluate_seo_health(
        model="123456",
        row=row,
        deterministic_product=deterministic,
        profile="full",
        phase2=phase2,
        phase3=phase3,
        phase4=phase4,
    )
    checks = {check["id"]: check for check in report["checks"]}
    migration = checks["rollout.migration_safety"]
    production = checks["rollout.production_validation"]

    assert migration["status"] == "fail"
    assert migration["blocks_publish"] is True
    assert {item["field"] for item in migration["evidence"]} == {
        "snapshot.hash_matches",
        "approval.scope_complete",
    }
    assert all(item["source"] == "runtime" for item in migration["evidence"])
    assert production["status"] == "not_run"
    assert [item["field"] for item in production["evidence"]] == [
        "live.http_success"
    ]
    assert report["coverage"] == {
        "active_weight": 100.0,
        "evaluated_weight": 97.0,
        "percentage": 97,
    }
    assert report["publish_gate"]["enforcement_mode"] == "blockers_only"
    assert report["publish_gate"]["enforced_allowed"] is False
    assert validate_seo_health_contract(report) == []


def test_missing_phase4_groups_are_not_run_and_schema_accepts_phase_four() -> None:
    row, deterministic, phase2, phase3 = _inputs()
    report = evaluate_seo_health(
        model="123456",
        row=row,
        deterministic_product=deterministic,
        profile="full",
        phase2=phase2,
        phase3=phase3,
    )
    rollout = [check for check in report["checks"] if check["phase"] == 4]

    assert len(rollout) == 4
    assert all(check["status"] == "not_run" for check in rollout)
    assert report["coverage"]["percentage"] == 85
    assert report["publish_gate"]["enforcement_mode"] == "blockers_only"
    assert report["publish_gate"]["enforced_allowed"] is True

    schema_path = Path(__file__).parents[3] / "docs" / "contracts" / "seo_health.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["$defs"]["check"]["properties"]["phase"]["enum"] == [1, 2, 3, 4]
    assert validate_seo_health_contract(report) == []


def test_empty_phase2_placeholders_are_not_counted_as_evaluated_evidence() -> None:
    row, deterministic, _phase2, phase3 = _inputs()
    report = evaluate_seo_health(
        model="123456",
        row=row,
        deterministic_product=deterministic,
        profile="full",
        phase2={
            "image_assets": [],
            "sections": [],
            "internal_links": {},
            "catalog_similarity": {},
            "description_heading": "",
            "catalog_available": False,
        },
        phase3=phase3,
        phase4=_passing_phase4(),
    )

    phase2_checks = [check for check in report["checks"] if check["phase"] == 2]
    assert phase2_checks
    assert {check["status"] for check in phase2_checks} == {"not_run"}
    assert report["coverage"]["percentage"] == 80
