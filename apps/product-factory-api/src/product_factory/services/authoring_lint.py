from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from ..intro_text_markup import strip_intro_text_markup
from ..normalize import normalize_whitespace

INTRO_TEXT_STAGE = "intro_text"
SEO_META_STAGE = "seo_meta"

_SENTENCE_RE = re.compile(r"[^.!;?。！？]+[.!;?。！？]?")
_TOKEN_RE = re.compile(r"[A-Za-z0-9Α-Ωα-ωΆ-Ώά-ώ._/-]+", re.UNICODE)
_STOPWORDS = {
    "και",
    "με",
    "για",
    "στο",
    "στη",
    "στην",
    "στον",
    "το",
    "τη",
    "την",
    "ο",
    "η",
    "ένα",
    "μια",
    "που",
    "ως",
    "σε",
    "από",
    "είναι",
}


@dataclass(frozen=True, slots=True)
class AuthoringLintWarning:
    code: str
    stage: str
    field: str
    message: str
    phrase: str = ""
    snippet: str = ""

    def to_dict(self) -> dict[str, str]:
        payload = {
            "code": self.code,
            "stage": self.stage,
            "field": self.field,
            "message": self.message,
        }
        if self.phrase:
            payload["phrase"] = self.phrase
        if self.snippet:
            payload["snippet"] = self.snippet
        return payload


def lint_intro_text_output(
    intro_text: str, product: dict[str, Any]
) -> list[AuthoringLintWarning]:
    return _lint_output(
        stage=INTRO_TEXT_STAGE,
        field="intro_text",
        text=strip_intro_text_markup(intro_text),
        product=product,
        category_code="intro_text_duplicate_category_phrase",
    )


def lint_seo_meta_description(
    meta_description: str, product: dict[str, Any]
) -> list[AuthoringLintWarning]:
    return _lint_output(
        stage=SEO_META_STAGE,
        field="product.meta_description",
        text=meta_description,
        product=product,
        category_code="seo_meta_duplicate_category_phrase",
    )


def lint_trace_payload(
    *,
    stage: str,
    output_path: str,
    trace_path: str,
    warnings: list[AuthoringLintWarning],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "stage": stage,
        "output_path": output_path,
        "trace_path": trace_path,
        "warning_count": len(warnings),
        "warning_codes": _unique([warning.code for warning in warnings]),
        "warnings": [warning.to_dict() for warning in warnings],
    }


def _lint_output(
    *,
    stage: str,
    field: str,
    text: str,
    product: dict[str, Any],
    category_code: str,
) -> list[AuthoringLintWarning]:
    normalized_text = normalize_whitespace(text)
    if not normalized_text:
        return []

    warnings: list[AuthoringLintWarning] = []
    prose_subject = _clean_product_value(product.get("prose_subject"))
    copy_name = _clean_product_value(product.get("copy_name"))
    preferred_identifier = _clean_product_value(product.get("preferred_identifier"))
    model_name = _clean_product_value(product.get("model_name"))
    mpn = _clean_product_value(product.get("mpn"))
    category = _clean_product_value(product.get("category"))
    subject = prose_subject or copy_name

    if subject:
        subject_occurrences = _phrase_occurrences(normalized_text, subject)
        if _has_close_occurrences(subject_occurrences, window_tokens=24):
            warnings.append(
                _warning(
                    "authoring_duplicate_prose_subject",
                    stage,
                    field,
                    "Product prose subject appears more than once in a short span.",
                    subject,
                    normalized_text,
                )
            )

    if subject and category:
        subject_contains_category = _contains_phrase(subject, category)
        copy_name_contains_category = copy_name and _contains_phrase(copy_name, category)
        if subject_contains_category or copy_name_contains_category:
            if _phrase_occurrences(normalized_text, f"{subject} {category}"):
                warnings.append(
                    _warning(
                        "authoring_duplicate_category_near_subject",
                        stage,
                        field,
                        "Category appears immediately after an identity phrase that already contains it.",
                        category,
                        normalized_text,
                    )
                )

    if category and _phrase_count(_first_sentence(normalized_text), category) >= 2:
        warnings.append(
            _warning(
                category_code,
                stage,
                field,
                "Category phrase appears more than once in the first sentence.",
                category,
                normalized_text,
            )
        )

    for identifier in _unique([preferred_identifier, model_name, mpn]):
        if not identifier:
            continue
        if any(
            _phrase_count(sentence, identifier) >= 2
            for sentence in _sentences(normalized_text)
        ):
            warnings.append(
                _warning(
                    "authoring_duplicate_identifier_phrase",
                    stage,
                    field,
                    "Model or MPN phrase appears more than once in the same sentence.",
                    identifier,
                    normalized_text,
                )
            )
            break

    repeated_phrase = _find_repeated_short_phrase(normalized_text)
    if repeated_phrase:
        warnings.append(
            _warning(
                "authoring_repeated_short_phrase",
                stage,
                field,
                "Exact short phrase is repeated within a short distance.",
                repeated_phrase,
                normalized_text,
            )
        )

    return _dedupe_warnings(warnings)


