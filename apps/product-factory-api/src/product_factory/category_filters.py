from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
import unicodedata
from typing import Any

from .description_enrichment import build_description_spec_items
from .models import SourceProductData, SpecItem, SpecSection, TaxonomyResolution
from .normalize import (
    candidate_label_keys,
    label_aliases_for,
    normalize_for_match,
    normalize_label_key,
    nullify_dash_values,
    repair_mojibake_text,
)
from .repo_paths import FILTER_MAP_PATH, category_filter_review_path_for_model_root
from .utils import read_json


@dataclass(slots=True)
class CategoryFilterValueResolution:
    category_id: str
    taxonomy_path: str
    group_id: str
    group_name: str
    required: bool
    group_status: str
    allowed_values: list[str] = field(default_factory=list)
    resolved_value: str = ""
    value_status: str = ""
    resolved_from: str = ""
    emitted: bool = False
    missing_required: bool = False
    outside_allowed: bool = False
    deprecated_value: bool = False
    inactive_group: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CategoryFilterResolution:
    category_id: str = ""
    taxonomy_path: str = ""
    filter_category_found: bool = False
    available_groups: list[str] = field(default_factory=list)
    emitted_columns: list[str] = field(default_factory=list)
    missing_required_groups: list[str] = field(default_factory=list)
    unresolved_optional_groups: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    groups: list[CategoryFilterValueResolution] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category_id": self.category_id,
            "taxonomy_path": self.taxonomy_path,
            "filter_category_found": self.filter_category_found,
            "available_groups": self.available_groups,
            "emitted_columns": self.emitted_columns,
            "missing_required_groups": self.missing_required_groups,
            "unresolved_optional_groups": self.unresolved_optional_groups,
            "errors": self.errors,
            "warnings": self.warnings,
            "groups": [group.to_dict() for group in self.groups],
        }


def load_filter_map(path: str | Path = FILTER_MAP_PATH) -> dict[str, Any]:
    return read_json(path)


def canonical_taxonomy_path(taxonomy: TaxonomyResolution) -> str:
    if taxonomy.taxonomy_path:
        return " > ".join(
            segment.strip()
            for segment in taxonomy.taxonomy_path.split(">")
            if segment.strip()
        )
    segments = [
        taxonomy.parent_category,
        taxonomy.leaf_category,
        taxonomy.sub_category or "",
    ]
    return " > ".join(
        str(segment).strip() for segment in segments if str(segment or "").strip()
    )


def find_filter_category(
    filter_map: dict[str, Any],
    *,
    category_id: str = "",
    taxonomy_path: str = "",
) -> dict[str, Any] | None:
    if category_id:
        by_id = filter_map.get("by_category_id", {})
        if isinstance(by_id, dict) and isinstance(by_id.get(category_id), dict):
            return by_id[category_id]
        for category in filter_map.get("subcategories", []):
            if (
                isinstance(category, dict)
                and category.get("category_id") == category_id
            ):
                return category

    normalized_path = normalize_for_match(canonicalize_path(taxonomy_path))
    if not normalized_path:
        return None
    by_path = filter_map.get("by_path", {})
    if isinstance(by_path, dict):
        for path, category in by_path.items():
            if normalize_for_match(
                canonicalize_path(str(path))
            ) == normalized_path and isinstance(category, dict):
                return category
    for category in filter_map.get("subcategories", []):
        if (
            isinstance(category, dict)
            and normalize_for_match(canonicalize_path(category.get("path", "")))
            == normalized_path
        ):
            return category
    return None


def canonicalize_path(path: str) -> str:
    return " > ".join(
        segment.strip() for segment in str(path or "").split(">") if segment.strip()
    )


def get_filter_group_names(
    category: dict[str, Any], include_inactive: bool = False
) -> list[str]:
    names: list[str] = []
    for group in category.get("filter_groups", []):
        if not isinstance(group, dict):
            continue
        status = str(group.get("status", "active") or "active")
        if not include_inactive and status in {"inactive", "deprecated"}:
            continue
        name = str(group.get("name", "") or "")
        if name:
            names.append(name)
    return names


