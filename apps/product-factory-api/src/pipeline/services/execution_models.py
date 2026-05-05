from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from ..models import CLIInput, ParsedProduct, SchemaMatchResult, SourceProductData, TaxonomyResolution
from .models import RunStatus

_T = TypeVar("_T")


def _as_dict(payload: Mapping[str, object] | None) -> dict[str, object]:
    return dict(payload or {})


def _require_path(payload: Mapping[str, object], field_name: str) -> Path:
    value = payload[field_name]
    if value in (None, ""):
        raise ValueError(f"{field_name} is required")
    return Path(value)


def _optional_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    return Path(value)


def _coerce_run_status(value: RunStatus | str) -> RunStatus:
    if isinstance(value, RunStatus):
        return value
    return RunStatus(str(value))


def _typed_or_none(value: Any, expected_type: type[_T]) -> _T | None:
    if isinstance(value, expected_type):
        return value
    return None


def _coerce_warnings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]


@dataclass(slots=True)
class PreparedProductContext:
    model: str
    model_root: Path
    scrape_dir: Path
    llm_dir: Path
    source_json_path: Path
    scrape_normalized_json_path: Path
    source_report_json_path: Path
    task_manifest_path: Path
    intro_text_context_path: Path
    intro_text_prompt_path: Path
    intro_text_output_path: Path
    seo_meta_context_path: Path
    seo_meta_prompt_path: Path
    seo_meta_output_path: Path
    source_product: SourceProductData | None = None
    parsed: ParsedProduct | None = None
    taxonomy: TaxonomyResolution | None = None
    schema_match: SchemaMatchResult | None = None
    normalized_payload: Mapping[str, Any] = field(default_factory=dict)
    report_payload: Mapping[str, Any] = field(default_factory=dict)
    payload: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_model(cls, model: str, *, model_root: Path) -> "PreparedProductContext":
        scrape_dir = model_root / "scrape"
        llm_dir = model_root / "llm"
        return cls(
            model=model,
            model_root=model_root,
            scrape_dir=scrape_dir,
            llm_dir=llm_dir,
            source_json_path=scrape_dir / f"{model}.source.json",
            scrape_normalized_json_path=scrape_dir / f"{model}.normalized.json",
            source_report_json_path=scrape_dir / f"{model}.report.json",
            task_manifest_path=llm_dir / "task_manifest.json",
            intro_text_context_path=llm_dir / "intro_text.context.json",
            intro_text_prompt_path=llm_dir / "intro_text.prompt.txt",
            intro_text_output_path=llm_dir / "intro_text.output.txt",
            seo_meta_context_path=llm_dir / "seo_meta.context.json",
            seo_meta_prompt_path=llm_dir / "seo_meta.prompt.txt",
            seo_meta_output_path=llm_dir / "seo_meta.output.json",
        )

    @classmethod
    def from_prepare_stage_result(
        cls,
        *,
        cli: CLIInput,
        model_root: Path,
        scrape_dir: Path,
        llm_dir: Path,
        stage_result: Mapping[str, object],
    ) -> "PreparedProductContext":
        context = cls.from_model(cli.model, model_root=model_root)
        payload_dict = _as_dict(stage_result)
        normalized_payload = payload_dict.get("normalized")
        normalized_dict = normalized_payload if isinstance(normalized_payload, Mapping) else {}
        report_payload = payload_dict.get("report")
        report_dict = report_payload if isinstance(report_payload, Mapping) else {}
        parsed = _typed_or_none(payload_dict.get("parsed"), ParsedProduct)
        return cls(
            model=cli.model,
            model_root=model_root,
            scrape_dir=scrape_dir,
            llm_dir=llm_dir,
            source_json_path=_path_from_payload(payload_dict, "source_json_path", context.source_json_path),
            scrape_normalized_json_path=_path_from_payload(payload_dict, "normalized_json_path", context.scrape_normalized_json_path),
            source_report_json_path=_path_from_payload(payload_dict, "report_json_path", context.source_report_json_path),
            task_manifest_path=llm_dir / "task_manifest.json",
            intro_text_context_path=llm_dir / "intro_text.context.json",
            intro_text_prompt_path=llm_dir / "intro_text.prompt.txt",
            intro_text_output_path=llm_dir / "intro_text.output.txt",
            seo_meta_context_path=llm_dir / "seo_meta.context.json",
            seo_meta_prompt_path=llm_dir / "seo_meta.prompt.txt",
            seo_meta_output_path=llm_dir / "seo_meta.output.json",
            source_product=parsed.source if parsed is not None else None,
            parsed=parsed,
            taxonomy=_typed_or_none(payload_dict.get("taxonomy"), TaxonomyResolution),
            schema_match=_typed_or_none(payload_dict.get("schema_match"), SchemaMatchResult),
            normalized_payload=normalized_dict,
            report_payload=report_dict,
            payload=payload_dict,
        )

    @property
    def deterministic_product(self) -> dict[str, Any]:
        deterministic_payload = self.normalized_payload.get("deterministic_product", {})
        if not isinstance(deterministic_payload, Mapping):
            return {}
        return dict(deterministic_payload)

    def require_parsed(self) -> ParsedProduct:
        if self.parsed is None:
            raise ValueError("Prepared product context is missing parsed product data")
        return self.parsed

    def require_taxonomy(self) -> TaxonomyResolution:
        if self.taxonomy is None:
            raise ValueError("Prepared product context is missing taxonomy data")
        return self.taxonomy

    def require_schema_match(self) -> SchemaMatchResult:
        if self.schema_match is None:
            raise ValueError("Prepared product context is missing schema match data")
        return self.schema_match

    def load_for_render(
        self,
        *,
        source_loader: Callable[[Path], SourceProductData],
        json_loader: Callable[[Path], dict[str, Any]],
    ) -> "PreparedProductContext":
        source_product = source_loader(self.source_json_path)
        normalized = json_loader(self.scrape_normalized_json_path)
        return self.with_render_payloads(
            source_product=source_product,
            normalized_payload=normalized,
        )

    def with_render_payloads(
        self,
        *,
        source_product: SourceProductData,
        normalized_payload: Mapping[str, Any],
    ) -> "PreparedProductContext":
        taxonomy = TaxonomyResolution(**normalized_payload.get("taxonomy", {}))
        schema_match = SchemaMatchResult(**normalized_payload.get("schema_match", {}))
        return PreparedProductContext(
            model=self.model,
            model_root=self.model_root,
            scrape_dir=self.scrape_dir,
            llm_dir=self.llm_dir,
            source_json_path=self.source_json_path,
            scrape_normalized_json_path=self.scrape_normalized_json_path,
            source_report_json_path=self.source_report_json_path,
            task_manifest_path=self.task_manifest_path,
            intro_text_context_path=self.intro_text_context_path,
            intro_text_prompt_path=self.intro_text_prompt_path,
            intro_text_output_path=self.intro_text_output_path,
            seo_meta_context_path=self.seo_meta_context_path,
            seo_meta_prompt_path=self.seo_meta_prompt_path,
            seo_meta_output_path=self.seo_meta_output_path,
            source_product=source_product,
            parsed=ParsedProduct(source=source_product),
            taxonomy=taxonomy,
            schema_match=schema_match,
            normalized_payload=normalized_payload,
            report_payload=self.report_payload,
            payload=self.payload,
        )

    def build_render_cli(self, *, candidate_out: Path) -> CLIInput:
        input_data = self.normalized_payload.get("input", {})
        return CLIInput(
            model=str(input_data.get("model", self.model)),
            url=str(input_data.get("url", "")),
            photos=int(input_data.get("photos", 1)),
            sections=int(input_data.get("sections", 0)),
            skroutz_status=int(input_data.get("skroutz_status", 0)),
            boxnow=int(input_data.get("boxnow", 0)),
            price=input_data.get("price", 0),
            out=str(candidate_out),
        )


