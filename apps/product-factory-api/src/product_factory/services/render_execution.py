from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping

from ..csv_writer import write_csv_row
from ..html_builders import extract_presentation_blocks
from ..llm_contract import (
    INTRO_MAX_WORDS,
    INTRO_MIN_WORDS,
    MAX_EMPHASIZED_WORD_RATIO,
    validate_intro_text_output,
    validate_seo_meta_output,
)
from ..mapping import build_row
from ..models import GalleryImage, SourceProductData, SpecItem, SpecSection
from ..presentation_sections import normalize_presentation_sections
from ..repo_paths import REPO_ROOT, category_filter_review_path
from ..utils import ensure_directory, read_json, utcnow_iso, write_json, write_text
from ..validator import validate_candidate_csv, write_validation_report
from .execution_models import (
    PreparedProductContext,
    RenderExecutionResult,
    RenderExecutionValidationReport,
)
from .errors import ServiceErrorCode, service_error_from_exception
from .llm_stage_execution import (
    IntroTextResolver,
    SeoMetaResolver,
    SplitLLMStageResult,
    execute_split_llm_stage,
)
from .metadata import maybe_write_run_metadata
from .models import RunArtifacts, RunStatus, RunType
from .settings_service import get_intro_text_policy

WORK_ROOT = REPO_ROOT / "work"
PRODUCTS_ROOT = REPO_ROOT / "products"


