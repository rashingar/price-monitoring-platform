from __future__ import annotations

"""Reusable deterministic SEO identity primitives.

Category modules resolve their evidence into :class:`SeoIdentity`; this module
then owns generic title budgeting and slug locking.  Keeping these mechanics
separate from CSV serialization lets new category profiles opt in safely.
"""

from dataclasses import asdict, dataclass, field
import re
from typing import Iterable

from .normalize import normalize_whitespace, slugify_greek_for_seo


SEO_TITLE_SUFFIX = " | eTranoulis"
SEO_TITLE_PASS_MAX = 65
SEO_TITLE_WARN_MAX = 75
SEO_KEYWORD_MAX_LENGTH = 96
SEO_KEYWORD_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class SeoIdentity:
    """Deterministic product identity with field-level provenance labels."""

    family: str = ""
    commercial_series: str = ""
    primary_model: str = ""
    set_model: str = ""
    indoor_model: str = ""
    outdoor_model: str = ""
    inverter: bool | None = None
    wifi: bool | None = None
    ionizer: bool | None = None
    published_seo_keyword: str = ""
    seo_keyword_candidate: str = ""
    seo_keyword_locked: bool = False
    category_phrase: str = ""
    btu: str = ""
    cooling_energy_class: str = ""
    heating_energy_class: str = ""
    verified_features: tuple[str, ...] = ()
    provenance: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["verified_features"] = list(self.verified_features)
        return payload


@dataclass(frozen=True, slots=True)
class MetaTitleComponent:
    value: str
    required: bool = False
    priority: int = 0
    key: str = ""


def compose_meta_title(
    components: Iterable[MetaTitleComponent],
    *,
    suffix: str = SEO_TITLE_SUFFIX,
    pass_max_chars: int = SEO_TITLE_PASS_MAX,
) -> str:
    """Compose a title without splitting tokens and drop low-priority options.

    Required components are never removed.  When required identity alone is
    longer than the budget, it is intentionally retained so health reporting
    can surface the exceptional length instead of silently losing identity.
    """

    deduped: list[MetaTitleComponent] = []
    seen: set[str] = set()
    for component in components:
        value = normalize_whitespace(component.value)
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        deduped.append(
            MetaTitleComponent(
                value=value,
                required=component.required,
                priority=component.priority,
                key=component.key,
            )
        )

    retained = list(deduped)
    optional_indexes = sorted(
        (index for index, item in enumerate(retained) if not item.required),
        key=lambda index: retained[index].priority,
        reverse=True,
    )
    while optional_indexes and _title_length(retained, suffix) > pass_max_chars:
        retained.pop(optional_indexes.pop(0))
        optional_indexes = sorted(
            (index for index, item in enumerate(retained) if not item.required),
            key=lambda index: retained[index].priority,
            reverse=True,
        )
    title = normalize_whitespace(" ".join(item.value for item in retained))
    return f"{title}{suffix}" if title else ""


def meta_title_length_status(title: str) -> str:
    length = len(normalize_whitespace(title))
    if length <= SEO_TITLE_PASS_MAX:
        return "pass"
    if length <= SEO_TITLE_WARN_MAX:
        return "warn"
    return "fail"


def build_seo_keyword_candidate(
    parts: Iterable[str],
    *,
    max_length: int = SEO_KEYWORD_MAX_LENGTH,
) -> str:
    """Build a stable URL-safe candidate without truncating a model token."""

    tokens: list[str] = []
    for part in parts:
        token = slugify_greek_for_seo(normalize_whitespace(part))
        if token and token not in tokens:
            tokens.append(token)
    while tokens and len("-".join(tokens)) > max_length:
        # Category profiles order lower-value, optional terms last.
        tokens.pop()
    return "-".join(tokens)


def lock_seo_keyword(candidate: str, published: str = "") -> tuple[str, bool]:
    published_value = normalize_whitespace(published)
    return (published_value, True) if published_value else (candidate, False)


def valid_seo_keyword(value: str) -> bool:
    return bool(SEO_KEYWORD_RE.fullmatch(normalize_whitespace(value)))


def _title_length(components: list[MetaTitleComponent], suffix: str) -> int:
    return len(normalize_whitespace(" ".join(item.value for item in components)) + suffix)
