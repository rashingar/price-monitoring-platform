from __future__ import annotations

from dataclasses import asdict
import re
from typing import Any
from urllib.parse import urlparse

from .models import SourceProductData, SpecSection, TaxonomyResolution
from .normalize import normalize_for_match
from .repo_paths import CATALOG_TAXONOMY_PATH, FILTER_MAP_PATH
from .utils import dedupe_strings, read_json

ALIASES = {
    normalize_for_match("Εξοπλισμός Σπιτιού"): "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
    normalize_for_match("Οικιακές Συσκευές"): "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
    normalize_for_match("Πλυντήρια Ρούχων Εμπρόσθιας Φόρτωσης"): "Πλυντήρια Ρούχων",
    normalize_for_match("Πλυντήρια Ρούχων Άνω Φόρτωσης"): "Πλυντήρια Ρούχων",
    normalize_for_match("Audio Home Systems"): "Audio Systems",
    normalize_for_match("Sound Bars - Docking Stations"): "Sound Bars",
    normalize_for_match("Mini Hifi"): "Hifi",
    normalize_for_match("Σταθερά Dect"): "Σταθέρα",
    normalize_for_match("Εντοιχιζόμενες"): "Εντοιχιζόμενες Συσκευές",
    normalize_for_match("Σκούπα Stick"): "Σκούπες Stick",
    normalize_for_match("Γυναικεία Φροντίδα"): "Προσωπική Φροντίδα",
    normalize_for_match("Βούρτσες - Ψαλίδια"): "Βούρτσες-Ψαλίδια-ισιωτικά",
    normalize_for_match("Air Condition"): "Κλιματιστικά",
    normalize_for_match("Κλιματιστικά Inverter"): "Τοίχου",
    normalize_for_match("Οικιακά Κλιματιστικά (Split)"): "Τοίχου",
}
TV_LEAF = normalize_for_match("Τηλεοράσεις")
TV_CATEGORY_CTA_URL = "https://www.etranoulis.gr/eikona-hxos/thleoraseis"
MICROWAVE_LEAF = normalize_for_match("Φούρνοι Μικροκυμάτων")
MICROWAVE_CATEGORY_CTA_URL = (
    "https://www.etranoulis.gr/oikiakes-syskeues/fournoi-mikrokymatwn"
)
TV_SIZE_BUCKETS = {
    "Έως 32''": (0, 32),
    "33''-50''": (33, 50),
    "50'' & άνω": (51, None),
}
TV_MANUFACTURER_SUBCATEGORIES = ("TCL",)
TV_MULTI_CATEGORY_ORDER = (
    "Έως 32''",
    "33''-50''",
    "50'' & άνω",
    "8K UHD",
    "OLED TV",
    "4K UHD",
    "TCL",
)
TV_NAME_INCHES_RE = re.compile(
    r"(?<!\d)(\d{2,3})(?:\s*(?:''|\"|”|ιντσ(?:ες|ών)?))(?!\d)", re.IGNORECASE
)
TV_INCH_LABELS = {
    normalize_for_match("Διαγώνιος Οθόνης ( Ίντσες )"),
    normalize_for_match("Διαγώνιος Οθόνης"),
    normalize_for_match("Διαγώνιος"),
    normalize_for_match("Μέγεθος Οθόνης"),
}


def _common_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    idx = 0
    while idx < limit and left[idx] == right[idx]:
        idx += 1
    return idx


def _tokens_soft_overlap(
    left_tokens: set[str], right_tokens: set[str], min_prefix: int = 6
) -> int:
    if not left_tokens or not right_tokens:
        return 0
    matches = 0
    for left in left_tokens:
        if any(
            left == right
            or left.startswith(right)
            or right.startswith(left)
            or _common_prefix_length(left, right) >= min_prefix
            for right in right_tokens
        ):
            matches += 1
    return matches