def execute_render_workflow(
    model: str,
    *,
    work_root: Path = WORK_ROOT,
    products_root: Path = PRODUCTS_ROOT,
    resolve_intro_text_fn: IntroTextResolver | None = None,
    resolve_seo_meta_fn: SeoMetaResolver | None = None,
) -> RenderExecutionResult:
    model_root = work_root / model
    prepared_context = PreparedProductContext.from_model(model, model_root=model_root)
    scrape_dir = prepared_context.scrape_dir
    llm_dir = prepared_context.llm_dir
    source_json = prepared_context.source_json_path
    normalized_json = prepared_context.scrape_normalized_json_path
    task_manifest_json = prepared_context.task_manifest_path
    candidate_dir = model_root / "candidate"
    candidate_csv_path = candidate_dir / f"{model}.csv"
    published_csv_path = products_root / f"{model}.csv"
    review_path = category_filter_review_path(model, repo_root=work_root.parent)
    description_path = candidate_dir / "description.html"
    characteristics_path = candidate_dir / "characteristics.html"
    normalized_candidate_path = candidate_dir / f"{model}.normalized.json"
    validation_report_path = candidate_dir / f"{model}.validation.json"
    llm_artifact_paths = {
        "intro_text_output_path": llm_dir / "intro_text.output.txt",
        "intro_text_trace_path": llm_dir / "intro_text.retry_trace.json",
        "seo_meta_output_path": llm_dir / "seo_meta.output.json",
    }
    requested_at = utcnow_iso()
    started_at = requested_at
    try:
        if not source_json.exists() or not normalized_json.exists():
            raise FileNotFoundError(f"Missing scrape artifacts in {scrape_dir}")

        prepared_context = prepared_context.load_for_render(
            source_loader=load_source_product,
            json_loader=read_json,
        )
        source = prepared_context.source_product
        if source is None:
            raise ValueError("Prepared product context is missing source product data")
        characteristics_source = _load_characteristics_source_from_normalized(
            prepared_context.normalized_payload,
            fallback=source,
        )
        cli = prepared_context.build_render_cli(candidate_out=candidate_dir)
        taxonomy = prepared_context.require_taxonomy()
        schema_match = prepared_context.require_schema_match()
        parsed = prepared_context.require_parsed()
        intro_policy = get_intro_text_policy(
            source=source.source_name,
            category_id=str(getattr(taxonomy, "category_id", "") or ""),
            taxonomy_path=str(getattr(taxonomy, "taxonomy_path", "") or ""),
        )

        split_llm_result = execute_split_llm_stage(
            llm_dir=llm_dir,
            task_manifest_path=task_manifest_json,
            resolve_intro_text_fn=resolve_intro_text_fn,
            resolve_seo_meta_fn=resolve_seo_meta_fn,
            intro_policy=intro_policy,
        )
        llm_errors = _build_llm_validation_backstop_errors(
            split_llm_result, intro_policy=intro_policy
        )
        llm_mode = "split_tasks"
        llm_artifact_paths = split_llm_result.artifact_paths

        extracted_sections = extract_presentation_blocks(
            presentation_source_html=source.presentation_source_html,
            presentation_source_text=source.presentation_source_text,
            base_url=source.canonical_url or source.url,
        )
        render_sections, section_warnings = _resolve_render_sections(
            extracted_sections=extracted_sections,
            sections_requested=max(int(cli.sections), 0),
        )

        candidate_dir = ensure_directory(model_root / "candidate")

        besco_filenames_by_section = {
            image.position: image.local_filename
            for image in source.besco_images
            if image.local_filename
        }
        row, candidate_normalized, mapping_warnings = build_row(
            cli=cli,
            parsed=parsed,
            taxonomy=taxonomy,
            schema_match=schema_match,
            downloaded_image_count=len(source.gallery_images),
            besco_filenames_by_section=besco_filenames_by_section,
            llm_product=split_llm_result.llm_product,
            llm_intro_text=split_llm_result.intro_text,
            deterministic_presentation_sections=render_sections,
            model_root=model_root,
            characteristics_source=characteristics_source,
        )
        headers, ordered_row = write_csv_row(row, candidate_csv_path)
        candidate_normalized["csv_headers"] = headers
        candidate_normalized["csv_ordered_row"] = ordered_row
        candidate_normalized["mapping_warnings"] = mapping_warnings
        candidate_normalized["llm_mode"] = llm_mode
        candidate_normalized["llm_artifact_paths"] = {
            key: str(value) for key, value in llm_artifact_paths.items()
        }
        candidate_normalized["presentation_sections"] = render_sections
        write_json(normalized_candidate_path, candidate_normalized)
        write_text(description_path, row["description"])
        write_text(characteristics_path, row["characteristics"])

        baseline_path = products_root / f"{model}.csv"
        validation_report = validate_candidate_csv(
            csv_path=candidate_csv_path,
            baseline_path=baseline_path if baseline_path.exists() else None,
            llm_errors=llm_errors,
            category_filter_errors=list(
                candidate_normalized.get("category_filters", {}).get("errors", [])
            ),
            category_filter_warnings=list(
                candidate_normalized.get("category_filters", {}).get("warnings", [])
            ),
        )
        category_filter_warnings = set(
            candidate_normalized.get("category_filters", {}).get("warnings", [])
        )
        non_category_mapping_warnings = [
            warning
            for warning in mapping_warnings
            if warning not in category_filter_warnings
        ]
        if non_category_mapping_warnings:
            validation_report["warnings"].extend(non_category_mapping_warnings)
        if section_warnings:
            validation_report["warnings"].extend(section_warnings)
        validation_ok = bool(validation_report.get("ok", False))
        if not validation_ok:
            validation_report["warnings"].append(
                "Candidate failed validation; skipping publish to products/."
            )
        write_validation_report(validation_report, validation_report_path)

        published_csv_result_path: Path | None = None
        if validation_ok:
            ensure_directory(products_root)
            shutil.copyfile(candidate_csv_path, published_csv_path)
            published_csv_result_path = published_csv_path
        run_status = RunStatus.COMPLETED if validation_ok else RunStatus.FAILED
        finished_at = utcnow_iso()
        run_warnings = list(validation_report.get("warnings", []))
        metadata_path = maybe_write_run_metadata(
            model=model,
            run_type=RunType.RENDER,
            status=run_status,
            model_root=model_root,
            artifacts=RunArtifacts(
                model_root=model_root,
                scrape_dir=scrape_dir,
                llm_dir=llm_dir if llm_dir.exists() else None,
                candidate_dir=candidate_dir,
                source_json_path=source_json,
                scrape_normalized_json_path=normalized_json,
                llm_task_manifest_path=(
                    task_manifest_json if task_manifest_json.exists() else None
                ),
                intro_text_output_path=llm_artifact_paths.get("intro_text_output_path"),
                seo_meta_output_path=llm_artifact_paths.get("seo_meta_output_path"),
                candidate_csv_path=candidate_csv_path,
                published_csv_path=published_csv_result_path,
                candidate_normalized_json_path=normalized_candidate_path,
                validation_report_path=validation_report_path,
                description_html_path=description_path,
                characteristics_html_path=characteristics_path,
                category_filter_review_path=(
                    review_path if review_path.exists() else None
                ),
            ),
            requested_at=requested_at,
            started_at=started_at,
            finished_at=finished_at,
            warnings=run_warnings,
            error_code=(
                None if validation_ok else ServiceErrorCode.VALIDATION_FAILURE.value
            ),
            error_detail=None if validation_ok else "Candidate validation failed",
            details={
                "validation_ok": validation_ok,
                "published": validation_ok,
                "llm_mode": llm_mode,
                "intro_text_trace_path": str(
                    llm_artifact_paths["intro_text_trace_path"]
                ),
            },
        )

        return RenderExecutionResult(
            candidate_dir=candidate_dir,
            candidate_csv_path=candidate_csv_path,
            published_csv_path=published_csv_result_path,
            description_path=description_path,
            characteristics_path=characteristics_path,
            validation_report_path=validation_report_path,
            run_status=run_status,
            metadata_path=metadata_path,
            validation_report=RenderExecutionValidationReport.from_mapping(
                validation_report
            ),
        )
    except Exception as exc:
        finished_at = utcnow_iso()
        if model_root.exists():
            service_error = service_error_from_exception(exc, operation="render")
            maybe_write_run_metadata(
                model=model,
                run_type=RunType.RENDER,
                status=RunStatus.FAILED,
                model_root=model_root,
                artifacts=RunArtifacts(
                    model_root=model_root,
                    scrape_dir=scrape_dir,
                    llm_dir=llm_dir if llm_dir.exists() else None,
                    candidate_dir=candidate_dir,
                    source_json_path=source_json,
                    scrape_normalized_json_path=normalized_json,
                    llm_task_manifest_path=(
                        task_manifest_json if task_manifest_json.exists() else None
                    ),
                    intro_text_output_path=llm_artifact_paths.get(
                        "intro_text_output_path"
                    ),
                    seo_meta_output_path=llm_artifact_paths.get("seo_meta_output_path"),
                    candidate_csv_path=candidate_csv_path,
                    published_csv_path=published_csv_path,
                    candidate_normalized_json_path=normalized_candidate_path,
                    validation_report_path=validation_report_path,
                    description_html_path=description_path,
                    characteristics_html_path=characteristics_path,
                    category_filter_review_path=(
                        review_path if review_path.exists() else None
                    ),
                ),
                requested_at=requested_at,
                started_at=started_at,
                finished_at=finished_at,
                error_code=service_error.code,
                error_detail=service_error.message,
                details=dict(service_error.details),
            )
        raise


