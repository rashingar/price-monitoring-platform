"""Run analysis helpers for Source URL Agent Mode."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ecommerce.source_url_agent.artifacts import (
    SOURCE_URL_AGENT_RUNS_DIR,
    build_rule_suggestions,
)


def analyze_run_artifacts(
    run_id: str, *, output_dir: Path | None = None
) -> dict[str, Any]:
    root = output_dir or SOURCE_URL_AGENT_RUNS_DIR
    run_dir = Path(root) / _safe_run_id(run_id)
    results_path = run_dir / "source_url_results.csv"
    if not results_path.exists():
        raise FileNotFoundError(f"Source URL agent results not found: {results_path}")
    rows = _read_csv(results_path)
    by_status = Counter(row.get("match_status", "") for row in rows)
    by_source = _counter_by(rows, "source_name", "match_status")
    repeated_errors = _counter_by(
        rows, "source_name", "match_method", status_filter="error"
    )
    title_only_count = sum(
        1 for row in rows if "Title-only matches" in (row.get("notes") or "")
    )
    missing_identifier_count = sum(
        1
        for row in rows
        if row.get("match_status") in {"needs_review", "not_found"}
        and row.get("evidence_mpn") == "missing"
        and row.get("evidence_model") == "missing"
    )
    payload = {
        "run_id": run_id,
        "candidate_count": len(rows),
        "by_status": dict(by_status),
        "by_source": {source: dict(counter) for source, counter in by_source.items()},
        "repeated_errors": {
            source: dict(counter) for source, counter in repeated_errors.items()
        },
        "title_only_count": title_only_count,
        "missing_identifier_count": missing_identifier_count,
        "recommendations": _recommendations(
            by_status, repeated_errors, title_only_count, missing_identifier_count
        ),
    }
    output_path = run_dir / "analysis_summary.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _counter_by(
    rows: list[dict[str, str]],
    group_key: str,
    value_key: str,
    *,
    status_filter: str | None = None,
) -> dict[str, Counter[str]]:
    grouped: dict[str, Counter[str]] = {}
    for row in rows:
        if status_filter is not None and row.get("match_status") != status_filter:
            continue
        group = row.get(group_key) or "unknown"
        value = row.get(value_key) or "unknown"
        grouped.setdefault(group, Counter())[value] += 1
    return grouped


def _recommendations(
    by_status: Counter[str],
    repeated_errors: dict[str, Counter[str]],
    title_only_count: int,
    missing_identifier_count: int,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    if title_only_count:
        recommendations.append(
            {
                "type": "title_only_review",
                "count": title_only_count,
                "message": "Keep title-only matches in review; accepted review rows can inform safer generic identifier extraction.",
            }
        )
    if missing_identifier_count:
        recommendations.append(
            {
                "type": "missing_identifiers",
                "count": missing_identifier_count,
                "message": "Inspect pages for source-specific model labels before relaxing confidence thresholds.",
            }
        )
    for source, counter in repeated_errors.items():
        blocked_count = counter.get("blocked_or_captcha", 0)
        if blocked_count:
            recommendations.append(
                {
                    "type": "blocked_or_captcha",
                    "source_name": source,
                    "count": int(blocked_count),
                    "message": "Retry with a smaller batch or larger rate limit; do not treat blocking as not_found.",
                }
            )
    if by_status.get("not_found", 0):
        recommendations.append(
            {
                "type": "not_found",
                "count": int(by_status["not_found"]),
                "message": "Review query generation and product URL patterns for sources with repeated not_found rows.",
            }
        )
    return recommendations


def _safe_run_id(run_id: str) -> str:
    value = str(run_id or "").strip()
    if not value or "/" in value or "\\" in value or value in {".", ".."}:
        raise ValueError("Invalid run_id.")
    return value