def _warning(
    code: str,
    stage: str,
    field: str,
    message: str,
    phrase: str,
    text: str,
) -> AuthoringLintWarning:
    return AuthoringLintWarning(
        code=code,
        stage=stage,
        field=field,
        message=message,
        phrase=phrase,
        snippet=_snippet_for_phrase(text, phrase),
    )


def _clean_product_value(value: object) -> str:
    return normalize_whitespace(str(value or ""))


def _normalize_for_match(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_accents = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return normalize_whitespace(without_accents)


def _phrase_occurrences(text: str, phrase: str) -> list[int]:
    normalized_text = _normalize_for_match(text)
    normalized_phrase = _normalize_for_match(phrase)
    if not normalized_text or not normalized_phrase:
        return []
    positions: list[int] = []
    pattern = re.compile(rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)")
    for match in pattern.finditer(normalized_text):
        positions.append(_token_count(normalized_text[: match.start()]))
    return positions


def _phrase_count(text: str, phrase: str) -> int:
    return len(_phrase_occurrences(text, phrase))


def _contains_phrase(value: str, phrase: str) -> bool:
    return bool(_phrase_occurrences(value, phrase))


def _has_close_occurrences(positions: list[int], *, window_tokens: int) -> bool:
    return any(
        second - first <= window_tokens
        for first, second in zip(positions, positions[1:], strict=False)
    )


def _first_sentence(text: str) -> str:
    sentences = _sentences(text)
    return sentences[0] if sentences else text


def _sentences(text: str) -> list[str]:
    return [
        normalize_whitespace(match.group(0))
        for match in _SENTENCE_RE.finditer(text)
        if normalize_whitespace(match.group(0))
    ]


def _tokens(text: str) -> list[str]:
    return [_normalize_for_match(token) for token in _TOKEN_RE.findall(text)]


def _token_count(text: str) -> int:
    return len(_tokens(text))


def _find_repeated_short_phrase(text: str) -> str:
    tokens = _tokens(text)
    if len(tokens) < 4:
        return ""
    for size in range(5, 1, -1):
        seen: dict[tuple[str, ...], int] = {}
        for index in range(0, len(tokens) - size + 1):
            phrase_tokens = tuple(tokens[index : index + size])
            if not _is_signal_phrase(phrase_tokens):
                continue
            previous = seen.get(phrase_tokens)
            if previous is not None and index - previous <= 10:
                return " ".join(phrase_tokens)
            seen.setdefault(phrase_tokens, index)
    return ""


def _is_signal_phrase(tokens: tuple[str, ...]) -> bool:
    signal_tokens = [
        token
        for token in tokens
        if token not in _STOPWORDS
        and (len(token) > 3 or any(char.isdigit() for char in token))
    ]
    return len(set(signal_tokens)) >= 2


def _snippet_for_phrase(text: str, phrase: str) -> str:
    if not phrase:
        return text[:160]
    normalized_text = _normalize_for_match(text)
    normalized_phrase = _normalize_for_match(phrase)
    index = normalized_text.find(normalized_phrase)
    if index < 0:
        return text[:160]
    start = max(0, index - 60)
    end = min(len(text), index + len(phrase) + 60)
    return text[start:end].strip()


def _dedupe_warnings(
    warnings: list[AuthoringLintWarning],
) -> list[AuthoringLintWarning]:
    deduped: list[AuthoringLintWarning] = []
    seen: set[tuple[str, str]] = set()
    for warning in warnings:
        key = (warning.code, _normalize_for_match(warning.phrase))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(warning)
    return deduped


def _unique(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values
