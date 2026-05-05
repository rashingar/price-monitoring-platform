from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tools.schema_registry.build_electronet_schema_library import (
    DEFAULT_TEMPLATE_ROOT,
    REPO_ROOT,
    load_json,
    normalize_key,
    normalize_whitespace,
)


DEFAULT_SCHEMA_PATH = REPO_ROOT / "resources" / "templates" / "schema_template.schema.json"
SUPPORTED_EXAMPLE_HOSTS = {"www.electronet.gr", "electronet.gr", "www.etranoulis.gr", "etranoulis.gr"}


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str


@dataclass(frozen=True)
class TemplateContext:
    path: Path
    stem: str
    authored_id: str
    logical_category: str
    logical_cta_map_key: str
    examples: tuple[str, ...]
    sections: tuple[dict[str, Any], ...]


def discover_templates(template_root: Path) -> list[Path]:
    return sorted(path for path in template_root.glob("*.json") if path.is_file())


def load_schema(schema_path: Path) -> dict[str, Any]:
    payload = load_json(schema_path)
    if not isinstance(payload, dict) or "oneOf" not in payload:
        raise ValueError(f"Shared schema file is malformed: {schema_path}")
    return payload


def _issue(path: str, message: str) -> ValidationIssue:
    return ValidationIssue(path=path, message=message)


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    return True


