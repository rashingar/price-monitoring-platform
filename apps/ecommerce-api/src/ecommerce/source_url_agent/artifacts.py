"""Artifact writers for Source URL Agent Mode."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ecommerce.source_url_agent.candidates import SourceUrlAgentCandidate


SOURCE_URL_AGENT_RUNS_DIR = Path("output") / "ecommerce" / "source-url-agent" / "runs"
RESULT_COLUMNS = [
    "model",
    "catalog_product_id",
    "catalog_name",
    "mpn",
    "manufacturer",
    "category",
    "own_price",
    "source_name",
    "source_domain",
    "source_type",
    "expected_listing",
    "candidate_url",
    "canonical_url",
    "candidate_title",
    "candidate_price",
    "match_status",
    "confidence_score",
    "match_method",
    "evidence_mpn",
    "evidence_brand",
    "evidence_model",
    "evidence_category",
    "evidence_price",
    "competing_candidates_count",
    "searched_queries",
    "notes",
    "checked_at",
]
REVIEW_COLUMNS = [
    "review_decision",
    "reviewed_url",
    "review_notes",
    "reviewed_by",
    "reviewed_at",
]


@dataclass(frozen=True)
class SourceUrlAgentArtifactPaths:
    run_dir: Path
    source_url_results: Path
    approved_source_urls: Path
    needs_review_source_urls: Path
    not_found_source_urls: Path
    errors: Path
    source_url_run_summary: Path
    searched_queries: Path
    rule_suggestions: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "run_dir": str(self.run_dir),
            "source_url_results": str(self.source_url_results),
            "approved_source_urls": str(self.approved_source_urls),
            "needs_review_source_urls": str(self.needs_review_source_urls),
            "not_found_source_urls": str(self.not_found_source_urls),
            "errors": str(self.errors),
            "source_url_run_summary": str(self.source_url_run_summary),
            "searched_queries": str(self.searched_queries),
            "rule_suggestions": str(self.rule_suggestions),
        }


def run_artifact_paths(run_id: str, output_dir: Path | None = None) -> SourceUrlAgentArtifactPaths:
    root = output_dir or SOURCE_URL_AGENT_RUNS_DIR
    run_dir = Path(root) / run_id
    return SourceUrlAgentArtifactPaths(
        run_dir=run_dir,
        source_url_results=run_dir / "source_url_results.csv",
        approved_source_urls=run_dir / "approved_source_urls.csv",
        needs_review_source_urls=run_dir / "needs_review_source_urls.csv",
        not_found_source_urls=run_dir / "not_found_source_urls.csv",
        errors=run_dir / "errors.csv",
        source_url_run_summary=run_dir / "source_url_run_summary.json",
        searched_queries=run_dir / "searched_queries.json",
        rule_suggestions=run_dir / "rule_suggestions.json",
    )


def write_run_artifacts(
    *,
    run_id: str,
    candidates: list[SourceUrlAgentCandidate],
    summary: dict[str, Any],
    output_dir: Path | None = None,
) -> SourceUrlAgentArtifactPaths:
    paths = run_artifact_paths(run_id, output_dir)
    paths.run_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(paths.source_url_results, RESULT_COLUMNS, [candidate.to_artifact_row() for candidate in candidates])
    _write_csv(
        paths.approved_source_urls,
        RESULT_COLUMNS,
        [candidate.to_artifact_row() for candidate in candidates if candidate.match_status == "matched"],
    )
    _write_csv(
        paths.needs_review_source_urls,
        [*RESULT_COLUMNS, *REVIEW_COLUMNS],
        [
            candidate.to_artifact_row(include_review_columns=True)
            for candidate in candidates
            if candidate.match_status == "needs_review"
        ],
    )
    _write_csv(
        paths.not_found_source_urls,
        RESULT_COLUMNS,
        [candidate.to_artifact_row() for candidate in candidates if candidate.match_status == "not_found"],
    )
    _write_csv(
        paths.errors,
        RESULT_COLUMNS,
        [candidate.to_artifact_row() for candidate in candidates if candidate.match_status == "error"],
    )
    _write_json(paths.searched_queries, _searched_queries_payload(candidates))
    suggestions = build_rule_suggestions(candidates)
    _write_json(paths.rule_suggestions, suggestions)
    _write_json(paths.source_url_run_summary, {**summary, "rule_suggestions": suggestions, "artifacts": paths.to_dict()})
    return paths


def build_summary_payload(
    *,
    run_id: str,
    mode: str,
    source: str,
    input_path: str | None,
    selected_count: int,
    candidates: list[SourceUrlAgentCandidate],
    dry_run: bool,
    apply_high_confidence: bool,
    warnings: list[str],
) -> dict[str, Any]:
    counts = Counter(candidate.match_status for candidate in candidates)
    return {
        "run_id": run_id,
        "mode": mode,
        "source": source,
        "input_path": input_path or "",
        "selected_count": selected_count,
        "candidate_count": len(candidates),
        "matched_count": int(counts["matched"]),
        "needs_review_count": int(counts["needs_review"]),
        "not_found_count": int(counts["not_found"]),
        "error_count": int(counts["error"]),
        "skipped_count": int(counts["skipped"]),
        "dry_run": dry_run,
        "apply_high_confidence": apply_high_confidence,
        "warnings": warnings,
        "by_source": _counts_by_source(candidates),
        "by_status": {key: int(value) for key, value in sorted(counts.items())},
    }


def build_rule_suggestions(candidates: list[SourceUrlAgentCandidate]) -> dict[str, Any]:
    source_counts: dict[str, Counter[str]] = {}
    missing_identifier_count = 0
    blocked_sources: Counter[str] = Counter()
    category_mismatch: Counter[str] = Counter()
    title_only: Counter[str] = Counter()
    body_only_marketplace_identifier: Counter[str] = Counter()
    for candidate in candidates:
        source_counts.setdefault(candidate.source_name, Counter())[candidate.match_status] += 1
        evidence = candidate.evidence_json
        if candidate.match_status in {"needs_review", "not_found"}:
            mpn_found = bool((evidence.get("mpn") or {}).get("found")) if isinstance(evidence.get("mpn"), dict) else False
            model_found = bool((evidence.get("model") or {}).get("found")) if isinstance(evidence.get("model"), dict) else False
            if not mpn_found and not model_found:
                missing_identifier_count += 1
        if str(evidence.get("error_code") or "") == "blocked_or_captcha":
            blocked_sources[candidate.source_name] += 1
        category = evidence.get("category")
        if isinstance(category, dict) and not category.get("compatible") and candidate.confidence_score >= 0.5:
            category_mismatch[candidate.source_name] += 1
        if bool(evidence.get("title_only")):
            title_only[candidate.source_name] += 1
        mpn = evidence.get("mpn")
        model = evidence.get("model")
        mpn_body_only = isinstance(mpn, dict) and mpn.get("found") and mpn.get("source") == "body"
        model_body_only = isinstance(model, dict) and model.get("found") and model.get("source") == "body"
        if candidate.source_type == "marketplace" and (mpn_body_only or model_body_only):
            body_only_marketplace_identifier[candidate.source_name] += 1
    suggestions = []
    if missing_identifier_count:
        suggestions.append(
            {
                "type": "missing_identifier_evidence",
                "count": missing_identifier_count,
                "suggestion": "Prefer additional model/MPN query variants and product-detail identifier extraction before relaxing scoring.",
            }
        )
    for source_name, count in blocked_sources.items():
        suggestions.append(
            {
                "type": "blocked_or_captcha",
                "source_name": source_name,
                "count": int(count),
                "suggestion": "Keep the source in error status for this run and retry later with lower rate limits.",
            }
        )
    for source_name, count in title_only.items():
        suggestions.append(
            {
                "type": "title_only_review",
                "source_name": source_name,
                "count": int(count),
                "suggestion": "Do not auto-apply title-only results; add accepted/rejected review decisions as future evidence.",
            }
        )
    for source_name, count in body_only_marketplace_identifier.items():
        suggestions.append(
            {
                "type": "body_only_marketplace_identifier",
                "source_name": source_name,
                "count": int(count),
                "suggestion": "Treat marketplace identifiers found only in page body as review evidence unless title or structured data also confirms the identifier.",
            }
        )
    return {
        "summary_by_source": {source: dict(counter) for source, counter in source_counts.items()},
        "category_mismatch_by_source": dict(category_mismatch),
        "suggestions": suggestions,
    }


def _searched_queries_payload(candidates: list[SourceUrlAgentCandidate]) -> dict[str, Any]:
    items: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = f"{candidate.product.model}|{candidate.source_name}"
        item = items.setdefault(
            key,
            {
                "model": candidate.product.model,
                "catalog_product_id": candidate.product.catalog_product_id,
                "source_name": candidate.source_name,
                "searched_queries": candidate.searched_queries,
            },
        )
        item["searched_queries"] = candidate.searched_queries
    return {"items": list(items.values())}


def _counts_by_source(candidates: list[SourceUrlAgentCandidate]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = {}
    for candidate in candidates:
        counts.setdefault(candidate.source_name, Counter())[candidate.match_status] += 1
    return {source: {key: int(value) for key, value in sorted(counter.items())} for source, counter in counts.items()}


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in columns})


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
