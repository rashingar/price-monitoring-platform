from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .. import repo_paths
from ..intro_text_markup import MAX_EMPHASIZED_WORD_RATIO
from ..llm_contract import INTRO_MAX_WORDS, INTRO_MIN_WORDS
from ..utils import ensure_directory, read_json, write_json
from .llm_stage_execution import MAX_INTRO_ATTEMPTS

DEFAULT_META_DESCRIPTION_MAX_CHARS = 255
DEFAULT_META_DESCRIPTION_TARGET_MIN_CHARS = 130
DEFAULT_META_DESCRIPTION_TARGET_MAX_CHARS = 170
DEFAULT_META_DESCRIPTION_HARD_MAX_CHARS = 180
DEFAULT_MAX_EMPHASIZED_WORDS_PERCENT = int(MAX_EMPHASIZED_WORD_RATIO * 100)
DEFAULT_IDENTITY_PHASE3_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "families": ["air_conditioner"],
    "mpn_require_verified": True,
    "mpn_allow_manual_override": True,
    "structured_data_artifact_enabled": True,
    "product_feed_artifact_enabled": True,
    "product_feed_identifier_mode": "mpn_only",
    "mpn_overrides": {},
}


class ProductFactorySettingsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IntroTextPolicy:
    min_words: int = INTRO_MIN_WORDS
    max_words: int = INTRO_MAX_WORDS
    max_attempts: int = MAX_INTRO_ATTEMPTS
    max_emphasized_words_percent: int = DEFAULT_MAX_EMPHASIZED_WORDS_PERCENT

    @property
    def max_emphasized_word_ratio(self) -> float:
        return self.max_emphasized_words_percent / 100


@dataclass(frozen=True, slots=True)
class SeoMetaPolicy:
    meta_description_max_chars: int = DEFAULT_META_DESCRIPTION_MAX_CHARS
    target_min_chars: int = DEFAULT_META_DESCRIPTION_TARGET_MIN_CHARS
    target_max_chars: int = DEFAULT_META_DESCRIPTION_TARGET_MAX_CHARS
    hard_max_chars: int = DEFAULT_META_DESCRIPTION_HARD_MAX_CHARS


@dataclass(frozen=True, slots=True)
class ProductFactorySettings:
    payload: dict[str, Any]
    intro_text_default: IntroTextPolicy
    seo_meta_default: SeoMetaPolicy

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.payload)


def default_product_factory_settings_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "seo_health": {
            "ruleset_version": "phase1.0",
            "enforcement_mode": "blockers_only",
            "thresholds": {
                "minimum_score": 80,
                "minimum_coverage": 100,
                "blocking_failures_must_be_zero": True,
            },
        },
        "identity_phase3": deepcopy(DEFAULT_IDENTITY_PHASE3_SETTINGS),
        "authoring": {
            "intro_text": {
                "default": {
                    "min_words": INTRO_MIN_WORDS,
                    "max_words": INTRO_MAX_WORDS,
                    "max_attempts": MAX_INTRO_ATTEMPTS,
                    "max_emphasized_words_percent": DEFAULT_MAX_EMPHASIZED_WORDS_PERCENT,
                },
                "by_source": {},
                "by_category": {},
            },
            "seo_meta": {
                "default": {
                    "meta_description_max_chars": DEFAULT_META_DESCRIPTION_MAX_CHARS,
                    "target_min_chars": DEFAULT_META_DESCRIPTION_TARGET_MIN_CHARS,
                    "target_max_chars": DEFAULT_META_DESCRIPTION_TARGET_MAX_CHARS,
                    "hard_max_chars": DEFAULT_META_DESCRIPTION_HARD_MAX_CHARS,
                },
                "by_source": {},
                "by_category": {},
            },
        },
    }


def load_product_factory_settings(
    *, settings_path: Path | None = None
) -> ProductFactorySettings:
    path = settings_path or repo_paths.PRODUCT_FACTORY_SETTINGS_PATH
    if not path.exists():
        return _validate_settings(default_product_factory_settings_payload())
    try:
        payload = read_json(path)
    except Exception as exc:
        raise ProductFactorySettingsError(
            f"Invalid Product Factory settings JSON: {path}: {exc}"
        ) from exc
    return _validate_settings(payload)


def save_product_factory_settings(
    payload: Mapping[str, Any],
    *,
    settings_path: Path | None = None,
) -> ProductFactorySettings:
    settings = _validate_settings(dict(payload))
    path = settings_path or repo_paths.PRODUCT_FACTORY_SETTINGS_PATH
    ensure_directory(path.parent)
    write_json(path, settings.to_dict())
    return settings


