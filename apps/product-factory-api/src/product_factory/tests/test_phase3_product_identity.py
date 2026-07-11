from __future__ import annotations

import json
from pathlib import Path

import pytest

from product_factory.mapping import build_row
from product_factory.models import CLIInput, ParsedProduct, SchemaMatchResult, SourceProductData, TaxonomyResolution
from product_factory.product_identity import (
    normalize_mpn_display,
    normalize_mpn_for_match,
    resolve_product_identity,
    validate_mpn_identity,
)
from product_factory.seo_health import evaluate_seo_health, seo_health_allows_publish


SEO_IDENTITY = {
    "family": "air_conditioner",
    "commercial_series": "Solunar",
    "primary_model": "EF-12RD1H",
    "set_model": "EF-12RD1H/MX1-12RD1H",
    "indoor_model": "EF-12RD1H",
    "outdoor_model": "MX1-12RD1H",
}


def _resolve(**overrides):
    values = {
        "internal_model": "747100",
        "brand": "Midea",
        "source_mpn": "EF-12RD1H/MX1-12RD1H",
        "source_name": "electronet",
        "source_url": "https://example.test/product",
        "source_title": "Midea Solunar EF-12RD1H/MX1-12RD1H air conditioner",
        "family_key": "air_conditioner",
        "seo_identity": SEO_IDENTITY,
    }
    values.update(overrides)
    return resolve_product_identity(**values)


def test_verified_complete_set_preserves_components_and_compact_primary_model() -> None:
    identity = _resolve()

    assert identity.mpn == "EF-12RD1H/MX1-12RD1H"
    assert identity.mpn_status == "verified"
    assert identity.mpn_scope == "complete_set"
    assert identity.primary_model == "EF-12RD1H"
    assert identity.component_models == ["EF-12RD1H", "MX1-12RD1H"]
    assert identity.source == "electronet"


def test_component_candidate_conflict_never_silently_replaces_complete_set() -> None:
    identity = _resolve(
        explicit_candidates=[
            {"value": "EF-12RD1H", "scope": "indoor_unit", "source": "trusted_retailer", "confidence": .82}
        ]
    )

    assert identity.mpn == ""
    assert identity.mpn_status == "conflicting"
    assert identity.conflict_reason == "complete_set_and_component_identifier_conflict"
    assert "mpn_candidates_conflicting" in validate_mpn_identity(identity.to_dict(), csv_mpn="", active=True)


def test_verified_single_unit_and_missing_or_internal_values() -> None:
    single = _resolve(source_mpn="EF-12RD1H", source_title="Midea EF-12RD1H air conditioner", seo_identity={"family": "air_conditioner", "primary_model": "EF-12RD1H"})
    internal = _resolve(source_mpn="747100", source_title="Midea air conditioner")

    assert single.mpn_status == "verified" and single.mpn_scope == "single_unit"
    assert internal.mpn_status == "missing" and "source_mpn_rejected" in internal.warnings


def test_manual_override_is_explicit_and_has_manual_provenance() -> None:
    identity = _resolve(
        source_mpn="",
        source_title="Midea Solunar air conditioner",
        manual_override={"value": "EF-12RD1H/MX1-12RD1H", "scope": "complete_set", "reason": "supplier_invoice"},
    )

    assert identity.mpn_status == "verified"
    assert identity.source == "manual_override"
    assert "manual_override" in identity.warnings


def test_normalization_preserves_slash_sets_and_normalizes_dash_spacing() -> None:
    value = " MPN: EF\u201312RD1H / MX1\u201112RD1H "

    assert normalize_mpn_display(value) == "EF-12RD1H/MX1-12RD1H"
    assert normalize_mpn_for_match(value) == "EF-12RD1H/MX1-12RD1H"


def test_product_identity_schema_validates() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).parents[3] / "docs" / "contracts" / "product_identity.schema.json"

    jsonschema.Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(_resolve().to_dict())


def test_phase3_mapping_changes_only_active_ac_mpn_and_keeps_compact_title() -> None:
    source = SourceProductData(
        source_name="electronet", brand="Midea", mpn="EF-12RD1H/MX1-12RD1H",
        name="Midea Solunar EF-12RD1H/MX1-12RD1H air conditioner 12000 BTU",
    )
    taxonomy = TaxonomyResolution(leaf_category="Air Conditioners", sub_category="Wall")
    row, normalized, _ = build_row(
        CLIInput(model="747100", url="https://example.test/product"),
        ParsedProduct(source=source), taxonomy, SchemaMatchResult(),
        phase3_settings={"enabled": True, "families": ["air_conditioner"], "mpn_allow_manual_override": True, "mpn_overrides": {}},
    )

    identity = normalized["deterministic_product"]["product_identity"]
    assert row["mpn"] == "EF-12RD1H/MX1-12RD1H"
    assert identity["primary_model"] in row["meta_title"]
    assert "EF-12RD1H/MX1-12RD1H" in row["name"]


def test_phase3_disabled_preserves_existing_deterministic_shape() -> None:
    source = SourceProductData(brand="LG", mpn="GSGV80PYLL", name="LG GSGV80PYLL Refrigerator")
    row, normalized, _ = build_row(
        CLIInput(model="747100", url="https://example.test/product"), ParsedProduct(source=source),
        TaxonomyResolution(leaf_category="Refrigerators"), SchemaMatchResult(),
        phase3_settings={"enabled": False},
    )

    assert row["mpn"] == "GSGV80PYLL"
    assert "product_identity" not in normalized["deterministic_product"]


def test_conflicting_mpn_blocks_active_air_conditioner_publish_gate() -> None:
    identity = _resolve(
        explicit_candidates=[{"value": "EF-12RD1H", "scope": "indoor_unit", "source": "trusted_retailer", "confidence": .82}]
    ).to_dict()
    report = evaluate_seo_health(
        model="747100",
        row={
            "mpn": "EF-12RD1H/MX1-12RD1H", "name": "Midea Solunar EF-12RD1H/MX1-12RD1H Air Conditioner",
            "meta_title": "Midea Solunar EF-12RD1H Air Conditioner | eTranoulis", "meta_description": "Midea Solunar air conditioner.", "seo_keyword": "midea-solunar-ef-12rd1h-air-conditioner", "product_url": "https://example.test/product",
        },
        deterministic_product={"brand": "Midea", "mpn": "EF-12RD1H/MX1-12RD1H", "seo_identity": SEO_IDENTITY, "product_identity": identity},
        settings={"phase3": {"enabled": True, "families": ["air_conditioner"], "mpn_require_verified": True}},
        phase3={"enabled": True, "active": True, "identity": identity, "structured_data": {}, "feed": {}, "errors": ["mpn_candidates_conflicting"]},
    )

    conflict_check = next(check for check in report["checks"] if check["id"] == "identity.no_component_set_conflict")
    assert conflict_check["status"] == "fail" and conflict_check["blocks_publish"] is True
    assert seo_health_allows_publish(report) is False
