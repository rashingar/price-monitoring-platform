from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_ROOT = REPO_ROOT / "resources" / "templates" / "electronet"
DEFAULT_TAXONOMY_PATH = REPO_ROOT / "resources" / "mappings" / "catalog_taxonomy.json"
DEFAULT_SCHEMA_POLICY_RULES_PATH = REPO_ROOT / "resources" / "mappings" / "schema_policy_rules.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "resources" / "schemas" / "electronet_schema_library.json"
CURRENT_LIBRARY_PATH = DEFAULT_OUTPUT_PATH
LIBRARY_VERSION = "2026-04-01"
SUBCATEGORY_MATCH_POLICY_EXACT = "exact_subcategory"
SUBCATEGORY_MATCH_POLICY_LEAF_FAMILY = "leaf_family"
SUBCATEGORY_MATCH_POLICY_MIXED_FAMILY = "mixed_family"

NBSP_PATTERN = re.compile(r"[\u00A0\u202F\u2007]")
WS_PATTERN = re.compile(r"\s+")
SEPARATOR_TOKEN_PATTERN = re.compile(r"(?<=\s)[xX×χΧ](?=\s)")
SLASH_SPACING_PATTERN = re.compile(r"\s*/\s*")
QUOTE_VARIANTS = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201b": "'",
        "\u2032": "'",
        "\u2035": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201f": '"',
        "\u2033": '"',
        "\u2036": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
    }
)


@dataclass(frozen=True)
class AuthoredSection:
    name: str
    labels: list[str]


@dataclass(frozen=True)
class TemplateRecord:
    template_id: str
    authored_template_id: str
    category_label: str
    cta_map_key: str
    cta_url: str
    electronet_examples: list[str]
    binding_hint_url: str
    fingerprint: str
    authored_sections: list[AuthoredSection]
    source_template_file: str
    source_filename: str
    template_status: str


@dataclass(frozen=True)
class TaxonomyBinding:
    parent_category: str
    leaf_category: str
    sub_category: str | None
    category_path: str
    cta_url: str


def normalize_whitespace(text: str | None) -> str:
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = NBSP_PATTERN.sub(" ", text)
    text = text.translate(QUOTE_VARIANTS)
    text = WS_PATTERN.sub(" ", text)
    return text.strip()


def normalize_safe_text(text: str | None) -> str:
    normalized = normalize_whitespace(text)
    if not normalized:
        return ""
    normalized = SLASH_SPACING_PATTERN.sub(" / ", normalized)
    normalized = re.sub(r"\bin\s+(\d)\b", r"in\1", normalized, flags=re.IGNORECASE)
    normalized = SEPARATOR_TOKEN_PATTERN.sub("x", normalized)
    normalized = WS_PATTERN.sub(" ", normalized)
    return normalized.strip()


def normalize_key(text: str | None) -> str:
    normalized = normalize_safe_text(text)
    if not normalized:
        return ""
    normalized = unicodedata.normalize("NFD", normalized)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.casefold()
    normalized = re.sub(r"[^\w\s]+", " ", normalized, flags=re.UNICODE)
    normalized = WS_PATTERN.sub(" ", normalized)
    return normalized.strip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_schema_policy_rules(path: Path) -> dict[str, str]:
    payload = load_json(path)
    default_policy = normalize_whitespace(payload.get("default_policy")) or SUBCATEGORY_MATCH_POLICY_EXACT
    allowed = {
        SUBCATEGORY_MATCH_POLICY_EXACT,
        SUBCATEGORY_MATCH_POLICY_LEAF_FAMILY,
        SUBCATEGORY_MATCH_POLICY_MIXED_FAMILY,
    }
    if default_policy != SUBCATEGORY_MATCH_POLICY_EXACT:
        raise ValueError(f"schema policy default_policy must be {SUBCATEGORY_MATCH_POLICY_EXACT!r}")
    overrides_payload = payload.get("overrides")
    if not isinstance(overrides_payload, dict):
        raise ValueError("schema policy overrides must be an object")
    overrides: dict[str, str] = {}
    for template_id, raw_policy in overrides_payload.items():
        normalized_template_id = normalize_whitespace(template_id)
        normalized_policy = normalize_whitespace(raw_policy)
        if not normalized_template_id:
            raise ValueError("schema policy override keys must be non-empty template ids")
        if normalized_policy not in allowed:
            raise ValueError(f"Unsupported schema policy {raw_policy!r} for template {template_id!r}")
        overrides[normalized_template_id] = normalized_policy
    return overrides


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _sha1_id(value: Any) -> str:
    return f"sha1:{hashlib.sha1(_canonical_json(value).encode('utf-8')).hexdigest()}"