def get_filter_group_value_map(
    category: dict[str, Any], include_inactive: bool = False
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for group in category.get("filter_groups", []):
        if not isinstance(group, dict):
            continue
        group_status = str(group.get("status", "active") or "active")
        if not include_inactive and group_status in {"inactive", "deprecated"}:
            continue
        values: list[str] = []
        for value in group.get("values", []):
            if not isinstance(value, dict):
                continue
            status = str(value.get("status", "active") or "active")
            if not include_inactive and status == "inactive":
                continue
            display_value = str(value.get("value", "") or "")
            if display_value:
                values.append(display_value)
        out[str(group.get("name", "") or "")] = values
    return out


def build_spec_lookup_for_filters(source: SourceProductData) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for item in source.key_specs:
        _add_lookup_value(lookup, item)
    for section in source.spec_sections:
        for item in section.items:
            _add_lookup_value(lookup, item)
    for section in source.manufacturer_spec_sections:
        for item in section.items:
            _add_lookup_value(lookup, item)
    return lookup


def resolve_category_filter_values(
    source: SourceProductData,
    taxonomy: TaxonomyResolution,
    filter_category: dict[str, Any],
    review_values: dict[str, str] | None = None,
) -> CategoryFilterResolution:
    taxonomy_path = canonical_taxonomy_path(taxonomy) or str(
        filter_category.get("path", "") or ""
    )
    category_id = str(filter_category.get("category_id") or taxonomy.category_id or "")
    exact_source, exact_manufacturer, exact_description, normalized_lookup = (
        _build_resolution_lookups(source)
    )
    review_exact = {
        str(key): str(value).strip()
        for key, value in (review_values or {}).items()
        if str(value or "").strip()
    }
    review_normalized = {
        normalized_key: value
        for key, value in review_exact.items()
        for normalized_key in candidate_label_keys(key)
    }

    resolution = CategoryFilterResolution(
        category_id=category_id,
        taxonomy_path=taxonomy_path,
        filter_category_found=True,
        available_groups=get_filter_group_names(filter_category, include_inactive=True),
    )

    for group in filter_category.get("filter_groups", []):
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("group_id", "") or "")
        group_name = str(group.get("name", "") or "")
        group_status = str(group.get("status", "active") or "active")
        required = bool(group.get("required", True)) and group_status == "active"
        allowed_values, value_status_by_exact, value_aliases_by_normalized = (
            _allowed_values(group)
        )
        resolved_value, resolved_from = _resolve_group_value(
            group_id=group_id,
            group_name=group_name,
            taxonomy_path=taxonomy_path,
            review_exact=review_exact,
            review_normalized=review_normalized,
            exact_source=exact_source,
            exact_manufacturer=exact_manufacturer,
            exact_description=exact_description,
            normalized_lookup=normalized_lookup,
        )
        if group_status == "inactive" and resolved_from != "approved_review":
            resolved_value = ""
            resolved_from = ""
        resolved_value = _canonical_filter_value(
            resolved_value, value_aliases_by_normalized
        )
        emitted = bool(resolved_value) and group_status == "active"
        inactive_group = group_status == "inactive"
        if (
            resolved_value
            and group_status == "inactive"
            and resolved_from == "approved_review"
        ):
            emitted = True
        if resolved_value and group_status == "deprecated":
            emitted = True

        value_status = value_status_by_exact.get(resolved_value, "")
        deprecated_value = value_status == "deprecated"
        allowed_active_or_deprecated = set(value_status_by_exact)
        outside_allowed = (
            bool(resolved_value)
            and bool(allowed_active_or_deprecated)
            and resolved_value not in allowed_active_or_deprecated
        )
        missing_required = required and not resolved_value

        diagnostic = CategoryFilterValueResolution(
            category_id=category_id,
            taxonomy_path=taxonomy_path,
            group_id=group_id,
            group_name=group_name,
            required=required,
            group_status=group_status,
            allowed_values=allowed_values,
            resolved_value=resolved_value,
            value_status=value_status,
            resolved_from=resolved_from,
            emitted=emitted,
            missing_required=missing_required,
            outside_allowed=outside_allowed,
            deprecated_value=deprecated_value,
            inactive_group=inactive_group,
        )
        resolution.groups.append(diagnostic)

        if emitted:
            resolution.emitted_columns.append(f"filter_group:{group_name}")
        elif missing_required:
            resolution.missing_required_groups.append(group_name)
            resolution.warnings.append(f"required_category_filter_missing:{group_name}")
        elif group_status == "active":
            resolution.unresolved_optional_groups.append(group_name)

        if resolved_value and group_status == "inactive":
            resolution.warnings.append(f"inactive_category_filter_used:{group_name}")
        if resolved_value and group_status == "deprecated":
            resolution.warnings.append(
                f"deprecated_category_filter_group_used:{group_name}"
            )
        if deprecated_value:
            resolution.warnings.append(
                f"deprecated_category_filter_value_used:{group_name}"
            )
        if outside_allowed:
            resolution.warnings.append(
                f"category_filter_value_outside_allowed:{group_name}"
            )

    return resolution


def load_category_filter_review_values(model_root: Path) -> dict[str, str]:
    payload = load_category_filter_review_payload(model_root)
    if not payload:
        return {}
    return coerce_category_filter_review_values(payload)


def coerce_category_filter_review_values(payload: dict[str, Any]) -> dict[str, str]:
    values = payload.get("values", {})
    if not isinstance(values, dict):
        return {}
    coerced: dict[str, str] = {}
    for key, value in values.items():
        if isinstance(value, dict):
            display_value = str(value.get("value", "") or "").strip()
            group_id = str(value.get("group_id") or key or "").strip()
            group_name = str(value.get("group_name", "") or "").strip()
            if display_value and group_id:
                coerced[group_id] = display_value
            if display_value and group_name:
                coerced[group_name] = display_value
            continue
        display_value = str(value or "").strip()
        if display_value:
            coerced[str(key)] = display_value
    return coerced