def _path_from_payload(payload: Mapping[str, object], field_name: str, default: Path) -> Path:
    value = payload.get(field_name)
    if value in (None, ""):
        return default
    return Path(value)


@dataclass(slots=True)
class PrepareExecutionScrapeResult:
    source: str = ""
    parsed: ParsedProduct | None = None
    taxonomy: TaxonomyResolution | None = None
    schema_match: SchemaMatchResult | None = None
    report_warnings: list[str] = field(default_factory=list)
    payload: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object] | None) -> "PrepareExecutionScrapeResult":
        payload_dict = _as_dict(payload)
        report = payload_dict.get("report")
        report_dict = _as_dict(report) if isinstance(report, Mapping) else {}
        return cls(
            source=str(payload_dict.get("source", "") or ""),
            parsed=_typed_or_none(payload_dict.get("parsed"), ParsedProduct),
            taxonomy=_typed_or_none(payload_dict.get("taxonomy"), TaxonomyResolution),
            schema_match=_typed_or_none(payload_dict.get("schema_match"), SchemaMatchResult),
            report_warnings=_coerce_warnings(report_dict.get("warnings")),
            payload=payload_dict,
        )


@dataclass(slots=True)
class PrepareExecutionResult:
    model_root: Path
    scrape_dir: Path
    llm_dir: Path
    task_manifest_path: Path
    intro_text_context_path: Path
    intro_text_prompt_path: Path
    intro_text_output_path: Path
    seo_meta_context_path: Path
    seo_meta_prompt_path: Path
    seo_meta_output_path: Path
    run_status: RunStatus
    metadata_path: Path
    scrape_result: PrepareExecutionScrapeResult = field(default_factory=PrepareExecutionScrapeResult)
    payload: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "PrepareExecutionResult":
        payload_dict = _as_dict(payload)
        return cls(
            model_root=_require_path(payload_dict, "model_root"),
            scrape_dir=_require_path(payload_dict, "scrape_dir"),
            llm_dir=_require_path(payload_dict, "llm_dir"),
            task_manifest_path=_require_path(payload_dict, "task_manifest_path"),
            intro_text_context_path=_require_path(payload_dict, "intro_text_context_path"),
            intro_text_prompt_path=_require_path(payload_dict, "intro_text_prompt_path"),
            intro_text_output_path=_require_path(payload_dict, "intro_text_output_path"),
            seo_meta_context_path=_require_path(payload_dict, "seo_meta_context_path"),
            seo_meta_prompt_path=_require_path(payload_dict, "seo_meta_prompt_path"),
            seo_meta_output_path=_require_path(payload_dict, "seo_meta_output_path"),
            run_status=_coerce_run_status(payload_dict["run_status"]),
            metadata_path=_require_path(payload_dict, "metadata_path"),
            scrape_result=PrepareExecutionScrapeResult.from_mapping(payload_dict.get("scrape_result")),
            payload=payload_dict,
        )


