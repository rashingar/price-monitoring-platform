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

DEFAULT_META_DESCRIPTION_MAX_CHARS = 260
DEFAULT_MAX_EMPHASIZED_WORDS_PERCENT = int(MAX_EMPHASIZED_WORD_RATIO * 100)


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
        },
    }
    normalized["authoring"] = normalized_authoring
    return ProductFactorySettings(
        payload=normalized,
        intro_text_default=intro_policy,
        seo_meta_default=seo_policy,
    )


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
    return SeoMetaPolicy(meta_description_max_chars=max_chars)


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