def load_category_filter_review_payload(model_root: Path) -> dict[str, Any]:
    review_path = category_filter_review_path_for_model_root(model_root)
    if not review_path.exists():
        return {}
    try:
        with review_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"approved": False, "values": {}, "load_error": True}
    return payload if isinstance(payload, dict) else {}


def _add_lookup_value(lookup: dict[str, str], item: SpecItem) -> None:
    label = str(item.label or "")
    value = str(item.value or "").strip()
    if label and value and label not in lookup:
        lookup[label] = value


def _build_resolution_lookups(
    source: SourceProductData,
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, tuple[str, str]]]:
    exact_source: dict[str, str] = {}
    exact_manufacturer: dict[str, str] = {}
    exact_description: dict[str, str] = {}
    normalized: dict[str, tuple[str, str]] = {}

    for item in source.key_specs:
        _add_exact_and_normalized(exact_source, normalized, item, "source")
    for section in source.spec_sections:
        for item in section.items:
            _add_exact_and_normalized(exact_source, normalized, item, "source")
    for section in source.manufacturer_spec_sections:
        for item in section.items:
            _add_exact_and_normalized(
                exact_manufacturer, normalized, item, "manufacturer"
            )
    _add_source_derived_filter_hints(source, exact_source, normalized)
    if normalize_for_match(source.source_name) == "skroutz":
        for item in build_description_spec_items(source):
            _add_exact_and_normalized(
                exact_description, normalized, item, "description"
            )
    return exact_source, exact_manufacturer, exact_description, normalized


def _add_exact_and_normalized(
    exact: dict[str, str],
    normalized: dict[str, tuple[str, str]],
    item: SpecItem,
    source_name: str,
) -> None:
    label = str(item.label or "")
    value = nullify_dash_values(item.value) or ""
    value = str(value).strip()
    if not label or not value:
        return
    exact.setdefault(label, value)
    for normalized_key in candidate_label_keys(label):
        normalized.setdefault(normalized_key, (value, f"normalized_{source_name}"))


def _add_source_derived_filter_hints(
    source: SourceProductData,
    exact: dict[str, str],
    normalized: dict[str, tuple[str, str]],
) -> None:
    title_key = normalize_label_key(source.name)
    source_text = " ".join(
        part
        for part in (
            source.name,
            source.hero_summary,
            source.presentation_source_text,
        )
        if part
    )
    source_text_key = normalize_label_key(source_text)
    spec_lookup = {normalize_label_key(label): value for label, value in exact.items()}

    if "smart" in title_key or any(
        key in spec_lookup for key in ("λογισμικο", "υποστηριζομενες εφαρμογες")
    ):
        _add_exact_and_normalized(
            exact, normalized, SpecItem("Smart Tv", "Υποστηρίζεται"), "derived"
        )
    if "wifi" in source_text_key or "wi fi" in source_text_key:
        _add_exact_and_normalized(
            exact, normalized, SpecItem("Wifi", "Υποστηρίζεται"), "derived"
        )
    wifi_value = spec_lookup.get("wi fi") or spec_lookup.get("wifi")
    if wifi_value and _normalize_filter_yes_no(wifi_value) != "Όχι":
        _add_exact_and_normalized(
            exact, normalized, SpecItem("Wifi", "Υποστηρίζεται"), "derived"
        )
    btu_capacity = _extract_btu_capacity_hint(source_text)
    if btu_capacity:
        _add_exact_and_normalized(
            exact, normalized, SpecItem("Ονομαστική Απόδοση", btu_capacity), "derived"
        )
    if "grill" in title_key or "γκριλ" in title_key:
        _add_exact_and_normalized(
            exact, normalized, SpecItem("Με Grill", "Ναι"), "derived"
        )
    grill_value = spec_lookup.get("λειτουργια grill")
    if grill_value and _normalize_filter_yes_no(grill_value) == "Ναι":
        _add_exact_and_normalized(
            exact, normalized, SpecItem("Με Grill", "Ναι"), "derived"
        )
    if "βραστηρας αυγ" in title_key or "βραστηρα αυγ" in title_key:
        _add_exact_and_normalized(
            exact, normalized, SpecItem("Βραστήρας Αυγών", "Ναι"), "derived"
        )

    energy = _extract_energy_class_hint(source.name)
    if energy:
        _add_exact_and_normalized(
            exact, normalized, SpecItem("Ενεργειακή Κλάση", energy), "derived"
        )