def patch_product_factory_settings(
    patch: Mapping[str, Any],
    *,
    settings_path: Path | None = None,
) -> ProductFactorySettings:
    current = load_product_factory_settings(settings_path=settings_path).to_dict()
    merged = _deep_merge(current, dict(patch))
    return save_product_factory_settings(merged, settings_path=settings_path)


def get_intro_text_policy(
    source: str = "",
    category_id: str = "",
    taxonomy_path: str = "",
    *,
    settings_path: Path | None = None,
) -> IntroTextPolicy:
    del source, category_id, taxonomy_path
    return load_product_factory_settings(settings_path=settings_path).intro_text_default


def get_seo_meta_policy(
    source: str = "",
    category_id: str = "",
    taxonomy_path: str = "",
    *,
    settings_path: Path | None = None,
) -> SeoMetaPolicy:
    del source, category_id, taxonomy_path
    return load_product_factory_settings(settings_path=settings_path).seo_meta_default


def _validate_settings(payload: Mapping[str, Any]) -> ProductFactorySettings:
    if not isinstance(payload, Mapping):
        raise ProductFactorySettingsError(
            "Product Factory settings must be a JSON object."
        )
    normalized = deepcopy(dict(payload))
    normalized.setdefault("schema_version", 1)
    normalized["identity_phase3"] = _validate_identity_phase3_settings(
        normalized.get("identity_phase3", {})
    )
    authoring = normalized.get("authoring")
    if not isinstance(authoring, Mapping):
        raise ProductFactorySettingsError(
            "Product Factory settings must include authoring settings."
        )

    intro_text = authoring.get("intro_text")
    if not isinstance(intro_text, Mapping):
        raise ProductFactorySettingsError("Malformed authoring.intro_text settings.")
    intro_default = intro_text.get("default")
    if not isinstance(intro_default, Mapping):
        raise ProductFactorySettingsError(
            "Malformed authoring.intro_text.default settings."
        )
    intro_policy = _validate_intro_policy(intro_default)
    _require_mapping(intro_text, "by_source", "authoring.intro_text.by_source")
    _require_mapping(intro_text, "by_category", "authoring.intro_text.by_category")

    seo_meta = authoring.get("seo_meta")
    if not isinstance(seo_meta, Mapping):
        raise ProductFactorySettingsError("Malformed authoring.seo_meta settings.")
    seo_default = seo_meta.get("default")
    if not isinstance(seo_default, Mapping):
        raise ProductFactorySettingsError(
            "Malformed authoring.seo_meta.default settings."
        )
    seo_policy = _validate_seo_policy(seo_default)
    _require_mapping(seo_meta, "by_source", "authoring.seo_meta.by_source")
    _require_mapping(seo_meta, "by_category", "authoring.seo_meta.by_category")

    normalized_authoring = dict(authoring)
    normalized_authoring["intro_text"] = {
        **dict(intro_text),
        "default": {
            "min_words": intro_policy.min_words,
            "max_words": intro_policy.max_words,
            "max_attempts": intro_policy.max_attempts,
            "max_emphasized_words_percent": intro_policy.max_emphasized_words_percent,
        },
    }
    normalized_authoring["seo_meta"] = {
        **dict(seo_meta),
        "default": {
            "meta_description_max_chars": seo_policy.meta_description_max_chars,
            "target_min_chars": seo_policy.target_min_chars,
            "target_max_chars": seo_policy.target_max_chars,
            "hard_max_chars": seo_policy.hard_max_chars,
        },
    }
    normalized["authoring"] = normalized_authoring
    return ProductFactorySettings(
        payload=normalized,
        intro_text_default=intro_policy,
        seo_meta_default=seo_policy,
    )


def _validate_identity_phase3_settings(payload: object) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ProductFactorySettingsError("identity_phase3 must be an object.")
    normalized = {**deepcopy(DEFAULT_IDENTITY_PHASE3_SETTINGS), **deepcopy(dict(payload))}
    for key in (
        "enabled",
        "mpn_require_verified",
        "mpn_allow_manual_override",
        "structured_data_artifact_enabled",
        "product_feed_artifact_enabled",
    ):
        if not isinstance(normalized.get(key), bool):
            raise ProductFactorySettingsError(f"identity_phase3.{key} must be a boolean.")
    families = normalized.get("families")
    if not isinstance(families, list) or not all(isinstance(item, str) and item.strip() for item in families):
        raise ProductFactorySettingsError("identity_phase3.families must be a list of non-empty strings.")
    normalized["families"] = [item.strip() for item in families]
    if normalized.get("product_feed_identifier_mode") != "mpn_only":
        raise ProductFactorySettingsError("identity_phase3.product_feed_identifier_mode must be mpn_only.")
    overrides = normalized.get("mpn_overrides")
    if not isinstance(overrides, Mapping):
        raise ProductFactorySettingsError("identity_phase3.mpn_overrides must be an object.")
    for model, override in overrides.items():
        if not isinstance(model, str) or not model.isdigit() or len(model) != 6 or not isinstance(override, Mapping):
            raise ProductFactorySettingsError("identity_phase3.mpn_overrides entries must use a 6-digit model and an object value.")
    normalized["mpn_overrides"] = deepcopy(dict(overrides))
    return normalized


