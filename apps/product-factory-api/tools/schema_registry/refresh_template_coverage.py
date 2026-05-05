from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.schema_registry.build_electronet_schema_library import (
    DEFAULT_TAXONOMY_PATH,
    DEFAULT_TEMPLATE_ROOT,
    REPO_ROOT,
    TaxonomyBinding,
    _load_templates,
    _resolve_taxonomy_binding,
    load_json,
    normalize_whitespace,
)


DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs" / "audits" / "electronet_template_coverage.md"
DEFAULT_FILTER_MAP_PATH = REPO_ROOT / "resources" / "mappings" / "filter_map.json"


@dataclass(frozen=True)
class ExpectedCategory:
    key: str
    label: str
    parent_category: str
    leaf_category: str
    sub_category: str | None
    category_path: str
    cta_url: str


@dataclass(frozen=True)
class ObservedTemplate:
    template_id: str
    template_file: str
    category_path: str
    template_status: str
    examples: tuple[str, ...]


def _display_template_file(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def _expected_label(parent_category: str, leaf_category: str, sub_category: str | None) -> str:
    return sub_category or leaf_category


def _coverage_label_context(expected: ExpectedCategory) -> str:
    return f"{expected.parent_category} > {expected.leaf_category}"


def _render_coverage_label(expected: ExpectedCategory, counts: Counter[str]) -> str:
    if counts[expected.label] <= 1:
        return expected.label
    return f"{expected.label} [{_coverage_label_context(expected)}]"


def _rendered_coverage_labels(expected_categories: list[ExpectedCategory]) -> dict[str, str]:
    label_counts = Counter(expected.label for expected in expected_categories)
    return {
        expected.category_path: _render_coverage_label(expected, label_counts)
        for expected in expected_categories
    }


def load_expected_categories(
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH,
    filter_map_path: Path = DEFAULT_FILTER_MAP_PATH,
) -> list[ExpectedCategory]:
    taxonomy_payload = load_json(taxonomy_path)
    if not isinstance(taxonomy_payload, dict) or not isinstance(taxonomy_payload.get("paths"), list):
        raise ValueError(f"Taxonomy payload is malformed: {taxonomy_path}")

    filter_payload = load_json(filter_map_path)
    if not isinstance(filter_payload, dict):
        raise ValueError(f"Filter map payload is malformed: {filter_map_path}")

    raw_paths = taxonomy_payload["paths"]
    expected_categories: list[ExpectedCategory] = []
    seen_paths: set[str] = set()
    for item in sorted(
        raw_paths,
        key=lambda row: (
            normalize_whitespace(row.get("path")),
            normalize_whitespace(row.get("parent_category")),
            normalize_whitespace(row.get("leaf_category")),
            normalize_whitespace(row.get("sub_category")),
        ),
    ):
        parent_category = normalize_whitespace(item.get("parent_category"))
        leaf_category = normalize_whitespace(item.get("leaf_category"))
        sub_category = normalize_whitespace(item.get("sub_category")) or None
        category_path = normalize_whitespace(item.get("path"))
        cta_url = normalize_whitespace(item.get("cta_url") or item.get("url"))
        if not parent_category or not leaf_category or not category_path:
            raise ValueError(f"Taxonomy path is missing required fields: {item!r}")
        if category_path in seen_paths:
            raise ValueError(f"Duplicate taxonomy path detected: {category_path}")
        seen_paths.add(category_path)
        label = _expected_label(parent_category, leaf_category, sub_category)
        expected_categories.append(
            ExpectedCategory(
                key=category_path,
                label=label,
                parent_category=parent_category,
                leaf_category=leaf_category,
                sub_category=sub_category,
                category_path=category_path,
                cta_url=cta_url,
            )
        )

    return expected_categories


def load_observed_templates(
    template_root: Path = DEFAULT_TEMPLATE_ROOT,
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH,
) -> tuple[list[ObservedTemplate], list[ObservedTemplate]]:
    taxonomy_payload = load_json(taxonomy_path)
    taxonomy_paths = taxonomy_payload.get("paths", [])
    if not isinstance(taxonomy_paths, list):
        raise ValueError(f"Taxonomy payload is malformed: {taxonomy_path}")

    observed: list[ObservedTemplate] = []
    orphans: list[ObservedTemplate] = []

    for template in _load_templates(template_root):
        try:
            binding = _resolve_taxonomy_binding(template, taxonomy_paths)
            observed.append(_observed_from_binding(template.template_id, template.source_template_file, template.template_status, template.electronet_examples, binding))
        except ValueError:
            orphans.append(
                ObservedTemplate(
                    template_id=template.template_id,
                    template_file=template.source_template_file,
                    category_path="",
                    template_status="review",
                    examples=tuple(template.electronet_examples),
                )
            )

    observed.sort(key=lambda item: (item.category_path, item.template_status, item.template_file))
    orphans.sort(key=lambda item: item.template_file)
    return observed, orphans


def _observed_from_binding(
    template_id: str,
    template_file: str,
    template_status: str,
    examples: list[str],
    binding: TaxonomyBinding,
) -> ObservedTemplate:
    return ObservedTemplate(
        template_id=template_id,
        template_file=Path(template_file).name,
        category_path=binding.category_path,
        template_status=template_status,
        examples=tuple(normalize_whitespace(url) for url in examples if normalize_whitespace(url)),
    )


def _status_for_templates(templates: list[ObservedTemplate]) -> str:
    if not templates:
        return "MISSING"
    if len(templates) > 1:
        return "REVIEW"
    if templates[0].template_status == "manual_only":
        return "NEEDS_MANUAL"
    return "OK"


def _join_examples(templates: list[ObservedTemplate]) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for template in templates:
        for example in template.examples:
            key = example.casefold()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(example)
    return "<br>".join(ordered) if ordered else "-"


def assess_template_coverage(
    expected_categories: list[ExpectedCategory],
    observed_templates: list[ObservedTemplate],
    orphan_templates: list[ObservedTemplate] | None = None,
) -> list[dict[str, str]]:
    orphan_templates = orphan_templates or []
    observed_by_path: defaultdict[str, list[ObservedTemplate]] = defaultdict(list)
    rendered_labels = _rendered_coverage_labels(expected_categories)
    for template in observed_templates:
        observed_by_path[template.category_path].append(template)

    rows: list[dict[str, str]] = []
    for expected in expected_categories:
        templates = sorted(
            observed_by_path.get(expected.category_path, []),
            key=lambda item: (item.template_status, item.template_file, item.template_id),
        )
        rows.append(
            {
                "CTA Leaf Category": rendered_labels[expected.category_path],
                "File": "<br>".join(template.template_file for template in templates) if templates else "-",
                "Status": _status_for_templates(templates),
                "Electronet Examples": _join_examples(templates),
                "_sort_path": expected.category_path,
            }
        )

    for orphan in orphan_templates:
        rows.append(
            {
                "CTA Leaf Category": f"{orphan.template_id} [UNBOUND]",
                "File": orphan.template_file,
                "Status": "REVIEW",
                "Electronet Examples": _join_examples([orphan]),
                "_sort_path": f"zzzz::{orphan.template_file}",
            }
        )

    rows.sort(key=lambda row: (row["_sort_path"], row["CTA Leaf Category"], row["File"]))
    return rows


def build_markdown_table(rows: list[dict[str, str]]) -> str:
    lines = [
        "| CTA Leaf Category | File | Status | Electronet Examples |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['CTA Leaf Category']} | {row['File']} | {row['Status']} | {row['Electronet Examples']} |"
        )
    return "\n".join(lines) + "\n"


def write_report(markdown: str, output_path: Path = DEFAULT_OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")


def main() -> None:
    expected_categories = load_expected_categories()
    observed_templates, orphan_templates = load_observed_templates()
    rows = assess_template_coverage(expected_categories, observed_templates, orphan_templates)
    write_report(build_markdown_table(rows), DEFAULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()
