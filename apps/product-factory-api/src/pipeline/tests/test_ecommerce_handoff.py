from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.models import CLIInput, FetchResult, FieldDiagnostic, ParsedProduct, SchemaMatchResult, SourceProductData, TaxonomyResolution
from pipeline.prepare_result_assembly import PrepareResultAssemblyResult
from pipeline.prepare_stage import execute_prepare_stage
from pipeline.prepare_taxonomy_enrichment import PrepareTaxonomyEnrichmentResult
from pipeline.ecommerce_handoff import build_ecommerce_source_handoff, ecommerce_handoff_path
from pipeline.source_acquisition_models import SourceAcquisitionResult


def _build_cli(tmp_path: Path, *, model: str = "233541", url: str = "https://www.electronet.gr/example") -> CLIInput:
    return CLIInput(
        model=model,
        url=url,
        photos=1,
        sections=0,
        skroutz_status=0,
        boxnow=0,
        price="199",
        out=str(tmp_path / "work" / model / "scrape"),
    )


def _build_parsed(url: str, *, model: str = "233541") -> ParsedProduct:
    return ParsedProduct(
        source=SourceProductData(
            source_name="electronet",
            page_type="product",
            url=url,
            canonical_url=f"{url}?canonical=1",
            product_code=model,
            brand="LG",
            name="LG GSGV80PYLL",
            mpn="GSGV80PYLL",
            price_value=929.9,
            delivery_text="Άμεσα διαθέσιμο",
            taxonomy_source_category="Ψυγειοκαταψύκτες",
        ),
        provenance={"name": "json_ld", "price": "json_ld"},
        field_diagnostics={"price": FieldDiagnostic(confidence=0.98, selected_strategy="json_ld", value_present=True)},
        warnings=["source_product_code_mismatch:input=233541:page=999999"],
        missing_fields=["source.energy_label_asset_url"],
    )


def _build_fetch(url: str) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=f"{url}?ref=final",
        html="<html></html>",
        status_code=200,
        method="httpx",
        fallback_used=False,
        response_headers={"Content-Type": "text/html; charset=utf-8"},
    )


def test_build_ecommerce_source_handoff_has_stable_contract_shape(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pipeline.ecommerce_handoff.utcnow_iso", lambda: "2026-05-05T10:20:30+00:00")
    cli = _build_cli(tmp_path)
    parsed = _build_parsed(cli.url, model=cli.model)
    fetch = _build_fetch(cli.url)

    payload = build_ecommerce_source_handoff(
        cli=cli,
        source="electronet",
        provider_id="electronet",
        fetch=fetch,
        parsed=parsed,
    )

    assert list(payload) == [
        "schema_version",
        "generated_at",
        "model",
        "input_url",
        "source",
        "provider_id",
        "requested_url",
        "final_url",
        "canonical_url",
        "source_name",
        "source_domain",
        "product",
        "evidence",
        "fetch",
        "warnings",
        "missing_fields",
        "critical_missing",
        "artifact_refs",
    ]
    assert payload["schema_version"] == "1.0"
    assert payload["generated_at"] == "2026-05-05T10:20:30+00:00"
    assert payload["model"] == "233541"
    assert payload["source_domain"] == "www.electronet.gr"
    assert payload["product"] == {
        "name": "LG GSGV80PYLL",
        "brand": "LG",
        "manufacturer": "",
        "mpn": "GSGV80PYLL",
        "product_code": "233541",
        "page_type": "product",
        "price": 929.9,
        "currency": "EUR",
        "availability": "Άμεσα διαθέσιμο",
        "stock_status": "",
    }
    assert payload["evidence"]["provenance"] == {"name": "json_ld", "price": "json_ld"}
    assert payload["evidence"]["field_diagnostics"]["price"]["selected_strategy"] == "json_ld"
    assert payload["fetch"] == {
        "method": "httpx",
        "status_code": 200,
        "content_type": "text/html; charset=utf-8",
        "fallback_used": False,
    }
    assert payload["missing_fields"] == [
        "source.energy_label_asset_url",
        "product.manufacturer",
        "product.stock_status",
    ]
    assert payload["artifact_refs"] == {
        "source_json": "work/233541/scrape/233541.source.json",
        "report_json": "work/233541/scrape/233541.report.json",
    }


def test_prepare_stage_writes_ecommerce_handoff_after_success(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pipeline.ecommerce_handoff.utcnow_iso", lambda: "2026-05-05T10:20:30+00:00")
    cli = _build_cli(tmp_path)
    scrape_dir = tmp_path / "work" / cli.model / "scrape"
    parsed = _build_parsed(cli.url, model=cli.model)
    fetch = _build_fetch(cli.url)

    def fake_execute_source_acquisition_stage(**_kwargs):
        return SourceAcquisitionResult(
            model_dir=scrape_dir,
            source="electronet",
            provider_id="electronet",
            fetch=fetch,
            parsed=parsed,
        )

    execute_prepare_stage(
        cli,
        model_dir=scrape_dir,
        execute_source_acquisition_stage_fn=fake_execute_source_acquisition_stage,
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: PrepareTaxonomyEnrichmentResult(
            taxonomy=TaxonomyResolution(),
            taxonomy_candidates=[],
            manufacturer_enrichment={},
        ),
        assemble_prepare_result_fn=lambda **_kwargs: PrepareResultAssemblyResult(
            schema_match=SchemaMatchResult(),
            schema_candidates=[],
            row={},
            normalized={},
            report={"warnings": []},
        ),
    )

    handoff_path = ecommerce_handoff_path(scrape_dir)
    assert handoff_path == ecommerce_handoff_path(scrape_dir)
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["provider_id"] == "electronet"
    assert payload["artifact_refs"]["source_json"] == "work/233541/scrape/233541.source.json"


def test_prepare_stage_writes_failure_handoff_after_partial_acquisition(tmp_path: Path) -> None:
    cli = _build_cli(tmp_path)
    scrape_dir = tmp_path / "work" / cli.model / "scrape"
    parsed = _build_parsed(cli.url, model=cli.model)
    fetch = _build_fetch(cli.url)

    def fake_execute_source_acquisition_stage(**_kwargs):
        return SourceAcquisitionResult(
            model_dir=scrape_dir,
            source="electronet",
            provider_id="electronet",
            fetch=fetch,
            parsed=parsed,
        )

    with pytest.raises(RuntimeError, match="taxonomy exploded"):
        execute_prepare_stage(
            cli,
            model_dir=scrape_dir,
            execute_source_acquisition_stage_fn=fake_execute_source_acquisition_stage,
            resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("taxonomy exploded")),
        )

    handoff_path = ecommerce_handoff_path(scrape_dir)
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["error"] == {"type": "RuntimeError", "message": "taxonomy exploded"}
    assert payload["provider_id"] == "electronet"
    assert payload["product"]["mpn"] == "GSGV80PYLL"