def load_source_product(path: str | Path) -> SourceProductData:
    payload = read_json(path)
    return _source_product_from_payload(payload)


def _load_characteristics_source_from_normalized(
    normalized_payload: Mapping[str, Any],
    *,
    fallback: SourceProductData,
) -> SourceProductData:
    payload = normalized_payload.get("characteristics_source")
    if not isinstance(payload, Mapping):
        return fallback
    return _source_product_from_payload(payload)


def _source_product_from_payload(payload: Mapping[str, Any]) -> SourceProductData:
    return SourceProductData(
        source_name=payload.get("source_name", ""),
        page_type=payload.get("page_type", "product"),
        url=payload.get("url", ""),
        canonical_url=payload.get("canonical_url", ""),
        breadcrumbs=list(payload.get("breadcrumbs", [])),
        skroutz_family=payload.get("skroutz_family", ""),
        category_tag_text=payload.get("category_tag_text", ""),
        category_tag_href=payload.get("category_tag_href", ""),
        category_tag_slug=payload.get("category_tag_slug", ""),
        taxonomy_source_category=payload.get("taxonomy_source_category", ""),
        taxonomy_match_type=payload.get("taxonomy_match_type", ""),
        taxonomy_rule_id=payload.get("taxonomy_rule_id", ""),
        taxonomy_ambiguity=bool(payload.get("taxonomy_ambiguity", False)),
        taxonomy_escalation_reason=payload.get("taxonomy_escalation_reason", ""),
        taxonomy_tv_inches=payload.get("taxonomy_tv_inches"),
        product_code=payload.get("product_code", ""),
        brand=payload.get("brand", ""),
        name=payload.get("name", ""),
        hero_summary=payload.get("hero_summary", ""),
        price_text=payload.get("price_text", ""),
        price_value=payload.get("price_value"),
        installments_text=payload.get("installments_text", ""),
        delivery_text=payload.get("delivery_text", ""),
        pickup_text=payload.get("pickup_text", ""),
        gallery_images=[
            GalleryImage(**item) for item in payload.get("gallery_images", [])
        ],
        besco_images=[GalleryImage(**item) for item in payload.get("besco_images", [])],
        energy_label_asset_url=payload.get("energy_label_asset_url", ""),
        product_sheet_asset_url=payload.get("product_sheet_asset_url", ""),
        key_specs=[SpecItem(**item) for item in payload.get("key_specs", [])],
        spec_sections=[
            SpecSection(
                section=section.get("section", ""),
                items=[SpecItem(**item) for item in section.get("items", [])],
            )
            for section in payload.get("spec_sections", [])
        ],
        manufacturer_spec_sections=[
            SpecSection(
                section=section.get("section", ""),
                items=[SpecItem(**item) for item in section.get("items", [])],
            )
            for section in payload.get("manufacturer_spec_sections", [])
        ],
        manufacturer_source_text=payload.get("manufacturer_source_text", ""),
        manufacturer_documents=list(payload.get("manufacturer_documents", [])),
        presentation_source_html=payload.get("presentation_source_html", ""),
        presentation_source_text=payload.get("presentation_source_text", ""),
        raw_html_path=payload.get("raw_html_path", ""),
        scraped_at=payload.get("scraped_at", ""),
        fallback_used=bool(payload.get("fallback_used", False)),
        mpn=payload.get("mpn", ""),
    )