def _resolve_group_value(
    *,
    group_id: str,
    group_name: str,
    taxonomy_path: str,
    review_exact: dict[str, str],
    review_normalized: dict[str, str],
    exact_source: dict[str, str],
    exact_manufacturer: dict[str, str],
    exact_description: dict[str, str],
    normalized_lookup: dict[str, tuple[str, str]],
) -> tuple[str, str]:
    candidate_labels = _candidate_source_labels(group_name, taxonomy_path=taxonomy_path)
    for key in (group_name, group_id):
        value = review_exact.get(key)
        if value:
            return value, "approved_review"
    for normalized_key in candidate_label_keys(group_name):
        value = review_normalized.get(normalized_key)
        if value:
            return value, "approved_review"
    derived_value, derived_from = _resolve_stable_id_group_value(
        group_id=group_id,
        exact_source=exact_source,
        exact_manufacturer=exact_manufacturer,
        normalized_lookup=normalized_lookup,
    )
    if derived_value:
        return derived_value, derived_from
    derived_value, derived_from = _resolve_hob_zone_group_value(
        group_name=group_name,
        exact_source=exact_source,
        exact_manufacturer=exact_manufacturer,
    )
    if derived_value:
        return derived_value, derived_from
    derived_value, derived_from = _resolve_derived_group_value(
        group_name=group_name,
        taxonomy_path=taxonomy_path,
        exact_source=exact_source,
        exact_manufacturer=exact_manufacturer,
    )
    if derived_value:
        return derived_value, derived_from
    for label in candidate_labels:
        value = exact_source.get(label)
        if value:
            return value, (
                "source_spec_exact" if label == group_name else "source_spec_alias"
            )
    for label in candidate_labels:
        value = exact_manufacturer.get(label)
        if value:
            return value, (
                "manufacturer_spec_exact"
                if label == group_name
                else "manufacturer_spec_alias"
            )
    for label in candidate_labels:
        value = exact_description.get(label)
        if value:
            return value, (
                "description_exact" if label == group_name else "description_alias"
            )
    for label in candidate_labels:
        for normalized_key in candidate_label_keys(label):
            normalized = normalized_lookup.get(normalized_key)
            if normalized:
                return normalized
    return "", ""


def _resolve_stable_id_group_value(
    *,
    group_id: str,
    exact_source: dict[str, str],
    exact_manufacturer: dict[str, str],
    normalized_lookup: dict[str, tuple[str, str]],
) -> tuple[str, str]:
    if group_id == "fg_fc9322252117":
        return _resolve_air_condition_energy_class(
            exact_source=exact_source,
            exact_manufacturer=exact_manufacturer,
            normalized_lookup=normalized_lookup,
        )
    if group_id == "fg_7d0f9663ebc1":
        return _resolve_wifi_support(
            exact_source=exact_source,
            exact_manufacturer=exact_manufacturer,
            normalized_lookup=normalized_lookup,
        )
    return "", ""


def _resolve_air_condition_energy_class(
    *,
    exact_source: dict[str, str],
    exact_manufacturer: dict[str, str],
    normalized_lookup: dict[str, tuple[str, str]],
) -> tuple[str, str]:
    lookups = (("source", exact_source), ("manufacturer", exact_manufacturer))
    for source_name, lookup in lookups:
        cooling = _first_energy_value_for_tokens(lookup, ("cool", "cooling", "seer"))
        heating = _first_energy_value_for_tokens(lookup, ("heat", "heating", "scop"))
        if cooling == "A" and heating == "A+++":
            return f"({cooling} / {heating})", f"{source_name}_cooling_heating_energy"
        if cooling:
            return cooling, f"{source_name}_cooling_energy"
    for source_name, lookup in lookups:
        value = _first_energy_value_for_tokens(lookup, ("cool", "cooling", "seer"))
        if value:
            return value, f"{source_name}_cooling_energy"
    for source_name, lookup in lookups:
        value = _first_energy_value_for_tokens(lookup, ("energy",))
        if value:
            return value, f"{source_name}_energy"
    for source_name, lookup in lookups:
        value = _first_energy_value(lookup)
        if value:
            return value, f"{source_name}_energy_value"
    for normalized_key, (value, source_name) in normalized_lookup.items():
        if "energy" not in normalized_key:
            continue
        energy = _latin_energy_class(value)
        if energy:
            return energy, source_name
    return "", ""


def _first_energy_value_for_tokens(
    lookup: dict[str, str], tokens: tuple[str, ...]
) -> str:
    for label, value in lookup.items():
        label_key = _ascii_label_key(label)
        if not all(_ascii_key_has_token(label_key, token) for token in tokens):
            continue
        energy = _latin_energy_class(value)
        if energy:
            return energy
    return ""


def _ascii_key_has_token(label_key: str, token: str) -> bool:
    aliases = {
        "cool": ("cool", "cooling", "psyx", "psix"),
        "cooling": ("cool", "cooling", "psyx", "psix"),
        "heat": ("heat", "heating", "therm"),
        "heating": ("heat", "heating", "therm"),
        "energy": ("energy", "energei"),
    }.get(token, (token,))
    return any(alias in label_key for alias in aliases)


def _first_energy_value(lookup: dict[str, str]) -> str:
    for value in lookup.values():
        energy = _latin_energy_class(value)
        if energy:
            return energy
    return ""