def _sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _preserve_order_unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _load_taxonomy_paths(taxonomy_path: Path) -> list[dict[str, Any]]:
    payload = load_json(taxonomy_path)
    return list(payload.get("paths", []))


def _discover_template_paths(template_root: Path) -> list[Path]:
    return sorted(path for path in template_root.glob("*.json") if path.is_file())


def _normalize_authored_sections(raw_sections: list[dict[str, Any]]) -> list[AuthoredSection]:
    sections: list[AuthoredSection] = []
    for section in raw_sections:
        name = normalize_whitespace(section.get("section") or section.get("name"))
        labels = [normalize_whitespace(label) for label in section.get("labels", []) if normalize_whitespace(label)]
        if not name or not labels:
            continue
        sections.append(AuthoredSection(name=name, labels=labels))
    return sections


def _derive_template_status(authored_sections: list[AuthoredSection]) -> str:
    if (
        len(authored_sections) == 1
        and normalize_key(authored_sections[0].name) == "todo"
        and [normalize_key(label) for label in authored_sections[0].labels] == ["needs_manual_labels"]
    ):
        return "manual_only"
    return "active"


def _derive_fingerprint(payload: dict[str, Any], authored_sections: list[AuthoredSection]) -> str:
    fingerprint = normalize_whitespace(payload.get("fingerprint"))
    if fingerprint:
        return fingerprint
    canonical_sections = [
        {"name": section.name, "labels": section.labels}
        for section in authored_sections
    ]
    return _sha256_hex(
        {
            "template_id": normalize_whitespace(payload.get("id") or payload.get("template_id")),
            "category_label": normalize_whitespace(payload.get("category_gr") or payload.get("category")),
            "cta_map_key": normalize_whitespace(payload.get("cta_map_key")),
            "cta_url": normalize_whitespace(payload.get("cta_url")),
            "sections": canonical_sections,
        }
    )


def _load_templates(template_root: Path) -> list[TemplateRecord]:
    records: list[TemplateRecord] = []
    for path in _discover_template_paths(template_root):
        payload = load_json(path)
        authored_sections = _normalize_authored_sections(list(payload.get("sections", [])))
        if not authored_sections:
            raise ValueError(f"Template {path} has no compilable sections.")
        authored_template_id = normalize_whitespace(payload.get("id") or payload.get("template_id"))
        if not authored_template_id:
            raise ValueError(f"Template {path} is missing an id/template_id.")
        category_label = normalize_whitespace(payload.get("category_gr") or payload.get("category"))
        if not category_label:
            raise ValueError(f"Template {path} is missing category_gr/category.")
        cta_map_key = normalize_whitespace(payload.get("cta_map_key")) or category_label
        cta_url = normalize_whitespace(payload.get("cta_url"))
        examples = [
            normalize_whitespace(url)
            for url in (
                payload.get("electronet_examples")
                or [payload.get("source", {}).get("electronet_url_example")]
            )
            if normalize_whitespace(url)
        ]
        template_status = _derive_template_status(authored_sections)
        records.append(
            TemplateRecord(
                template_id=path.stem,
                authored_template_id=authored_template_id,
                category_label=category_label,
                cta_map_key=cta_map_key,
                cta_url=cta_url,
                electronet_examples=examples,
                binding_hint_url=cta_url or (examples[0] if examples else ""),
                fingerprint=_derive_fingerprint(payload, authored_sections),
                authored_sections=authored_sections,
                source_template_file=_display_path(path),
                source_filename=path.name,
                template_status=template_status,
            )
        )
    return records


