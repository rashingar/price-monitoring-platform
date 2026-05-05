from __future__ import annotations

from typing import Any

from .models import SchemaMatchResult, SpecSection
from .normalize import normalize_for_match
from .repo_paths import SCHEMA_LIBRARY_PATH
from .utils import read_json


SUBCATEGORY_MATCH_POLICY_EXACT = "exact_subcategory"
SUBCATEGORY_MATCH_POLICY_LEAF_FAMILY = "leaf_family"
SUBCATEGORY_MATCH_POLICY_MIXED_FAMILY = "mixed_family"


class SchemaMatcher:
    def __init__(self, schema_path: str = str(SCHEMA_LIBRARY_PATH)) -> None:
        self.schema_path = schema_path
        self.payload = read_json(schema_path)
        self.schemas: list[dict[str, Any]] = self.payload.get("schemas", [])
        self.schemas_by_id: dict[str, dict[str, Any]] = {
            str(schema.get("schema_id", "")).strip(): schema
            for schema in self.schemas
            if str(schema.get("schema_id", "")).strip()
        }
        self.schemas_by_category_path: dict[str, list[dict[str, Any]]] = {}
        self.schemas_by_parent_leaf: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for schema in self.schemas:
            category_key = normalize_for_match(schema.get("category_path", ""))
            if category_key:
                self.schemas_by_category_path.setdefault(category_key, []).append(schema)
            parent_leaf_key = self._parent_leaf_key(
                schema.get("parent_category"),
                schema.get("leaf_category"),
            )
            if parent_leaf_key is not None:
                self.schemas_by_parent_leaf.setdefault(parent_leaf_key, []).append(schema)
        self._known_titles = {
            normalize_for_match(section.get("title", ""))
            for schema in self.schemas
            for section in schema.get("sections", [])
            if section.get("title")
        }
        self._known_titles.update(
            {
                normalize_for_match("Επιλογές Πλύσης"),
                normalize_for_match("Επιλογές"),
                normalize_for_match("Ασφάλεια"),
                normalize_for_match("Συνδέσεις"),
                normalize_for_match("Γενικά Χαρακτηριστικά"),
                normalize_for_match("Ενεργειακά χαρακτηριστικά"),
            }
        )

    @property
    def known_section_titles(self) -> set[str]:
        return {title for title in self._known_titles if title}

    def match(
        self,
        spec_sections: list[SpecSection],
        taxonomy_sub_category: str | None = None,
        preferred_source_files: list[str] | None = None,
        taxonomy_path: str | None = None,
        taxonomy_parent_category: str | None = None,
        taxonomy_leaf_category: str | None = None,
    ) -> tuple[SchemaMatchResult, list[dict[str, Any]]]:
        if not spec_sections:
            return (
                SchemaMatchResult(
                    matched_schema_id=None,
                    matched_sub_category=taxonomy_sub_category,
                    score=0.0,
                    warnings=["no_spec_sections_extracted"],
                    resolved_category_path=taxonomy_path or "",
                    fail_reason="no_safe_template_match",
                ),
                [],
            )

        extracted_titles = {normalize_for_match(section.section) for section in spec_sections if section.section}
        extracted_labels = {
            normalize_for_match(item.label)
            for section in spec_sections
            for item in section.items
            if item.label
        }
        extracted_pairs = {
            normalize_for_match(f"{section.section} || {item.label}")
            for section in spec_sections
            for item in section.items
            if section.section and item.label
        }
        category_pool = self.build_candidate_pool(
            taxonomy_sub_category=taxonomy_sub_category,
            taxonomy_path=taxonomy_path,
            taxonomy_parent_category=taxonomy_parent_category,
            taxonomy_leaf_category=taxonomy_leaf_category,
            preferred_source_files=preferred_source_files or [],
        )
        resolved_category_path = self._resolved_category_path(
            taxonomy_path=taxonomy_path,
            taxonomy_parent_category=taxonomy_parent_category,
            taxonomy_leaf_category=taxonomy_leaf_category,
            taxonomy_sub_category=taxonomy_sub_category,
        )
        candidate_template_ids = [str(schema.get("template_id", "")) for schema in category_pool if str(schema.get("template_id", "")).strip()]
        pool_subcategory_match_policy = self._pool_subcategory_match_policy(category_pool)
        if not category_pool:
            return (
                self._debug_result(
                    matched_schema_id=None,
                    matched_sub_category=taxonomy_sub_category,
                    score=0.0,
                    warnings=["no_safe_template_match"],
                    subcategory_match_policy=pool_subcategory_match_policy,
                    resolved_category_path=resolved_category_path,
                    candidate_pool_size=0,
                    candidate_template_ids=[],
                    selected_template_id=None,
                    match_mode="",
                    hard_gate_failures=[],
                    fail_reason="pool_empty_for_category",
                ),
                [],
            )

        safe_templates, inactive_candidates = self.filter_inactive_templates(category_pool)
        if not safe_templates:
            fail_reason = "manual_only_category" if self._all_manual_only(category_pool) else "no_active_templates"
            return (
                self._debug_result(
                    matched_schema_id=None,
                    matched_sub_category=taxonomy_sub_category,
                    score=0.0,
                    warnings=["no_safe_template_match"],
                    subcategory_match_policy=pool_subcategory_match_policy,
                    resolved_category_path=resolved_category_path,
                    candidate_pool_size=len(category_pool),
                    candidate_template_ids=candidate_template_ids,
                    selected_template_id=None,
                    match_mode=self._pool_match_mode(category_pool),
                    hard_gate_failures=[],
                    fail_reason=fail_reason,
                ),
                inactive_candidates[:5],
            )

        if len(safe_templates) == 1:
            selected = safe_templates[0]
            diagnostics = [
                self._candidate_record(
                    selected,
                    extracted_titles=extracted_titles,
                    extracted_labels=extracted_labels,
                    extracted_pairs=extracted_pairs,
                    score=1.0,
                    gate_status="bypassed_direct_single",
                    gate_reasons=[],
                )
            ]
            return self.select_safe_template(
                selected,
                diagnostics,
                extracted_titles=extracted_titles,
                extracted_labels=extracted_labels,
                taxonomy_sub_category=taxonomy_sub_category,
                score=1.0,
                resolved_category_path=resolved_category_path,
                candidate_pool_size=len(category_pool),
                candidate_template_ids=candidate_template_ids,
                fail_reason="",
            )

        gated_templates, gated_candidates = self.apply_hard_gates(
            safe_templates,
            extracted_titles=extracted_titles,
            extracted_labels=extracted_labels,
            extracted_pairs=extracted_pairs,
        )
        if not gated_templates:
            gated_candidates.sort(key=self._candidate_sort_key)
            return (
                self._debug_result(
                    matched_schema_id=None,
                    matched_sub_category=taxonomy_sub_category,
                    score=0.0,
                    warnings=["no_safe_template_match"],
                    subcategory_match_policy=pool_subcategory_match_policy,
                    resolved_category_path=resolved_category_path,
                    candidate_pool_size=len(category_pool),
                    candidate_template_ids=candidate_template_ids,
                    selected_template_id=None,
                    match_mode=self._pool_match_mode(safe_templates),
                    hard_gate_failures=self._hard_gate_failures(gated_candidates),
                    fail_reason=self._summarize_fail_reason(gated_candidates),
                    discriminator_hits=[],
                    discriminator_misses=self._aggregate_discriminator_misses(gated_candidates),
                ),
                gated_candidates[:5],
            )

        scored_candidates = self.score_sibling_candidates(
            gated_templates,
            extracted_titles=extracted_titles,
            extracted_labels=extracted_labels,
            extracted_pairs=extracted_pairs,
        )
        selected = self.schemas_by_id.get(str(scored_candidates[0]["matched_schema_id"]).strip())
        if selected is None:
            return (
                SchemaMatchResult(
                    matched_schema_id=None,
                    matched_sub_category=taxonomy_sub_category,
                    score=0.0,
                    warnings=["no_safe_template_match"],
                    subcategory_match_policy=pool_subcategory_match_policy,
                ),
                scored_candidates[:5],
            )
        return self.select_safe_template(
            selected,
            scored_candidates,
            extracted_titles=extracted_titles,
            extracted_labels=extracted_labels,
            taxonomy_sub_category=taxonomy_sub_category,
            score=float(scored_candidates[0]["score"]),
            resolved_category_path=resolved_category_path,
            candidate_pool_size=len(category_pool),
            candidate_template_ids=candidate_template_ids,
            fail_reason="",
        )

    def build_candidate_pool(
        self,
        *,
        taxonomy_sub_category: str | None,
        taxonomy_path: str | None,
        taxonomy_parent_category: str | None,
        taxonomy_leaf_category: str | None,
        preferred_source_files: list[str],
    ) -> list[dict[str, Any]]:
        normalized_taxonomy_path = normalize_for_match(taxonomy_path)
        if not normalized_taxonomy_path and taxonomy_parent_category and taxonomy_leaf_category:
            normalized_taxonomy_path = self._normalize_category_path(
                taxonomy_parent_category,
                taxonomy_leaf_category,
                taxonomy_sub_category,
            )

        exact_pool = list(self.schemas_by_category_path.get(normalized_taxonomy_path, [])) if normalized_taxonomy_path else []
        if exact_pool:
            pool = exact_pool
        elif taxonomy_parent_category and taxonomy_leaf_category and taxonomy_sub_category:
            pool = self._fallback_candidates_for_parent_leaf(taxonomy_parent_category, taxonomy_leaf_category)
        else:
            pool = []

        if not pool:
            return []

        normalized_preferred_files = {
            normalize_for_match(item)
            for item in preferred_source_files
            if normalize_for_match(item)
        }
        if not normalized_preferred_files:
            return pool

        preferred_pool = [
            schema
            for schema in pool
            if normalized_preferred_files & self._normalized_source_files(schema)
        ]
        return preferred_pool or pool

    def filter_inactive_templates(self, candidate_pool: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        safe_templates: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        for schema in candidate_pool:
            template_status = self._normalized_template_status(schema.get("template_status", ""))
            if template_status == "active":
                safe_templates.append(schema)
                continue
            diagnostics.append(
                self._candidate_record(
                    schema,
                    extracted_titles=set(),
                    extracted_labels=set(),
                    extracted_pairs=set(),
                    score=0.0,
                    gate_status="inactive",
                    gate_reasons=[f"template_status:{schema.get('template_status', '') or 'unknown'}"],
                )
            )
        diagnostics.sort(key=self._candidate_sort_key)
        return safe_templates, diagnostics

    def apply_hard_gates(
        self,
        candidates: list[dict[str, Any]],
        *,
        extracted_titles: set[str],
        extracted_labels: set[str],
        extracted_pairs: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        passed: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        for schema in candidates:
            section_overlap = len(extracted_titles & set(schema.get("section_names_normalized", [])))
            label_overlap = len(extracted_labels & set(schema.get("label_set_normalized", [])))
            gate_reasons: list[str] = []
            required_any = set(schema.get("required_labels_any", []))
            required_all = set(schema.get("required_labels_all", []))
            forbidden = set(schema.get("forbidden_labels", []))

            if required_all and not required_all <= extracted_labels:
                gate_reasons.append("missing_required_labels_all")
            if required_any and not (required_any & extracted_labels):
                gate_reasons.append("missing_required_labels_any")
            if forbidden and (forbidden & extracted_labels):
                gate_reasons.append("forbidden_labels_present")
            if section_overlap < int(schema.get("min_section_overlap") or 0):
                gate_reasons.append("min_section_overlap")
            if label_overlap < int(schema.get("min_label_overlap") or 0):
                gate_reasons.append("min_label_overlap")

            diagnostics.append(
                self._candidate_record(
                    schema,
                    extracted_titles=extracted_titles,
                    extracted_labels=extracted_labels,
                    extracted_pairs=extracted_pairs,
                    score=0.0,
                    gate_status="passed" if not gate_reasons else "failed",
                    gate_reasons=gate_reasons,
                )
            )
            if not gate_reasons:
                passed.append(schema)

        diagnostics.sort(key=self._candidate_sort_key)
        return passed, diagnostics

    def score_sibling_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        extracted_titles: set[str],
        extracted_labels: set[str],
        extracted_pairs: set[str],
    ) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []
        for schema in candidates:
            section_names = set(schema.get("section_names_normalized", []))
            labels = set(schema.get("label_set_normalized", []))
            section_label_pairs = set(schema.get("section_label_pairs_normalized", []))
            discriminator_labels = set(schema.get("discriminator_labels", []))

            section_overlap = len(extracted_titles & section_names)
            label_overlap = len(extracted_labels & labels)
            pair_overlap = len(extracted_pairs & section_label_pairs)
            discriminator_overlap = len(extracted_labels & discriminator_labels)

            section_ratio = section_overlap / max(len(section_names), 1)
            label_ratio = label_overlap / max(len(labels), 1)
            pair_ratio = pair_overlap / max(len(section_label_pairs), 1)
            discriminator_ratio = discriminator_overlap / max(len(discriminator_labels), 1)
            score = (0.2 * section_ratio) + (0.3 * label_ratio) + (0.4 * pair_ratio) + (0.1 * discriminator_ratio)

            scored.append(
                self._candidate_record(
                    schema,
                    extracted_titles=extracted_titles,
                    extracted_labels=extracted_labels,
                    extracted_pairs=extracted_pairs,
                    score=score,
                    gate_status="passed",
                    gate_reasons=[],
                )
            )

        scored.sort(key=self._candidate_sort_key)
        return scored

    def select_safe_template(
        self,
        schema: dict[str, Any],
        candidates: list[dict[str, Any]],
        *,
        extracted_titles: set[str],
        extracted_labels: set[str],
        taxonomy_sub_category: str | None,
        score: float,
        resolved_category_path: str,
        candidate_pool_size: int,
        candidate_template_ids: list[str],
        fail_reason: str,
    ) -> tuple[SchemaMatchResult, list[dict[str, Any]]]:
        warnings: list[str] = []
        if len(candidates) > 1 and score < 0.35:
            warnings.append("weak_schema_match")
        warnings.extend(self._selection_warnings(schema, extracted_titles=extracted_titles, extracted_labels=extracted_labels))
        best_candidate = candidates[0] if candidates else {}
        return (
            self._debug_result(
                matched_schema_id=str(schema.get("schema_id", "")).strip() or None,
                matched_sub_category=schema.get("sub_category") or taxonomy_sub_category,
                score=round(score, 4),
                warnings=warnings,
                subcategory_match_policy=self._normalized_subcategory_match_policy(
                    schema.get("subcategory_match_policy", "")
                ),
                resolved_category_path=resolved_category_path,
                candidate_pool_size=candidate_pool_size,
                candidate_template_ids=candidate_template_ids,
                selected_template_id=str(schema.get("template_id", "")).strip() or None,
                match_mode=str(schema.get("match_mode", "")).strip(),
                hard_gate_failures=self._hard_gate_failures(candidates),
                fail_reason=fail_reason,
                discriminator_hits=list(best_candidate.get("discriminator_hits", [])),
                discriminator_misses=list(best_candidate.get("discriminator_misses", [])),
                section_overlap_score=float(best_candidate.get("section_overlap_score", 0.0)),
                label_overlap_score=float(best_candidate.get("label_overlap_score", 0.0)),
            ),
            candidates[:5],
        )

    def _candidate_record(
        self,
        schema: dict[str, Any],
        *,
        extracted_titles: set[str],
        extracted_labels: set[str],
        extracted_pairs: set[str],
        score: float,
        gate_status: str,
        gate_reasons: list[str],
    ) -> dict[str, Any]:
        section_names = set(schema.get("section_names_normalized", []))
        labels = set(schema.get("label_set_normalized", []))
        section_label_pairs = set(schema.get("section_label_pairs_normalized", []))
        discriminator_labels = set(schema.get("discriminator_labels", []))
        section_overlap = len(extracted_titles & section_names)
        label_overlap = len(extracted_labels & labels)
        pair_overlap = len(extracted_pairs & section_label_pairs)
        discriminator_overlap = len(extracted_labels & discriminator_labels)
        discriminator_hits = sorted(label for label in discriminator_labels if label in extracted_labels)
        discriminator_misses = sorted(label for label in discriminator_labels if label not in extracted_labels)
        section_overlap_score = section_overlap / max(len(section_names), 1)
        label_overlap_score = label_overlap / max(len(labels), 1)
        return {
            "matched_schema_id": schema.get("schema_id"),
            "template_id": schema.get("template_id"),
            "matched_sub_category": schema.get("sub_category"),
            "category_path": schema.get("category_path", ""),
            "template_status": schema.get("template_status", ""),
            "match_mode": schema.get("match_mode", ""),
            "subcategory_match_policy": self._normalized_subcategory_match_policy(
                schema.get("subcategory_match_policy", "")
            ),
            "score": round(score, 4),
            "section_overlap": section_overlap,
            "label_overlap": label_overlap,
            "section_overlap_score": round(section_overlap_score, 4),
            "label_overlap_score": round(label_overlap_score, 4),
            "pair_overlap": pair_overlap,
            "discriminator_overlap": discriminator_overlap,
            "discriminator_hits": discriminator_hits,
            "discriminator_misses": discriminator_misses,
            "gate_status": gate_status,
            "gate_reasons": gate_reasons,
            "n_sections": schema.get("n_sections"),
            "n_rows_total": schema.get("n_rows_total"),
            "source_files": list(schema.get("source_files", [])),
        }

    def _selection_warnings(
        self,
        schema: dict[str, Any],
        *,
        extracted_titles: set[str],
        extracted_labels: set[str],
    ) -> list[str]:
        warnings: list[str] = []
        expected_titles = {
            normalize_for_match(section.get("title", ""))
            for section in schema.get("sections", [])
            if section.get("title")
        }
        missing_titles = sorted(title for title in expected_titles if title and title not in extracted_titles)
        if missing_titles:
            warnings.append(f"missing_expected_sections:{len(missing_titles)}")
        sentinel = schema.get("sentinel") or {}
        last_section = normalize_for_match(sentinel.get("last_section", ""))
        last_label = normalize_for_match(sentinel.get("last_label", ""))
        if last_section and last_section not in extracted_titles:
            warnings.append("schema_sentinel_section_missing")
        if last_label and last_label not in extracted_labels:
            warnings.append("schema_sentinel_label_missing")
        return warnings

    def _leaf_only_candidates(self, parent_category: str | None, leaf_category: str | None) -> list[dict[str, Any]]:
        parent_leaf_key = self._parent_leaf_key(parent_category, leaf_category)
        if parent_leaf_key is None:
            return []
        return [
            schema
            for schema in self.schemas_by_parent_leaf.get(parent_leaf_key, [])
            if not normalize_for_match(schema.get("sub_category", ""))
        ]

    def _fallback_candidates_for_parent_leaf(self, parent_category: str | None, leaf_category: str | None) -> list[dict[str, Any]]:
        return [
            schema
            for schema in self._leaf_only_candidates(parent_category, leaf_category)
            if self._allows_leaf_fallback(schema)
        ]

    def _allows_leaf_fallback(self, schema: dict[str, Any]) -> bool:
        return self._normalized_subcategory_match_policy(schema.get("subcategory_match_policy", "")) in {
            SUBCATEGORY_MATCH_POLICY_LEAF_FAMILY,
            SUBCATEGORY_MATCH_POLICY_MIXED_FAMILY,
        }

    def _normalized_source_files(self, schema: dict[str, Any]) -> set[str]:
        return {
            normalize_for_match(source_file)
            for source_file in schema.get("source_files", [])
            if normalize_for_match(source_file)
        }

    def _normalize_category_path(
        self,
        parent_category: str | None,
        leaf_category: str | None,
        sub_category: str | None,
    ) -> str:
        parent = str(parent_category or "").strip()
        leaf = str(leaf_category or "").strip()
        if not parent or not leaf:
            return ""
        return normalize_for_match(f"{parent} > {leaf} > {sub_category or '-'}")

    def _resolved_category_path(
        self,
        *,
        taxonomy_path: str | None,
        taxonomy_parent_category: str | None,
        taxonomy_leaf_category: str | None,
        taxonomy_sub_category: str | None,
    ) -> str:
        if str(taxonomy_path or "").strip():
            return str(taxonomy_path or "").strip()
        parent = str(taxonomy_parent_category or "").strip()
        leaf = str(taxonomy_leaf_category or "").strip()
        if not parent or not leaf:
            return ""
        return f"{parent} > {leaf} > {taxonomy_sub_category or '-'}"

    def _parent_leaf_key(self, parent_category: str | None, leaf_category: str | None) -> tuple[str, str] | None:
        parent = normalize_for_match(parent_category)
        leaf = normalize_for_match(leaf_category)
        if not parent or not leaf:
            return None
        return parent, leaf

    def _candidate_sort_key(self, item: dict[str, Any]) -> tuple[float, int, int, int, int, str]:
        return (
            -float(item.get("score", 0.0)),
            -int(item.get("pair_overlap", 0)),
            -int(item.get("label_overlap", 0)),
            -int(item.get("section_overlap", 0)),
            -int(item.get("discriminator_overlap", 0)),
            str(item.get("template_id", "")),
        )

    def _debug_result(
        self,
        *,
        matched_schema_id: str | None,
        matched_sub_category: str | None,
        score: float,
        warnings: list[str],
        subcategory_match_policy: str,
        resolved_category_path: str,
        candidate_pool_size: int,
        candidate_template_ids: list[str],
        selected_template_id: str | None = None,
        match_mode: str = "",
        hard_gate_failures: list[dict[str, Any]] | None = None,
        fail_reason: str = "",
        discriminator_hits: list[str] | None = None,
        discriminator_misses: list[str] | None = None,
        section_overlap_score: float = 0.0,
        label_overlap_score: float = 0.0,
    ) -> SchemaMatchResult:
        return SchemaMatchResult(
            matched_schema_id=matched_schema_id,
            matched_sub_category=matched_sub_category,
            score=score,
            warnings=warnings,
            subcategory_match_policy=subcategory_match_policy,
            resolved_category_path=resolved_category_path,
            candidate_pool_size=candidate_pool_size,
            candidate_template_ids=candidate_template_ids,
            selected_template_id=selected_template_id,
            match_mode=match_mode,
            hard_gate_failures=hard_gate_failures or [],
            fail_reason=fail_reason,
            discriminator_hits=discriminator_hits or [],
            discriminator_misses=discriminator_misses or [],
            section_overlap_score=round(section_overlap_score, 4),
            label_overlap_score=round(label_overlap_score, 4),
        )

    def _all_manual_only(self, category_pool: list[dict[str, Any]]) -> bool:
        return bool(category_pool) and all(self._normalized_template_status(schema.get("template_status", "")) == "manual_only" for schema in category_pool)

    def _pool_match_mode(self, category_pool: list[dict[str, Any]]) -> str:
        modes = [str(schema.get("match_mode", "")).strip() for schema in category_pool if str(schema.get("match_mode", "")).strip()]
        return modes[0] if len(set(modes)) == 1 and modes else ("mixed" if modes else "")

    def _pool_subcategory_match_policy(self, category_pool: list[dict[str, Any]]) -> str:
        policies = [
            self._normalized_subcategory_match_policy(schema.get("subcategory_match_policy", ""))
            for schema in category_pool
        ]
        if len(set(policies)) == 1 and policies:
            return policies[0]
        return "mixed" if policies else ""

    def _hard_gate_failures(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "template_id": candidate.get("template_id"),
                "gate_reasons": list(candidate.get("gate_reasons", [])),
            }
            for candidate in candidates
            if candidate.get("gate_reasons")
        ]

    def _aggregate_discriminator_misses(self, candidates: list[dict[str, Any]]) -> list[str]:
        misses: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            for label in candidate.get("discriminator_misses", []):
                if label in seen:
                    continue
                seen.add(label)
                misses.append(str(label))
        return misses

    def _summarize_fail_reason(self, candidates: list[dict[str, Any]]) -> str:
        failures = [set(candidate.get("gate_reasons", [])) for candidate in candidates if candidate.get("gate_reasons")]
        if not failures:
            return "no_safe_template_match"
        if all(any(reason in reasons for reason in {"missing_required_labels_any", "missing_required_labels_all", "forbidden_labels_present"}) for reasons in failures):
            return "discriminator_miss"
        if all("min_section_overlap" in reasons and reasons <= {"min_section_overlap"} for reasons in failures):
            return "insufficient_section_overlap"
        if all("min_label_overlap" in reasons and reasons <= {"min_label_overlap"} for reasons in failures):
            return "insufficient_label_overlap"
        return "no_safe_template_match"

    def _normalized_template_status(self, value: Any) -> str:
        return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")

    def _normalized_subcategory_match_policy(self, value: Any) -> str:
        normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if normalized == SUBCATEGORY_MATCH_POLICY_LEAF_FAMILY:
            return SUBCATEGORY_MATCH_POLICY_LEAF_FAMILY
        if normalized == SUBCATEGORY_MATCH_POLICY_MIXED_FAMILY:
            return SUBCATEGORY_MATCH_POLICY_MIXED_FAMILY
        return SUBCATEGORY_MATCH_POLICY_EXACT
