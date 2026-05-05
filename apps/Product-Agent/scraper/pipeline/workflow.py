from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .input_validation import FAIL_MESSAGE, validate_input
from .models import CLIInput
from .prepare_stage import execute_prepare_stage
from .repo_paths import REPO_ROOT
from .services.errors import ServiceError, ServiceErrorCode
from .services.execution_models import PrepareExecutionResult, RenderExecutionResult
from .services.models import PrepareRequest, PublishRequest, RenderRequest, ServiceResult
from .services.prepare_execution import execute_prepare_workflow
from .services.prepare_service import prepare_product
from .services.publish_service import build_publish_phase_details, publish_product
from .services.render_execution import execute_render_workflow
from .services.render_service import render_product

WORK_ROOT = REPO_ROOT / "work"
PRODUCTS_ROOT = REPO_ROOT / "products"
SERVICE_ERROR_EXIT_CODES = {
    ServiceErrorCode.MISSING_ARTIFACT.value: 3,
    ServiceErrorCode.PROVIDER_FAILURE.value: 4,
    ServiceErrorCode.VALIDATION_FAILURE.value: 5,
    ServiceErrorCode.PARSE_FAILURE.value: 6,
    ServiceErrorCode.PUBLISH_FAILURE.value: 7,
    ServiceErrorCode.UNEXPECTED_FAILURE.value: 8,
}


def exit_code_for_service_error(code: str | None) -> int:
    return SERVICE_ERROR_EXIT_CODES.get(str(code or ""), SERVICE_ERROR_EXIT_CODES[ServiceErrorCode.UNEXPECTED_FAILURE.value])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pipeline.workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    add_template_options(prepare_parser)
    add_input_fields(prepare_parser)

    render_parser = subparsers.add_parser("render")
    add_template_options(render_parser)
    render_parser.add_argument("--model", default=None)

    return parser


def add_template_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--template-file", default=None)
    parser.add_argument("--stdin", action="store_true")


def add_input_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default=None)
    parser.add_argument("--url", default=None)
    parser.add_argument("--photos", type=int, default=None)
    parser.add_argument("--sections", type=int, default=None)
    parser.add_argument("--skroutz-status", type=int, default=None, dest="skroutz_status")
    parser.add_argument("--boxnow", type=int, default=None)
    parser.add_argument("--price", default=None)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            cli = build_cli_input_from_args(args)
            result = prepare_product(
                PrepareRequest(
                    model=cli.model,
                    url=cli.url,
                    photos=cli.photos,
                    sections=cli.sections,
                    skroutz_status=cli.skroutz_status,
                    boxnow=cli.boxnow,
                    price=cli.price,
                )
            )
            print(f"Scrape artifacts: {result.artifacts.scrape_dir}")
            print(f"LLM task manifest: {result.artifacts.llm_task_manifest_path}")
            print(f"Intro task context: {result.artifacts.intro_text_context_path}")
            print(f"Intro task prompt: {result.artifacts.intro_text_prompt_path}")
            print(f"SEO task context: {result.artifacts.seo_meta_context_path}")
            print(f"SEO task prompt: {result.artifacts.seo_meta_prompt_path}")
            print(f"Run status: {result.run.status.value}")
            print(f"Metadata path: {result.artifacts.metadata_path}")
            return 0

        model = resolve_model_for_render(args)
        render_result = render_product(RenderRequest(model=model))
        publish_result = (
            publish_product(
                PublishRequest(
                    model=model,
                    current_job_product_file=render_result.artifacts.published_csv_path,
                )
            )
            if render_result.artifacts.published_csv_path is not None
            else None
        )
        publish_details = build_publish_phase_details(model, publish_result)
        _print_render_cli_summary(render_result, publish_details)
        return 0 if bool(render_result.details.get("validation_ok", False)) else exit_code_for_service_error(render_result.run.error_code)
    except ValueError as exc:
        message = str(exc)
        print(message)
        return 1 if message == FAIL_MESSAGE else 2
    except ServiceError as exc:
        print(exc.message, file=sys.stderr)
        return exit_code_for_service_error(exc.code)