def _build_llm_validation_backstop_errors(
    split_llm_result: SplitLLMStageResult, *, intro_policy=None
) -> list[str]:
    intro_text, intro_errors = validate_intro_text_output(
        split_llm_result.intro_text,
        intro_word_min=getattr(intro_policy, "min_words", INTRO_MIN_WORDS),
        intro_word_max=getattr(intro_policy, "max_words", INTRO_MAX_WORDS),
        intro_max_emphasized_word_ratio=getattr(
            intro_policy, "max_emphasized_word_ratio", MAX_EMPHASIZED_WORD_RATIO
        ),
    )
    _, seo_errors = validate_seo_meta_output(
        {
            "product": {
                "meta_description": split_llm_result.llm_product.get(
                    "meta_description", ""
                ),
                "meta_keywords": split_llm_result.llm_product.get("meta_keywords", []),
            }
        }
    )
    del intro_text
    return [*intro_errors, *seo_errors]


def _resolve_render_sections(
    *,
    extracted_sections: list[dict[str, object]],
    sections_requested: int,
) -> tuple[list[dict[str, object]], list[str]]:
    if sections_requested <= 0:
        return [], []
    if not extracted_sections:
        raise ValueError(
            "Missing presentation source sections for requested render sections"
        )

    normalized_sections = normalize_presentation_sections(
        extracted_sections, sections_requested=sections_requested
    )
    usable_sections = [
        {
            "title": section.title,
            "body_text": section.body_text,
            "quality": section.quality,
            "reason": section.reason,
            "metrics": section.metrics.to_dict(),
            "source_index": section.source_index,
            "image_url": section.image_url,
        }
        for section in normalized_sections
        if section.quality == "usable"
    ]
    weak_sections = [
        {
            "title": section.title,
            "body_text": section.body_text,
            "quality": section.quality,
            "reason": section.reason,
            "metrics": section.metrics.to_dict(),
            "source_index": section.source_index,
            "image_url": section.image_url,
        }
        for section in normalized_sections
        if section.quality == "weak"
    ]
    missing_count = sum(
        1 for section in normalized_sections if section.quality == "missing"
    )
    weak_count = sum(1 for section in normalized_sections if section.quality == "weak")

    selected_sections = usable_sections[:]
    if len(selected_sections) < sections_requested:
        selected_sections.extend(
            weak_sections[: max(sections_requested - len(selected_sections), 0)]
        )
    selected_sections = sorted(
        selected_sections, key=lambda section: int(section.get("source_index") or 0)
    )

    if not selected_sections:
        raise ValueError(
            "No usable deterministic presentation sections for requested render sections"
        )
    warnings: list[str] = []
    if weak_count > 0:
        warnings.append(f"presentation_sections_weak:{weak_count}")
    if missing_count > 0:
        warnings.append(f"presentation_sections_missing:{missing_count}")
    if len(selected_sections) < sections_requested:
        warnings.append(f"requested_sections_reduced:{len(selected_sections)}")
    return selected_sections[:sections_requested], warnings