def _resolve_wifi_support(
    *,
    exact_source: dict[str, str],
    exact_manufacturer: dict[str, str],
    normalized_lookup: dict[str, tuple[str, str]],
) -> tuple[str, str]:
    for source_name, lookup in (
        ("source", exact_source),
        ("manufacturer", exact_manufacturer),
    ):
        for label, value in lookup.items():
            label_key = _ascii_label_key(label)
            value_key = _ascii_label_key(value)
            if (
                "wifi" not in label_key
                and "wi fi" not in label_key
                and "wifi" not in value_key
                and "wi fi" not in value_key
            ):
                continue
            if _is_negative_wifi_value(value_key):
                continue
            return "Υποστηρίζεται", f"{source_name}_wifi"
    for normalized_key, (value, source_name) in normalized_lookup.items():
        if "wifi" not in normalized_key and "wi fi" not in normalized_key:
            continue
        if _is_negative_wifi_value(_ascii_label_key(value)):
            continue
        return "Υποστηρίζεται", source_name
    return "", ""


def _is_negative_wifi_value(value_key: str) -> bool:
    return bool(
        re.search(r"\b(no|not|without|none|false|0)\b", value_key)
        or "οχι" in value_key
        or "χωρις" in value_key
    )


def _ascii_label_key(value: str) -> str:
    repaired = repair_mojibake_text(value)
    normalized = unicodedata.normalize("NFD", repaired)
    normalized = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    normalized = unicodedata.normalize("NFC", normalized).casefold()
    replacements = str.maketrans(
        {
            "α": "a",
            "β": "b",
            "γ": "g",
            "δ": "d",
            "ε": "e",
            "ζ": "z",
            "η": "i",
            "θ": "th",
            "ι": "i",
            "κ": "k",
            "λ": "l",
            "μ": "m",
            "ν": "n",
            "ξ": "x",
            "ο": "o",
            "π": "p",
            "ρ": "r",
            "σ": "s",
            "ς": "s",
            "τ": "t",
            "υ": "y",
            "φ": "f",
            "χ": "ch",
            "ψ": "ps",
            "ω": "o",
        }
    )
    normalized = normalized.translate(replacements)
    normalized = re.sub(r"[_\W]+", " ", normalized, flags=re.ASCII)
    return re.sub(r"\s+", " ", normalized).strip()


def _candidate_source_labels(group_name: str, *, taxonomy_path: str = "") -> list[str]:
    candidates = [group_name]
    without_parenthetical = re.sub(r"\s*\([^)]*\)\s*", " ", group_name).strip()
    if without_parenthetical and without_parenthetical not in candidates:
        candidates.append(without_parenthetical)

    aliases: list[str] = []
    aliases.extend(label_aliases_for(group_name))
    normalized_group = normalize_label_key(group_name)
    normalized_taxonomy = normalize_label_key(taxonomy_path)
    if "κιλα πλυσης" in normalized_group:
        aliases.extend(["Χωρητικότητα", "Χωρητικότητα Πλύσης"])
    if (
        "κιλα στεγνωματος" in normalized_group
        and "στεγνωτηρια ρουχων" in normalized_taxonomy
    ):
        aliases.extend(["Χωρητικότητα", "Χωρητικότητα Στεγνώματος"])
    if "στροφες στυψιματος" in normalized_group:
        aliases.extend(["Στροφές", "Μέγιστη ταχύτητα στυψίματος"])
    if "τροπος φορτωσης" in normalized_group:
        aliases.extend(["Τύπος", "Τύπος φόρτωσης"])
    if "χωρητικοτητα" in normalized_group and (
        "λιτρα" in normalized_group or "φουρνου" in normalized_group
    ):
        aliases.append("Χωρητικότητα")
    if (
        "χωρητικοτητα" in normalized_group
        and "λιτρα" in normalized_group
        and "φριτεζες" in normalized_taxonomy
    ):
        aliases.extend(
            [
                "Χωρητικότητα Κάδου Μαγειρέματος σε Κιλά",
                "Χωρητικότητα Κάδου Μαγειρέματος",
            ]
        )
    if (
        normalized_group == normalize_label_key("Ισχύς (Watt)")
        and "φουρνοι μικροκυματων" in normalized_taxonomy
    ):
        aliases.extend(["Ισχύς Μικροκυμάτων (Watt)", "Ισχύς Μικροκυμάτων"])
    if normalized_group == "με grill":
        aliases.extend(["Grill", "Λειτουργία Grill"])
    if "τεχνολογια εστιων" in normalized_group:
        aliases.extend(["Τύπος", "Τύπος Εστίας", "Τεχνολογία Πλατώ Εστιών"])
    if (
        normalized_group == normalize_label_key("Υλικό πλάκας")
        and "κουζινες" in normalized_taxonomy
    ):
        aliases.extend(["Τύπος Εστιών", "Τύπος Εστίας"])
    if "Αριθμός" in group_name and "εστιών" in group_name:
        aliases.extend(["Εστίες", "Εστία"])
    if group_name == "Σύστημα Ήχου" or "Σύστημα" in group_name and "Ήχου" in group_name:
        aliases.extend(["Κανάλια", "Ηχεία"])
    if normalized_group == normalize_label_key("Ισχύς (Watt)"):
        aliases.extend(["Κατανάλωση", "Κατανάλωση Ισχύος"])
    if (
        "διαμετρος" in normalized_group
        and ("εκατοστα" in normalized_group or "cm" in normalized_group)
    ):
        aliases.extend(["Διάμετρος", "Διάμετρος σε cm", "Διάμετρος (cm)"])
    for alias in aliases:
        if alias not in candidates:
            candidates.append(alias)
    return candidates