@dataclass(slots=True)
class RenderExecutionValidationReport:
    ok: bool = False
    warnings: list[str] = field(default_factory=list)
    payload: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object] | None) -> "RenderExecutionValidationReport":
        payload_dict = _as_dict(payload)
        return cls(
            ok=bool(payload_dict.get("ok", False)),
            warnings=_coerce_warnings(payload_dict.get("warnings")),
            payload=payload_dict,
        )


@dataclass(slots=True)
class RenderExecutionResult:
    candidate_dir: Path
    candidate_csv_path: Path
    published_csv_path: Path | None
    description_path: Path
    characteristics_path: Path
    validation_report_path: Path
    run_status: RunStatus
    metadata_path: Path
    validation_report: RenderExecutionValidationReport = field(default_factory=RenderExecutionValidationReport)
    payload: dict[str, object] = field(default_factory=dict)

    @property
    def model_root(self) -> Path:
        return self.candidate_dir.parent

    @property
    def scrape_dir(self) -> Path:
        return self.model_root / "scrape"

    @property
    def llm_dir(self) -> Path:
        return self.model_root / "llm"

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "RenderExecutionResult":
        payload_dict = _as_dict(payload)
        return cls(
            candidate_dir=_require_path(payload_dict, "candidate_dir"),
            candidate_csv_path=_require_path(payload_dict, "candidate_csv_path"),
            published_csv_path=_optional_path(payload_dict.get("published_csv_path")),
            description_path=_require_path(payload_dict, "description_path"),
            characteristics_path=_require_path(payload_dict, "characteristics_path"),
            validation_report_path=_require_path(payload_dict, "validation_report_path"),
            run_status=_coerce_run_status(payload_dict["run_status"]),
            metadata_path=_require_path(payload_dict, "metadata_path"),
            validation_report=RenderExecutionValidationReport.from_mapping(payload_dict.get("validation_report")),
            payload=payload_dict,
        )