def build_cli_input_from_args(args: argparse.Namespace) -> CLIInput:
    template_values = read_template_values(args.template_file, args.stdin)
    merged = {
        "model": template_values.get("model", ""),
        "url": template_values.get("url", ""),
        "photos": template_values.get("photos", "1"),
        "sections": template_values.get("sections", "0"),
        "skroutz_status": template_values.get("skroutz_status", "0"),
        "boxnow": template_values.get("boxnow", "0"),
        "price": template_values.get("price", "0"),
    }
    for key in ["model", "url", "photos", "sections", "skroutz_status", "boxnow", "price"]:
        value = getattr(args, key, None)
        if value is not None:
            merged[key] = value
    namespace = argparse.Namespace(
        model=merged["model"],
        url=merged["url"],
        photos=merged["photos"],
        sections=merged["sections"],
        skroutz_status=merged["skroutz_status"],
        boxnow=merged["boxnow"],
        price=merged["price"],
        out=str(WORK_ROOT),
    )
    cli = validate_input(namespace)
    return CLIInput(
        model=cli.model,
        url=cli.url,
        photos=cli.photos,
        sections=cli.sections,
        skroutz_status=cli.skroutz_status,
        boxnow=cli.boxnow,
        price=cli.price,
        out=str(WORK_ROOT / cli.model / "scrape"),
    )


def read_template_values(template_file: str | None, use_stdin: bool) -> dict[str, str]:
    if template_file:
        text = Path(template_file).read_text(encoding="utf-8")
        return parse_template_text(text)
    if use_stdin:
        text = sys.stdin.read()
        return parse_template_text(text)
    return {}


def parse_template_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized_key in {"model", "url", "photos", "sections", "skroutz_status", "boxnow", "price"}:
            values[normalized_key] = value.strip()
    return values


def prepare_workflow(cli: CLIInput) -> PrepareExecutionResult:
    return execute_prepare_workflow(cli, work_root=WORK_ROOT, execute_prepare_stage_fn=execute_prepare_stage)


def resolve_model_for_render(args: argparse.Namespace) -> str:
    values = read_template_values(args.template_file, args.stdin)
    model = str(args.model or values.get("model", "")).strip()
    if not model:
        raise ValueError(FAIL_MESSAGE)
    if not model.isdigit() or len(model) != 6:
        raise ValueError(FAIL_MESSAGE)
    return model


def render_workflow(model: str) -> RenderExecutionResult:
    return execute_render_workflow(model, work_root=WORK_ROOT, products_root=PRODUCTS_ROOT)


def _print_render_cli_summary(
    render_result: ServiceResult,
    publish_details: dict[str, str | int | float | bool | None],
) -> None:
    print(f"Candidate CSV: {render_result.artifacts.candidate_csv_path}")
    if render_result.artifacts.published_csv_path is not None:
        print(f"Published CSV: {render_result.artifacts.published_csv_path}")
    print(f"Validation report: {render_result.artifacts.validation_report_path}")
    print(f"Validation ok: {bool(render_result.details.get('validation_ok', False))}")
    print(f"Render status: {'success' if bool(render_result.details.get('validation_ok', False)) else 'failure'}")
    print(f"Publish status: {publish_details.get('publish_status')}")
    print(f"Publish stage: {publish_details.get('publish_stage')}")
    if publish_details.get("publish_message") is not None:
        print(f"Publish message: {publish_details.get('publish_message')}")
    if publish_details.get("upload_report_path"):
        print(f"OpenCart upload report: {publish_details.get('upload_report_path')}")
    if publish_details.get("import_report_path"):
        print(f"OpenCart import report: {publish_details.get('import_report_path')}")
    print(f"Run status: {render_result.run.status.value}")
    print(f"Metadata path: {render_result.artifacts.metadata_path}")
    if publish_details.get("publish_metadata_path"):
        print(f"Publish metadata path: {publish_details.get('publish_metadata_path')}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