def _allowed_values(
    group: dict[str, Any],
) -> tuple[list[str], dict[str, str], dict[str, str]]:
    values: list[str] = []
    statuses: dict[str, str] = {}
    aliases_by_normalized: dict[str, str] = {}
    for item in group.get("values", []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "active") or "active")
        value = str(item.get("value", "") or "").strip()
        if not value or status == "inactive":
            continue
        values.append(value)
        statuses[value] = status
        for alias_key in _filter_value_alias_keys(value):
            aliases_by_normalized.setdefault(alias_key, value)
        for alias in item.get("aliases", []):
            for alias_key in _filter_value_alias_keys(str(alias or "").strip()):
                aliases_by_normalized.setdefault(alias_key, value)
    return values, statuses, aliases_by_normalized


def _canonical_filter_value(value: str, aliases_by_normalized: dict[str, str]) -> str:
    if not value:
        return ""
    for normalized_value in _filter_value_alias_keys(value):
        exact = aliases_by_normalized.get(normalized_value)
        if exact:
            return exact
    for normalized_value in _filter_value_alias_keys(value):
        matches = {
            canonical
            for alias_key, canonical in aliases_by_normalized.items()
            if len(alias_key) > 2
            and _normalized_contains_phrase(normalized_value, alias_key)
        }
        if len(matches) == 1:
            return next(iter(matches))
    return value


def _filter_value_alias_keys(value: str) -> list[str]:
    normalized = normalize_label_key(value)
    energy_key = _energy_class_alias_key(value)
    if not normalized and not energy_key:
        return []
    aliases = [energy_key] if energy_key else []
    if normalized and normalized not in aliases:
        aliases.append(normalized)
    compact_units = re.sub(
        r"\b(\d+(?:[.,]\d+)?)\s+(w|watt|watts|kw|lt|l|kg|gr|g|cm|mm|db|btu|rpm)\b",
        r"\1\2",
        normalized,
    )
    if compact_units not in aliases:
        aliases.append(compact_units)
    spaced_units = re.sub(
        r"\b(\d+(?:[.,]\d+)?)(w|watt|watts|kw|lt|l|kg|gr|g|cm|mm|db|btu|rpm)\b",
        r"\1 \2",
        normalized,
    )
    if spaced_units not in aliases:
        aliases.append(spaced_units)
    normalized_units = _normalize_filter_value_units(spaced_units)
    if normalized_units and normalized_units not in aliases:
        aliases.append(normalized_units)
    numeric = _single_numeric_value(normalized_units or spaced_units)
    if numeric and numeric not in aliases:
        aliases.append(numeric)
    for extra in _semantic_filter_value_aliases(
        normalized_units or spaced_units, include_energy=not energy_key
    ):
        if extra not in aliases:
            aliases.append(extra)
    return aliases