class TaxonomyResolver:
    def __init__(
        self,
        taxonomy_path: str = str(CATALOG_TAXONOMY_PATH),
        filter_map_path: str = str(FILTER_MAP_PATH),
    ) -> None:
        self.taxonomy = read_json(taxonomy_path)
        self.filter_map = read_json(filter_map_path)
        self.paths: list[dict[str, Any]] = self.taxonomy.get("paths", [])
        self.gender_map: dict[str, dict[str, str]] = self.taxonomy.get("gender_map", {})
        self.filter_rows: list[dict[str, Any]] = self.filter_map.get(
            "subcategories", []
        )
        self.filter_by_path = {
            normalize_for_match(item.get("path", "")): item
            for item in self.filter_rows
            if item.get("path")
        }

    def resolve(
        self,
        breadcrumbs: list[str],
        url: str,
        name: str,
        key_specs: list[dict[str, Any]] | list[Any],
        spec_sections: list[SpecSection],
    ) -> tuple[TaxonomyResolution, list[dict[str, Any]]]:
        mapped_crumbs = [self._alias(item) for item in breadcrumbs]
        crumb_norms = [normalize_for_match(item) for item in mapped_crumbs if item]
        url_path_norm = normalize_for_match(urlparse(url).path)
        url_tokens = set(url_path_norm.split())
        name_tokens = set(normalize_for_match(name).split())
        spec_labels = {
            normalize_for_match(item.label)
            for section in spec_sections
            for item in section.items
            if item.label
        }
        tv_size_bucket = self._resolve_tv_size_bucket(
            name=name, key_specs=key_specs, spec_sections=spec_sections
        )

        candidates: list[dict[str, Any]] = []
        for candidate in self.paths:
            parent = candidate.get("parent_category") or ""
            leaf = candidate.get("leaf_category") or ""
            sub = candidate.get("sub_category")
            parent_norm = normalize_for_match(parent)
            leaf_norm = normalize_for_match(leaf)
            sub_norm = normalize_for_match(sub or "")
            candidate_path_norm = normalize_for_match(candidate.get("path", ""))
            score = 0.0
            reasons: list[str] = []

            if crumb_norms:
                if parent_norm and parent_norm in crumb_norms:
                    score += 3.0
                    reasons.append("parent_breadcrumb")
                if leaf_norm and leaf_norm in crumb_norms:
                    score += 4.0
                    reasons.append("leaf_breadcrumb")
                if sub_norm and sub_norm in crumb_norms:
                    score += 5.0
                    reasons.append("sub_breadcrumb")
                elif sub_norm and any(
                    set(sub_norm.split()).issubset(set(crumb.split()))
                    for crumb in crumb_norms
                ):
                    score += 5.0
                    reasons.append("sub_breadcrumb")
                if len(crumb_norms) >= 3:
                    path_guess = normalize_for_match(" > ".join(mapped_crumbs[1:4]))
                    if path_guess and path_guess == candidate_path_norm:
                        score += 4.0
                        reasons.append("full_breadcrumb_path")

            candidate_url_tokens = set(
                normalize_for_match(candidate.get("url", "")).split()
            )
            shared_url = len(url_tokens & candidate_url_tokens)
            if shared_url:
                score += min(shared_url * 0.5, 3.0)
                reasons.append("url_overlap")

            leaf_tokens = set(leaf_norm.split())
            sub_tokens = set(sub_norm.split()) if sub_norm else set()
            leaf_overlap = _tokens_soft_overlap(leaf_tokens, name_tokens)
            sub_overlap = _tokens_soft_overlap(sub_tokens, name_tokens)
            if leaf_overlap:
                score += 1.5 * (leaf_overlap / max(len(leaf_tokens), 1))
                reasons.append("leaf_name_overlap")
            if sub_overlap:
                score += 2.0 * (sub_overlap / max(len(sub_tokens), 1))
                reasons.append("sub_name_overlap")

            if (
                leaf_norm == TV_LEAF
                and tv_size_bucket
                and (sub or "") == tv_size_bucket
            ):
                score += 3.5
                reasons.append("television_size_bucket")

            if sub_norm == normalize_for_match("Hifi") and {"mini", "hifi"}.issubset(
                url_tokens
            ):
                score += 3.0
                reasons.append("electronet_mini_hifi_url")

            if "frapieres" in url_tokens and "frapieres" in candidate_url_tokens:
                score += 3.0
                reasons.append("electronet_frapieres_url")

            if (
                sub_norm == normalize_for_match("Τηγάνια")
                and "tigania" in url_tokens
                and "wok" in url_tokens
            ):
                score += 4.0
                reasons.append("electronet_tigania_wok_url")

            if leaf_norm == MICROWAVE_LEAF:
                without_grill_url = any(
                    token in url_path_norm
                    for token in ("horis grill", "xoris grill", "without grill")
                )
                with_grill_url = not without_grill_url and any(
                    token in url_path_norm
                    for token in ("me grill", "with grill", "grill")
                )
                if without_grill_url and sub_norm == normalize_for_match("Χωρίς Grill"):
                    score += 4.0
                    reasons.append("electronet_microwave_without_grill_url")
                elif with_grill_url and sub_norm == normalize_for_match("Με Grill"):
                    score += 4.0
                    reasons.append("electronet_microwave_with_grill_url")

            filter_row = self.filter_by_path.get(candidate_path_norm)
            if filter_row:
                matched_filters = 0
                for filter_group in filter_row.get("filter_groups", []):
                    filter_group_name = (
                        filter_group.get("name", "")
                        if isinstance(filter_group, dict)
                        else filter_group
                    )
                    if normalize_for_match(filter_group_name) in spec_labels:
                        matched_filters += 1
                if matched_filters:
                    score += min(matched_filters * 0.25, 1.0)
                    reasons.append("filter_map_tiebreak")

            cta_url = candidate.get("cta_url") or candidate.get("url") or ""
            if leaf_norm == TV_LEAF:
                cta_url = TV_CATEGORY_CTA_URL
            if leaf_norm == MICROWAVE_LEAF:
                cta_url = MICROWAVE_CATEGORY_CTA_URL

            candidates.append(
                {
                    "parent_category": parent,
                    "leaf_category": leaf,
                    "sub_category": sub,
                    "taxonomy_path": candidate.get("path", ""),
                    "cta_url": cta_url,
                    "confidence": round(score, 4),
                    "reasons": reasons,
                }
            )

        candidates.sort(key=lambda item: item["confidence"], reverse=True)
        best = candidates[0] if candidates else None
        second = candidates[1] if len(candidates) > 1 else None
        if not best:
            return TaxonomyResolution(reason="no_candidates"), []

        delta = best["confidence"] - (second["confidence"] if second else 0.0)
        resolved = False
        if best["confidence"] >= 7.0:
            resolved = True
        elif (
            best["confidence"] >= 5.0
            and delta >= 1.5
            and any(
                reason in best["reasons"]
                for reason in ["sub_breadcrumb", "full_breadcrumb_path"]
            )
        ):
            resolved = True
        elif (
            best["confidence"] >= 4.5
            and delta >= 2.0
            and "leaf_breadcrumb" in best["reasons"]
        ):
            resolved = True

        if not resolved:
            return (
                TaxonomyResolution(
                    confidence=best["confidence"], reason="low_confidence"
                ),
                candidates[:5],
            )

        gender, plural_label = self._lookup_gender(
            best.get("sub_category"), best.get("leaf_category", "")
        )
        if normalize_for_match(best.get("leaf_category", "")) == TV_LEAF:
            gender, plural_label = self._lookup_gender(
                None, best.get("leaf_category", "")
            )
        if normalize_for_match(best.get("leaf_category", "")) == MICROWAVE_LEAF:
            gender, plural_label = self._lookup_gender(
                None, best.get("leaf_category", "")
            )
        filter_row = (
            self.filter_by_path.get(normalize_for_match(best.get("taxonomy_path", "")))
            or {}
        )
        return (
            TaxonomyResolution(
                category_id=str(filter_row.get("category_id", "") or ""),
                parent_category=best["parent_category"],
                leaf_category=best["leaf_category"],
                sub_category=best.get("sub_category"),
                taxonomy_path=best.get("taxonomy_path", ""),
                cta_url=best.get("cta_url", ""),
                confidence=best["confidence"],
                reason=",".join(best["reasons"]),
                gender=gender,
                plural_label=plural_label,
            ),
            candidates[:5],
        )

    def serialize_category(
        self,
        resolution: TaxonomyResolution,
        boxnow: int = 0,
        source: SourceProductData | None = None,
    ) -> str:
        if not resolution.parent_category or not resolution.leaf_category:
            return ""
        parent = resolution.parent_category
        leaf = resolution.leaf_category
        assignments = [parent, f"{parent}///{leaf}"]
        subcategories = (
            self._tv_serialized_subcategories(resolution, source)
            if normalize_for_match(leaf) == TV_LEAF
            else [resolution.sub_category] if resolution.sub_category else []
        )
        assignments.extend(
            f"{parent}///{leaf}///{sub_category}"
            for sub_category in subcategories
            if sub_category
        )
        serialized = ":::".join(dedupe_strings(assignments))
        if int(boxnow) == 1:
            serialized += ":::Μικροσυσκευές"
        return serialized

    def _tv_serialized_subcategories(
        self,
        resolution: TaxonomyResolution,
        source: SourceProductData | None,
    ) -> list[str]:
        detected: set[str] = set()
        if resolution.sub_category:
            detected.add(resolution.sub_category)
        if source is not None:
            size_bucket = self._resolve_tv_size_bucket_from_source(source)
            if size_bucket:
                detected.add(size_bucket)
            detected.update(self._resolve_tv_technology_subcategories(source))
            for manufacturer in TV_MANUFACTURER_SUBCATEGORIES:
                if self._source_matches_tv_manufacturer(source, manufacturer):
                    detected.add(manufacturer)

        ordered = [
            sub_category
            for sub_category in TV_MULTI_CATEGORY_ORDER
            if sub_category in detected
        ]
        ordered.extend(
            sorted(
                sub_category
                for sub_category in detected
                if sub_category not in TV_MULTI_CATEGORY_ORDER
            )
        )
        return ordered

    def _resolve_tv_size_bucket_from_source(self, source: SourceProductData) -> str:
        if source.taxonomy_tv_inches:
            bucket = self._tv_size_bucket_for_inches(int(source.taxonomy_tv_inches))
            if bucket:
                return bucket
        return self._resolve_tv_size_bucket(
            name=source.name,
            key_specs=source.key_specs,
            spec_sections=[*source.spec_sections, *source.manufacturer_spec_sections],
        )

    def _resolve_tv_technology_subcategories(
        self, source: SourceProductData
    ) -> list[str]:
        normalized = normalize_for_match(self._source_tv_text(source))
        tokens = set(normalized.split())
        detected: list[str] = []
        if {"8k", "7680", "4320"} & tokens:
            detected.append("8K UHD")
        if "oled" in tokens:
            detected.append("OLED TV")
        if {"4k", "3840", "2160"} & tokens:
            detected.append("4K UHD")
        return detected

    def _source_matches_tv_manufacturer(
        self, source: SourceProductData, manufacturer: str
    ) -> bool:
        manufacturer_key = normalize_for_match(manufacturer)
        brand_key = normalize_for_match(source.brand)
        if brand_key == manufacturer_key:
            return True
        return manufacturer_key in set(normalize_for_match(source.name).split())

    def _source_tv_text(self, source: SourceProductData) -> str:
        parts = [
            source.brand,
            source.name,
            source.category_tag_text,
            source.taxonomy_source_category,
        ]
        for item in source.key_specs:
            parts.extend([item.label, item.value or ""])
        for section in [*source.spec_sections, *source.manufacturer_spec_sections]:
            parts.append(section.section)
            for item in section.items:
                parts.extend([item.label, item.value or ""])
        return " ".join(part for part in parts if part)

    def _lookup_gender(
        self, sub_category: str | None, leaf_category: str
    ) -> tuple[str, str]:
        for key in [sub_category or "", leaf_category]:
            entry = self.gender_map.get(key)
            if entry:
                return entry.get("gender", ""), entry.get("plural_label", "")
        return "", ""

    def _alias(self, value: str) -> str:
        normalized = normalize_for_match(value)
        if "κοπτηρια" in normalized and "ραβδο" in normalized:
            return "Κοπτήρια-Ράβδοι"
        return ALIASES.get(normalized, value)

    def _resolve_tv_size_bucket(
        self,
        *,
        name: str,
        key_specs: list[dict[str, Any]] | list[Any],
        spec_sections: list[SpecSection],
    ) -> str:
        inches = self._extract_tv_inches(
            name=name, key_specs=key_specs, spec_sections=spec_sections
        )
        if inches is None:
            return ""
        return self._tv_size_bucket_for_inches(inches)

    def _tv_size_bucket_for_inches(self, inches: int) -> str:
        for bucket, (minimum, maximum) in TV_SIZE_BUCKETS.items():
            if inches < minimum:
                continue
            if maximum is not None and inches > maximum:
                continue
            return bucket
        return ""

    def _extract_tv_inches(
        self,
        *,
        name: str,
        key_specs: list[dict[str, Any]] | list[Any],
        spec_sections: list[SpecSection],
    ) -> int | None:
        for item in key_specs:
            label = normalize_for_match(self._item_value(item, "label"))
            value = self._item_value(item, "value")
            if label in TV_INCH_LABELS:
                extracted = self._extract_int(value)
                if extracted is not None:
                    return extracted
        for section in spec_sections:
            for item in section.items:
                if normalize_for_match(item.label) in TV_INCH_LABELS:
                    extracted = self._extract_int(item.value or "")
                    if extracted is not None:
                        return extracted
        match = TV_NAME_INCHES_RE.search(name)
        if match:
            return int(match.group(1))
        return None

    def _item_value(self, item: Any, field: str) -> str:
        if isinstance(item, dict):
            return str(item.get(field, "") or "")
        return str(getattr(item, field, "") or "")

    def _extract_int(self, value: str) -> int | None:
        match = re.search(r"(\d{2,3})", str(value or ""))
        if not match:
            return None
        return int(match.group(1))