def _validate_schema_node(value: Any, schema_node: dict[str, Any], path: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if "oneOf" in schema_node:
        branch_results = [_validate_schema_node(value, branch, path) for branch in schema_node["oneOf"]]
        if not any(not branch for branch in branch_results):
            issues.append(_issue(path, "does not match any supported template schema shape"))
        return issues

    expected_type = schema_node.get("type")
    if isinstance(expected_type, str) and not _matches_type(value, expected_type):
        return [_issue(path, f"expected {expected_type}, got {_type_name(value)}")]

    if expected_type == "object":
        properties = schema_node.get("properties", {})
        required = schema_node.get("required", [])
        assert isinstance(value, dict)
        for key in required:
            if key not in value:
                issues.append(_issue(path, f"missing required key {key!r}"))
        for key, child_schema in properties.items():
            if key in value:
                issues.extend(_validate_schema_node(value[key], child_schema, f"{path}.{key}" if path else key))
        return issues

    if expected_type == "array":
        assert isinstance(value, list)
        min_items = schema_node.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            issues.append(_issue(path, f"must contain at least {min_items} item(s)"))
        item_schema = schema_node.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                issues.extend(_validate_schema_node(item, item_schema, f"{path}[{index}]"))
        return issues

    return issues


def validate_json_schema(payload: dict[str, Any], schema: dict[str, Any]) -> list[ValidationIssue]:
    return _validate_schema_node(payload, schema, "")


def _schema_normalized_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "id" in payload or "category_gr" in payload or any("section" in item for item in payload.get("sections", []) if isinstance(item, dict)):
        normalized_sections = []
        for section in payload.get("sections", []):
            if not isinstance(section, dict):
                normalized_sections.append(section)
                continue
            normalized_sections.append(
                {
                    **section,
                    "section": section.get("section", section.get("name")),
                }
            )
        return {
            **payload,
            "cta_map_key": payload.get("cta_map_key", payload.get("category_gr", payload.get("category", ""))),
            "cta_url": payload.get("cta_url", ""),
            "electronet_examples": payload.get("electronet_examples", []),
            "sections": normalized_sections,
        }
    return payload


def _authored_id(payload: dict[str, Any]) -> str:
    return normalize_whitespace(payload.get("id") or payload.get("template_id"))


def _logical_category(payload: dict[str, Any]) -> str:
    return normalize_whitespace(payload.get("category_gr") or payload.get("category"))


def _logical_cta_map_key(payload: dict[str, Any]) -> str:
    return normalize_whitespace(payload.get("cta_map_key") or _logical_category(payload))


def _iter_examples(payload: dict[str, Any]) -> tuple[str, ...]:
    if "electronet_examples" in payload:
        raw_examples = payload.get("electronet_examples") or []
        if not isinstance(raw_examples, list):
            return ()
        return tuple(normalize_whitespace(item) for item in raw_examples if normalize_whitespace(item))

    source = payload.get("source")
    if isinstance(source, dict):
        example = normalize_whitespace(source.get("electronet_url_example"))
        if example:
            return (example,)
    return ()


def _iter_sections(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    raw_sections = payload.get("sections")
    if not isinstance(raw_sections, list):
        return ()
    return tuple(section for section in raw_sections if isinstance(section, dict))


def _build_context(path: Path, payload: dict[str, Any]) -> TemplateContext:
    return TemplateContext(
        path=path,
        stem=path.stem,
        authored_id=_authored_id(payload),
        logical_category=_logical_category(payload),
        logical_cta_map_key=_logical_cta_map_key(payload),
        examples=_iter_examples(payload),
        sections=_iter_sections(payload),
    )


def _is_filename_consistent(stem: str, authored_id: str) -> bool:
    if not stem or not authored_id:
        return False
    if authored_id == stem:
        return True
    return authored_id.startswith(f"{stem}_")


def _validate_url(url: str, field_path: str) -> list[ValidationIssue]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return [_issue(field_path, f"invalid URL {url!r}")]
    host = parsed.netloc.casefold()
    if host not in SUPPORTED_EXAMPLE_HOSTS:
        return [_issue(field_path, f"unexpected host {parsed.netloc!r}")]
    return []


def _normalized_section_name(section: dict[str, Any]) -> str:
    return normalize_whitespace(section.get("section") or section.get("name"))


def _labels_for_section(section: dict[str, Any]) -> list[str]:
    raw_labels = section.get("labels")
    if not isinstance(raw_labels, list):
        return []
    return [str(label) for label in raw_labels]


def validate_repo_invariants(context: TemplateContext, payload: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not context.authored_id:
        issues.append(_issue("id", "logical template id is blank"))
    elif not _is_filename_consistent(context.stem, context.authored_id):
        issues.append(
            _issue(
                "id",
                f"filename stem {context.stem!r} is inconsistent with logical template id {context.authored_id!r}",
            )
        )

    if not context.logical_category:
        issues.append(_issue("category_gr", "logical category is blank"))
    if not context.logical_cta_map_key:
        issues.append(_issue("cta_map_key", "logical cta_map_key is blank"))

    raw_cta_url = payload.get("cta_url")
    if raw_cta_url is not None and not normalize_whitespace(raw_cta_url):
        issues.append(_issue("cta_url", "cta_url must not be blank when present"))
    elif normalize_whitespace(raw_cta_url):
        issues.extend(_validate_url(normalize_whitespace(raw_cta_url), "cta_url"))

    if not context.sections:
        issues.append(_issue("sections", "template must contain at least one section"))

    seen_sections: set[str] = set()
    for index, section in enumerate(context.sections):
        section_path = f"sections[{index}]"
        section_name = _normalized_section_name(section)
        if not section_name:
            issues.append(_issue(f"{section_path}.section", "section name is blank"))
        elif normalize_key(section_name) in seen_sections:
            issues.append(_issue(f"{section_path}.section", f"duplicate section name {section_name!r}"))
        else:
            seen_sections.add(normalize_key(section_name))

        labels = _labels_for_section(section)
        if not labels:
            issues.append(_issue(f"{section_path}.labels", "section must contain at least one label"))
            continue

        seen_labels: set[str] = set()
        non_empty_labels = 0
        for label_index, raw_label in enumerate(labels):
            label_path = f"{section_path}.labels[{label_index}]"
            trimmed = normalize_whitespace(raw_label)
            if not trimmed:
                issues.append(_issue(label_path, "label must be non-empty after trim"))
                continue
            non_empty_labels += 1
            normalized_label = normalize_key(trimmed)
            if normalized_label in seen_labels:
                issues.append(_issue(label_path, f"duplicate label {trimmed!r} within section"))
            else:
                seen_labels.add(normalized_label)
        if non_empty_labels == 0:
            issues.append(_issue(f"{section_path}.labels", "section must contain at least one non-empty label"))

    seen_examples: set[str] = set()
    for index, example in enumerate(context.examples):
        example_path = f"electronet_examples[{index}]"
        issues.extend(_validate_url(example, example_path))
        normalized_example = example.casefold()
        if normalized_example in seen_examples:
            issues.append(_issue(example_path, f"duplicate example URL {example!r}"))
        else:
            seen_examples.add(normalized_example)

    return issues


def validate_template_file(path: Path, schema: dict[str, Any]) -> tuple[TemplateContext, list[ValidationIssue]]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        return (
            TemplateContext(path=path, stem=path.stem, authored_id="", logical_category="", logical_cta_map_key="", examples=(), sections=()),
            [_issue("", "template root must be a JSON object")],
        )

    context = _build_context(path, payload)
    issues = validate_json_schema(_schema_normalized_payload(payload), schema)
    issues.extend(validate_repo_invariants(context, payload))
    return context, sorted(issues, key=lambda item: (item.path, item.message))


def validate_all_templates(
    template_root: Path = DEFAULT_TEMPLATE_ROOT,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> tuple[list[tuple[TemplateContext, list[ValidationIssue]]], list[str]]:
    schema = load_schema(schema_path)
    template_paths = discover_templates(template_root)
    if not template_paths:
        raise ValueError(f"No template JSON files found under {template_root}")

    results = [validate_template_file(path, schema) for path in template_paths]

    authored_ids: defaultdict[str, list[str]] = defaultdict(list)
    for context, _ in results:
        if context.authored_id:
            authored_ids[context.authored_id].append(_display_path(context.path))

    duplicate_messages: list[str] = []
    for authored_id, paths in sorted(authored_ids.items()):
        if len(paths) > 1:
            duplicate_messages.append(
                f"duplicate logical template id {authored_id!r} in {', '.join(paths)}"
            )

    return results, duplicate_messages


def render_report(
    results: list[tuple[TemplateContext, list[ValidationIssue]]],
    duplicate_messages: list[str],
) -> str:
    lines: list[str] = []
    total_issues = sum(len(issues) for _, issues in results) + len(duplicate_messages)
    invalid_files = sum(1 for _, issues in results if issues)

    for context, issues in results:
        status = "ERROR" if issues else "OK"
        label = context.authored_id or "-"
        lines.append(f"[{status}] {_display_path(context.path)} | template_id={label} | category={context.logical_category or '-'}")
        for issue in issues:
            prefix = issue.path or "$"
            lines.append(f"  - {prefix}: {issue.message}")

    if duplicate_messages:
        lines.append("[ERROR] cross-file invariants")
        for message in duplicate_messages:
            lines.append(f"  - {message}")

    lines.append(
        f"Summary: checked={len(results)} valid={len(results) - invalid_files} invalid={invalid_files} issues={total_issues}"
    )
    return "\n".join(lines)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    results, duplicate_messages = validate_all_templates()
    report = render_report(results, duplicate_messages)
    print(report)
    has_errors = any(issues for _, issues in results) or bool(duplicate_messages)
    if has_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