def _validate_intro_policy(payload: Mapping[str, Any]) -> IntroTextPolicy:
    min_words = _require_int(
        payload, "min_words", "authoring.intro_text.default.min_words"
    )
    max_words = _require_int(
        payload, "max_words", "authoring.intro_text.default.max_words"
    )
    max_attempts = _require_int(
        payload, "max_attempts", "authoring.intro_text.default.max_attempts"
    )
    max_emphasized_words_percent = _optional_int(
        payload,
        "max_emphasized_words_percent",
        DEFAULT_MAX_EMPHASIZED_WORDS_PERCENT,
        "authoring.intro_text.default.max_emphasized_words_percent",
    )
    if min_words <= 0:
        raise ProductFactorySettingsError(
            "authoring.intro_text.default.min_words must be a positive integer."
        )
    if max_words <= 0:
        raise ProductFactorySettingsError(
            "authoring.intro_text.default.max_words must be a positive integer."
        )
    if max_words < min_words:
        raise ProductFactorySettingsError(
            "authoring.intro_text.default.max_words must be greater than or equal to min_words."
        )
    if max_words > 500:
        raise ProductFactorySettingsError(
            "authoring.intro_text.default.max_words must be less than or equal to 500."
        )
    if max_attempts < 1 or max_attempts > 10:
        raise ProductFactorySettingsError(
            "authoring.intro_text.default.max_attempts must be between 1 and 10."
        )
    if max_emphasized_words_percent < 0 or max_emphasized_words_percent > 100:
        raise ProductFactorySettingsError(
            "authoring.intro_text.default.max_emphasized_words_percent must be between 0 and 100."
        )
    return IntroTextPolicy(
        min_words=min_words,
        max_words=max_words,
        max_attempts=max_attempts,
        max_emphasized_words_percent=max_emphasized_words_percent,
    )


def _validate_seo_policy(payload: Mapping[str, Any]) -> SeoMetaPolicy:
    max_chars = _require_int(
        payload,
        "meta_description_max_chars",
        "authoring.seo_meta.default.meta_description_max_chars",
    )
    if max_chars < 80 or max_chars > 500:
        raise ProductFactorySettingsError(
            "authoring.seo_meta.default.meta_description_max_chars must be between 80 and 500."
        )
    target_min = _optional_int(
        payload,
        "target_min_chars",
        DEFAULT_META_DESCRIPTION_TARGET_MIN_CHARS,
        "authoring.seo_meta.default.target_min_chars",
    )
    target_max = _optional_int(
        payload,
        "target_max_chars",
        DEFAULT_META_DESCRIPTION_TARGET_MAX_CHARS,
        "authoring.seo_meta.default.target_max_chars",
    )
    hard_max = _optional_int(
        payload,
        "hard_max_chars",
        DEFAULT_META_DESCRIPTION_HARD_MAX_CHARS,
        "authoring.seo_meta.default.hard_max_chars",
    )
    if target_min < 1 or target_max < target_min or hard_max < target_max:
        raise ProductFactorySettingsError(
            "authoring.seo_meta.default target and hard character limits are invalid."
        )
    return SeoMetaPolicy(
        meta_description_max_chars=max_chars,
        target_min_chars=target_min,
        target_max_chars=target_max,
        hard_max_chars=hard_max,
    )


def _require_mapping(payload: Mapping[str, Any], key: str, path: str) -> None:
    if not isinstance(payload.get(key), Mapping):
        raise ProductFactorySettingsError(f"{path} must be an object.")


def _require_int(payload: Mapping[str, Any], key: str, path: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProductFactorySettingsError(f"{path} must be an integer.")
    return value


def _optional_int(payload: Mapping[str, Any], key: str, default: int, path: str) -> int:
    if key not in payload:
        return default
    return _require_int(payload, key, path)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], dict(value))
        else:
            merged[key] = deepcopy(value)
    return merged