def _resolve_taxonomy_binding(template: TemplateRecord, taxonomy_paths: list[dict[str, Any]]) -> TaxonomyBinding:
    normalized_cta_url = normalize_whitespace(template.cta_url)
    if normalized_cta_url:
        cta_matches = [
            path
            for path in taxonomy_paths
            if normalize_whitespace(path.get("cta_url") or path.get("url")) == normalized_cta_url
        ]
        if len(cta_matches) == 1:
            matched = cta_matches[0]
            return TaxonomyBinding(
                parent_category=normalize_whitespace(matched.get("parent_category")),
                leaf_category=normalize_whitespace(matched.get("leaf_category")),
                sub_category=normalize_whitespace(matched.get("sub_category")) or None,
                category_path=normalize_whitespace(matched.get("path")),
                cta_url=normalize_whitespace(matched.get("cta_url") or matched.get("url")),
            )
        if len(cta_matches) > 1:
            matched = _pick_best_candidate_from_multiple(template, cta_matches)
            if matched is not None:
                return TaxonomyBinding(
                    parent_category=normalize_whitespace(matched.get("parent_category")),
                    leaf_category=normalize_whitespace(matched.get("leaf_category")),
                    sub_category=normalize_whitespace(matched.get("sub_category")) or None,
                    category_path=normalize_whitespace(matched.get("path")),
                    cta_url=normalize_whitespace(matched.get("cta_url") or matched.get("url")),
                )
            raise ValueError(f"Template {template.source_template_file} has ambiguous taxonomy binding for cta_url={template.cta_url!r}.")

    lookup_labels = _preserve_order_unique([template.category_label, template.cta_map_key])
    for label in lookup_labels:
        key = normalize_key(label)
        if not key:
            continue
        sub_matches = [
            path
            for path in taxonomy_paths
            if normalize_key(path.get("sub_category")) == key
        ]
        if len(sub_matches) == 1:
            matched = sub_matches[0]
            return TaxonomyBinding(
                parent_category=normalize_whitespace(matched.get("parent_category")),
                leaf_category=normalize_whitespace(matched.get("leaf_category")),
                sub_category=normalize_whitespace(matched.get("sub_category")) or None,
                category_path=normalize_whitespace(matched.get("path")),
                cta_url=normalize_whitespace(matched.get("cta_url") or matched.get("url")),
            )
        if len(sub_matches) > 1:
            matched = _pick_best_candidate_from_multiple(template, sub_matches)
            if matched is not None:
                return TaxonomyBinding(
                    parent_category=normalize_whitespace(matched.get("parent_category")),
                    leaf_category=normalize_whitespace(matched.get("leaf_category")),
                    sub_category=normalize_whitespace(matched.get("sub_category")) or None,
                    category_path=normalize_whitespace(matched.get("path")),
                    cta_url=normalize_whitespace(matched.get("cta_url") or matched.get("url")),
                )
        leaf_matches = [
            path
            for path in taxonomy_paths
            if normalize_key(path.get("leaf_category")) == key and not normalize_whitespace(path.get("sub_category"))
        ]
        if len(leaf_matches) == 1:
            matched = leaf_matches[0]
            return TaxonomyBinding(
                parent_category=normalize_whitespace(matched.get("parent_category")),
                leaf_category=normalize_whitespace(matched.get("leaf_category")),
                sub_category=None,
                category_path=normalize_whitespace(matched.get("path")),
                cta_url=normalize_whitespace(matched.get("cta_url") or matched.get("url")),
            )
        if len(leaf_matches) > 1:
            matched = _pick_best_candidate_from_multiple(template, leaf_matches)
            if matched is not None:
                return TaxonomyBinding(
                    parent_category=normalize_whitespace(matched.get("parent_category")),
                    leaf_category=normalize_whitespace(matched.get("leaf_category")),
                    sub_category=None,
                    category_path=normalize_whitespace(matched.get("path")),
                    cta_url=normalize_whitespace(matched.get("cta_url") or matched.get("url")),
                )

    raise ValueError(
        f"Template {template.source_template_file} could not be bound to a unique taxonomy path "
        f"from category={template.category_label!r} cta_map_key={template.cta_map_key!r} cta_url={template.cta_url!r}."
    )