def _normalize_filter_value_units(value: str) -> str:
    normalized = value
    normalized = re.sub(r"\bwatts?\b", "w", normalized)
    normalized = re.sub(r"\b(\d+(?:[.,]\d+)?)\s*/?\s*λεπτο\b", r"\1 rpm", normalized)
    normalized = re.sub(r"\bστροφες\s*/?\s*λεπτο\b|\bστροφων\b", "rpm", normalized)
    normalized = re.sub(r"\bλιτρα\b|\bλίτρα\b", "lt", normalized)
    normalized = re.sub(r"\bκιλα\b|\bκιλό\b|\bκιλά\b", "kg", normalized)
    normalized = re.sub(r"\bγραμμ(?:αρια|άρια)\b", "gr", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _single_numeric_value(value: str) -> str:
    match = re.fullmatch(
        r"(\d+(?:[.,]\d+)?)\s*(?:w|kw|lt|l|kg|gr|g|cm|mm|db|btu|rpm)", value
    )
    return match.group(1) if match else ""


def _semantic_filter_value_aliases(
    value: str, *, include_energy: bool = True
) -> list[str]:
    aliases: list[str] = []
    color_aliases = {
        "ivory": "μπεζ",
        "beige": "μπεζ",
        "black": "μαυρο",
        "white": "λευκο",
        "grey": "γκρι",
        "gray": "γκρι",
        "silver": "ασημι",
        "red": "κοκκινο",
    }
    mapped = color_aliases.get(value)
    if mapped:
        aliases.append(mapped)
    if include_energy:
        energy = _latin_energy_class(value)
        if energy:
            aliases.extend([_energy_class_alias_key(value), energy, f"({energy})"])
    if re.fullmatch(r"\d+(?:[.,]\d+)?", value):
        aliases.append(f"{value} kg")
        aliases.append(f"{value}lt")
        aliases.append(f"{value} rpm")
    if "εμπροσθ" in value or "μπροστιν" in value or "front" in value:
        aliases.append("εμπρος")
    if re.search(r"\bανω\b|\btop\b", value):
        aliases.append("ανω")
    if value in {"nofrost", "no frost"}:
        aliases.extend(["no frost", "nofrost"])
    if value in {"total nofrost", "total no frost"}:
        aliases.extend(["total no frost", "total nofrost"])
    if value == "hd":
        aliases.append("hd ready")
    if value == "4k uhd":
        aliases.extend(["4k ultra hd", "ultra hd 4k", "ultra hd (4k)", "ultra hd"])
    if value == "8k uhd":
        aliases.extend(["8k ultra hd", "ultra hd 8k", "ultra hd (8k)"])
    if "επαγωγ" in value:
        aliases.append("αυτονομο κεραμικο επαγωγικο")
    if "κεραμ" in value and "επαγωγ" not in value and "συνδυαζ" not in value:
        aliases.append("αυτονομο κεραμικο ηλεκτρικο")
    channels = re.fullmatch(r"(\d+(?:\.\d+){1,2})(?:\s*ch)?", value)
    if channels:
        aliases.extend([channels.group(1), f"{channels.group(1)} ch"])
    return aliases


def _energy_class_alias_key(value: str) -> str:
    energy = _latin_energy_class(value)
    return f"energy:{energy}" if energy else ""


def _latin_energy_class(value: str) -> str:
    normalized = repair_mojibake_text(value)
    normalized = unicodedata.normalize("NFD", normalized)
    normalized = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    normalized = unicodedata.normalize("NFC", normalized)
    normalized = re.sub(r"\s+", "", normalized.strip().strip("()[]{}"))
    normalized = "".join(
        {
            "Α": "A",
            "Β": "B",
            "Γ": "C",
            "Δ": "D",
            "Ε": "E",
            "Ζ": "F",
            "Η": "G",
            "α": "A",
            "β": "B",
            "γ": "C",
            "δ": "D",
            "ε": "E",
            "ζ": "F",
            "η": "G",
        }.get(char, char)
        for char in normalized
    )
    latin_match = re.fullmatch(
        r"([A-Ga-g])(\+{0,3})(?:/[A-Ga-g]\+{0,3})?",
        normalized,
    )
    if latin_match:
        return f"{latin_match.group(1).upper()}{latin_match.group(2)}"
    greek_to_latin = {
        "Α": "A",
        "Β": "B",
        "Γ": "C",
        "Δ": "D",
        "Ε": "E",
        "Ζ": "F",
        "Η": "G",
        "α": "A",
        "β": "B",
        "γ": "C",
        "δ": "D",
        "ε": "E",
        "ζ": "F",
        "η": "G",
    }
    match = re.fullmatch(
        r"([A-Ga-gΑ-Ηα-η])(\+{0,3})(?:/[A-Ga-gΑ-Ηα-η]\+{0,3})?",
        normalized,
    )
    if not match:
        return ""
    letter = greek_to_latin.get(match.group(1), match.group(1).upper())
    return f"{letter}{match.group(2)}"


def _extract_energy_class_hint(text: str) -> str:
    matches = re.finditer(
        r"(?<![A-Za-zΑ-Ωα-ω])"
        r"([A-GΑ-Ηα-η](?:\+{0,3})(?:\s*/\s*[A-GΑ-Ηα-η](?:\+{0,3}))?)"
        r"(?![A-Za-zΑ-Ωα-ω+])",
        repair_mojibake_text(text),
        flags=re.IGNORECASE,
    )
    fallback = ""
    for match in matches:
        raw = match.group(1)
        if "/" in raw and "+" not in raw:
            continue
        energy = _latin_energy_class(raw)
        if not energy:
            continue
        if "+" in energy:
            return energy
        if not fallback:
            fallback = energy
    return fallback


def _extract_btu_capacity_hint(text: str) -> str:
    match = re.search(
        r"\b(\d{1,2}(?:[.\s]?\d{3})|\d{4,5})\s*btu\b",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    value = re.sub(r"\D", "", match.group(1))
    return f"{value} BTU" if value else ""


def _normalize_filter_yes_no(value: str) -> str:
    normalized = normalize_label_key(value)
    if any(
        token in normalized for token in ("ναι", "yes", "υποστηριζεται", "ενσωματωμενο")
    ):
        return "Ναι"
    if any(token in normalized for token in ("οχι", "no", "δεν")):
        return "Όχι"
    return ""


def _resolve_derived_group_value(
    *,
    group_name: str,
    taxonomy_path: str,
    exact_source: dict[str, str],
    exact_manufacturer: dict[str, str],
) -> tuple[str, str]:
    if _is_width_cm_group(group_name):
        for source_name, lookup in (
            ("source", exact_source),
            ("manufacturer", exact_manufacturer),
        ):
            width = _width_from_named_width_labels(lookup, taxonomy_path=taxonomy_path)
            if width:
                return width, f"{source_name}_width_label"
        for source_name, lookup in (
            ("source", exact_source),
            ("manufacturer", exact_manufacturer),
        ):
            width = _width_from_dimension_triplets(lookup)
            if width:
                return width, f"{source_name}_dimension_triplet"
    return "", ""


def _resolve_hob_zone_group_value(
    *,
    group_name: str,
    exact_source: dict[str, str],
    exact_manufacturer: dict[str, str],
) -> tuple[str, str]:
    if normalize_label_key(group_name) != "αριθμος ζωνων":
        return "", ""
    for source_name, lookup in (
        ("source", exact_source),
        ("manufacturer", exact_manufacturer),
    ):
        count = _first_lookup_value(
            lookup,
            (
                "Αριθμός Ζωνών",
                "Αριθμός εστιών",
                "Εστίες",
                "Ζώνες",
                "Ζώνες Μαγειρέματος",
            ),
        )
        technology = _first_lookup_value(
            lookup,
            ("Τεχνολογία Εστιών", "Τύπος Εστίας", "Τύπος", "Είδος Εστίας"),
        )
        formatted = _format_hob_zone_count(count, technology)
        if formatted:
            return formatted, f"{source_name}_hob_zone_technology"
    return "", ""


def _first_lookup_value(lookup: dict[str, str], labels: tuple[str, ...]) -> str:
    for label in labels:
        value = lookup.get(label)
        if value:
            return value
    normalized_lookup = {
        normalize_label_key(label): value for label, value in lookup.items()
    }
    for label in labels:
        value = normalized_lookup.get(normalize_label_key(label))
        if value:
            return value
    return ""


def _format_hob_zone_count(count: str, technology: str) -> str:
    count_match = re.search(r"\d+", str(count or ""))
    if not count_match:
        return ""
    count_value = count_match.group(0)
    technology_key = normalize_label_key(technology)
    if "επαγωγ" in technology_key:
        return f"{count_value} επαγωγικές"
    if "κεραμ" in technology_key or "ηλεκτρ" in technology_key:
        return f"{count_value} ηλεκτρικές"
    if "αερι" in technology_key or "γκαζ" in technology_key:
        return f"{count_value} αερίου"
    return ""


def _is_width_cm_group(group_name: str) -> bool:
    key = normalize_label_key(group_name)
    return "πλατος" in key and "cm" in key


def _width_from_named_width_labels(
    lookup: dict[str, str], *, taxonomy_path: str
) -> str:
    preferred: list[str] = []
    fallback: list[str] = []
    taxonomy_key = normalize_label_key(taxonomy_path)
    for label, value in lookup.items():
        label_key = normalize_label_key(label)
        if "πλατος" not in label_key:
            continue
        token = _first_numeric_token(value)
        if not token:
            continue
        formatted = _safe_format_width_cm(token, value)
        if not formatted:
            continue
        if "εντοιχισ" in label_key and "εντοιχιζομενες" in taxonomy_key:
            preferred.append(formatted)
        else:
            fallback.append(formatted)
    candidates = preferred or fallback
    return candidates[0] if candidates else ""


def _width_from_dimension_triplets(lookup: dict[str, str]) -> str:
    for label, value in lookup.items():
        if not _looks_like_height_width_depth_label(label):
            continue
        tokens = _dimension_number_tokens(value)
        if len(tokens) >= 3:
            return _safe_format_width_cm(tokens[1], value)
    return ""


def _looks_like_height_width_depth_label(label: str) -> bool:
    key = normalize_label_key(label)
    if "διαστασεις" not in key:
        return False
    return bool(re.search(r"\b(?:υ|y|h)\b.*\b(?:π|p|w)\b.*\b(?:β|v|b|d)\b", key))


def _dimension_number_tokens(value: str) -> list[str]:
    return re.findall(r"\d+(?:[,.]\d+)?", str(value or ""))


def _first_numeric_token(value: str) -> str:
    tokens = _dimension_number_tokens(value)
    return tokens[0] if tokens else ""


def _safe_format_width_cm(token: str, raw_value: str) -> str:
    try:
        return _format_width_cm(token, raw_value)
    except ValueError:
        return ""


def _format_width_cm(token: str, raw_value: str) -> str:
    numeric = float(str(token).replace(",", "."))
    raw_key = normalize_label_key(raw_value)
    if "mm" in raw_key or numeric >= 200:
        numeric /= 10
    formatted = f"{numeric:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{formatted} cm"


def _normalized_contains_phrase(normalized_value: str, normalized_phrase: str) -> bool:
    if not normalized_value or not normalized_phrase:
        return False
    return f" {normalized_phrase} " in f" {normalized_value} "