def _candidate_url_overlap_score(binding_hint_url: str, candidate: dict[str, Any]) -> int:
    if not binding_hint_url:
        return 0
    hint_tokens = set(normalize_key(urlparse(binding_hint_url).path).split())
    candidate_tokens = set(normalize_key(urlparse(normalize_whitespace(candidate.get("cta_url") or candidate.get("url"))).path).split())
    if not hint_tokens or not candidate_tokens:
        return 0
    return len(hint_tokens & candidate_tokens)


def _pick_best_candidate_from_multiple(
    template: TemplateRecord,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    template_identity_key = normalize_key(
        " ".join(
            [
                template.template_id,
                template.category_label,
                template.cta_map_key,
                template.source_filename,
            ]
        )
    )
    template_identity_tokens = set(template_identity_key.split())
    template_is_built_in = "entoixiz" in template_identity_key
    scored = [
        (
            1
            if ("entoixiz" in normalize_key(" ".join(
                [
                    normalize_whitespace(candidate.get("parent_category")),
                    normalize_whitespace(candidate.get("leaf_category")),
                    normalize_whitespace(candidate.get("sub_category")),
                    normalize_whitespace(candidate.get("path")),
                    normalize_whitespace(candidate.get("cta_url") or candidate.get("url")),
                ]
            ))) == template_is_built_in
            else 0,
            _candidate_url_overlap_score(template.binding_hint_url, candidate),
            len(
                template_identity_tokens
                & set(
                    normalize_key(
                        " ".join(
                            [
                                normalize_whitespace(candidate.get("parent_category")),
                                normalize_whitespace(candidate.get("leaf_category")),
                                normalize_whitespace(candidate.get("sub_category")),
                                normalize_whitespace(candidate.get("path")),
                            ]
                        )
                    ).split()
                )
            ),
            index,
            candidate,
        )
        for index, candidate in enumerate(candidates)
    ]
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    best_signature = scored[0][:3]
    if best_signature == (0, 0, 0):
        return None
    best_candidates = [candidate for score_a, score_b, score_c, _, candidate in scored if (score_a, score_b, score_c) == best_signature]
    return best_candidates[0] if len(best_candidates) == 1 else None


def _compiled_sections_from_authored(template: TemplateRecord) -> list[dict[str, Any]]:
    return [
        {
            "title": section.name,
            "labels": [label for label in section.labels if label],
        }
        for section in template.authored_sections
    ]


def _subcategory_match_policy(template: TemplateRecord, policy_overrides: dict[str, str]) -> str:
    return policy_overrides.get(template.template_id, SUBCATEGORY_MATCH_POLICY_EXACT)


def _derive_schema_id(
    template: TemplateRecord,
    taxonomy_binding: TaxonomyBinding,
    compiled_sections: list[dict[str, Any]],
) -> str:
    return _sha1_id(
        {
            "source_system": "electronet",
            "template_id": template.template_id,
            "authored_template_id": template.authored_template_id,
            "category_gr": template.category_label,
            "category_path": taxonomy_binding.category_path,
            "parent_category": taxonomy_binding.parent_category,
            "leaf_category": taxonomy_binding.leaf_category,
            "sub_category": taxonomy_binding.sub_category,
            "cta_map_key": template.cta_map_key,
            "cta_url": taxonomy_binding.cta_url or template.cta_url,
            "template_status": template.template_status,
            "sections": compiled_sections,
        }
    )


def _sentinel_for_sections(sections: list[dict[str, Any]]) -> dict[str, str]:
    if not sections:
        return {"last_section": "", "last_label": ""}
    last_section = sections[-1]
    labels = [normalize_whitespace(label) for label in last_section.get("labels", []) if normalize_whitespace(label)]
    return {
        "last_section": normalize_whitespace(last_section.get("title")),
        "last_label": labels[-1] if labels else "",
    }


def _ordered_exact_labels(template: TemplateRecord) -> list[str]:
    labels: list[str] = []
    for section in template.authored_sections:
        labels.extend(section.labels)
    return _preserve_order_unique(labels)


def _ordered_normalized_labels(template: TemplateRecord) -> list[str]:
    return _preserve_order_unique([normalize_safe_text(label) for label in _ordered_exact_labels(template)])


def _ordered_section_names_exact(template: TemplateRecord) -> list[str]:
    return [section.name for section in template.authored_sections]


def _ordered_section_names_normalized(template: TemplateRecord) -> list[str]:
    return _preserve_order_unique([normalize_safe_text(section.name) for section in template.authored_sections])


def _ordered_section_label_pairs_normalized(template: TemplateRecord) -> list[str]:
    pairs: list[str] = []
    for section in template.authored_sections:
        normalized_section = normalize_safe_text(section.name)
        for label in section.labels:
            pairs.append(f"{normalized_section} || {normalize_safe_text(label)}")
    return _preserve_order_unique(pairs)


def _compute_match_metadata(entries: list[dict[str, Any]]) -> None:
    active_entries_by_category_path: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if entry["template_status"] != "active":
            continue
        active_entries_by_category_path.setdefault(entry["category_path"], []).append(entry)

    for category_entries in active_entries_by_category_path.values():
        ordered_entries = sorted(category_entries, key=lambda item: item["template_id"])
        for entry in ordered_entries:
            siblings = [candidate for candidate in ordered_entries if candidate["template_id"] != entry["template_id"]]
            entry["sibling_template_ids"] = [candidate["template_id"] for candidate in siblings]
            entry["match_mode"] = "direct_single" if not siblings else "category_pool"

            own_labels = list(entry["label_set_normalized"])
            sibling_labels = _preserve_order_unique(
                [
                    label
                    for sibling in siblings
                    for label in sibling["label_set_normalized"]
                ]
            )
            unique_labels = [label for label in own_labels if label and label not in sibling_labels]
            sibling_unique_labels = [
                label
                for label in sibling_labels
                if label and label not in own_labels
            ]

            entry["discriminator_labels"] = unique_labels
            entry["required_labels_any"] = unique_labels[:3] if unique_labels else own_labels[:3]
            entry["required_labels_all"] = unique_labels[:1] if unique_labels else []
            entry["forbidden_labels"] = sibling_unique_labels
            entry["min_section_overlap"] = min(3, max(1, math.ceil(len(entry["section_names_exact"]) * 0.5)))
            entry["min_label_overlap"] = min(8, max(1, math.ceil(len(own_labels) * 0.2)))

    for entry in entries:
        if entry["template_status"] == "active":
            continue
        entry["match_mode"] = "manual_only"
        entry["sibling_template_ids"] = []
        entry["discriminator_labels"] = []
        entry["required_labels_any"] = []
        entry["required_labels_all"] = []
        entry["forbidden_labels"] = []
        entry["min_section_overlap"] = 0
        entry["min_label_overlap"] = 0


def build_library_payload(
    template_root: Path = DEFAULT_TEMPLATE_ROOT,
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH,
    schema_policy_rules_path: Path = DEFAULT_SCHEMA_POLICY_RULES_PATH,
    existing_library_path: Path | None = CURRENT_LIBRARY_PATH,
) -> dict[str, Any]:
    templates = _load_templates(template_root)
    taxonomy_paths = _load_taxonomy_paths(taxonomy_path)
    schema_policy_overrides = _load_schema_policy_rules(schema_policy_rules_path)
    # Kept for call-site compatibility only. Compiled schema content must not inherit
    # structure or ids from any prior generated artifact.
    _ = existing_library_path

    compiled_entries: list[dict[str, Any]] = []
    for template in templates:
        taxonomy_binding = _resolve_taxonomy_binding(template, taxonomy_paths)
        compiled_sections = _compiled_sections_from_authored(template)
        subcategory_match_policy = _subcategory_match_policy(template, schema_policy_overrides)
        n_rows_total = sum(len(section.get("labels", [])) for section in compiled_sections)
        schema_id = _derive_schema_id(template, taxonomy_binding, compiled_sections)

        compiled_entries.append(
            {
                "schema_id": schema_id,
                "source_system": "electronet",
                "template_id": template.template_id,
                "authored_template_id": template.authored_template_id,
                "category_gr": template.category_label,
                "category_path": taxonomy_binding.category_path,
                "parent_category": taxonomy_binding.parent_category,
                "leaf_category": taxonomy_binding.leaf_category,
                "sub_category": taxonomy_binding.sub_category,
                "subcategory_match_policy": subcategory_match_policy,
                "cta_map_key": template.cta_map_key,
                "cta_url": taxonomy_binding.cta_url or template.cta_url,
                "template_status": template.template_status,
                "match_mode": "",
                "section_names_exact": _ordered_section_names_exact(template),
                "section_names_normalized": _ordered_section_names_normalized(template),
                "label_set_exact": _ordered_exact_labels(template),
                "label_set_normalized": _ordered_normalized_labels(template),
                "section_label_pairs_normalized": _ordered_section_label_pairs_normalized(template),
                "discriminator_labels": [],
                "required_labels_any": [],
                "required_labels_all": [],
                "forbidden_labels": [],
                "min_section_overlap": 0,
                "min_label_overlap": 0,
                "sibling_template_ids": [],
                "fingerprint": template.fingerprint,
                "source_template_file": template.source_template_file,
                "electronet_examples": list(template.electronet_examples),
                "n_sections": len(compiled_sections),
                "n_rows_total": n_rows_total,
                "sections": compiled_sections,
                "sentinel": _sentinel_for_sections(compiled_sections),
                "source_files": [template.source_filename],
            }
        )

    _compute_match_metadata(compiled_entries)
    compiled_entries.sort(
        key=lambda item: (
            item["category_path"],
            item["template_status"],
            item["template_id"],
        )
    )

    compile_fingerprint = _sha256_hex(
        [
            {
                "template_id": entry["template_id"],
                "schema_id": entry["schema_id"],
                "fingerprint": entry["fingerprint"],
                "category_path": entry["category_path"],
                "subcategory_match_policy": entry["subcategory_match_policy"],
                "template_status": entry["template_status"],
                "match_mode": entry["match_mode"],
            }
            for entry in compiled_entries
        ]
    )

    return {
        "version": LIBRARY_VERSION,
        "source_system": "electronet",
        "template_root": _display_path(template_root),
        "compile_fingerprint": compile_fingerprint,
        "schemas": compiled_entries,
    }


def write_library_payload(payload: dict[str, Any], output_path: Path = DEFAULT_OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=output_path.parent, suffix=".tmp") as handle:
        handle.write(rendered)
        temp_path = Path(handle.name)
    temp_path.replace(output_path)


def main() -> None:
    payload = build_library_payload()
    write_library_payload(payload, DEFAULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()
