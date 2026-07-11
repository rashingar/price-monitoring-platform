from __future__ import annotations

"""Deterministic Phase 2 SEO primitives.

This module deliberately keeps candidate data separate from published values.
The importer still owns its established CSV contract; richer information is
written to the candidate artifact for review and future OpenCart metadata work.
"""

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping

from .normalize import normalize_for_match, normalize_whitespace, slugify_greek_for_seo

IMAGE_FILENAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-[1-9][0-9]*\.jpg$")


def is_jpeg_bytes(payload: bytes) -> bool:
    """Validate bytes, not just a renamed extension."""
    if len(payload) < 4 or payload[:3] != b"\xff\xd8\xff":
        return False
    try:
        from io import BytesIO
        from PIL import Image
        with Image.open(BytesIO(payload)) as image:
            if image.format != "JPEG":
                return False
            image.verify()
        return True
    except Exception:
        return False


def image_content_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_image_slug_candidate(
    *, brand: str, commercial_series: str = "", primary_model: str = "",
    category_phrase: str = "", primary_spec: str = "",
) -> str:
    """Stable asset identity; excludes mutable retail claims by construction."""
    return "-".join(
        token for token in (
            slugify_greek_for_seo(normalize_whitespace(value))
            for value in (brand, commercial_series, primary_model, category_phrase, primary_spec)
        ) if token
    )


def image_slug_from_identity(identity: Mapping[str, Any], *, brand: str, category_phrase: str) -> str:
    return build_image_slug_candidate(
        brand=brand,
        commercial_series=str(identity.get("commercial_series") or ""),
        primary_model=str(identity.get("primary_model") or ""),
        category_phrase=category_phrase,
        primary_spec=str(identity.get("btu") or ""),
    )


def image_filename(slug: str, position: int) -> str:
    value = f"{slug}-{position}.jpg"
    if not IMAGE_FILENAME_RE.fullmatch(value):
        raise ValueError(f"invalid_image_filename_candidate:{value}")
    return value


def _image_path(model: str, filename: str) -> str:
    return f"catalog/01_main/{model}/{filename}"


def _split_additional(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(":::") if part.strip()]


def gallery_alt(*, product_identity: str, image: Mapping[str, Any], position: int) -> tuple[str, str]:
    source_alt = normalize_whitespace(str(image.get("source_alt") or image.get("alt") or ""))
    role = normalize_for_match(str(image.get("document_role") or image.get("role") or ""))
    if position == 1:
        return product_identity, "product_identity"
    if "energy" in role or "ενεργεια" in role or "energy label" in normalize_for_match(source_alt):
        return f"Ενεργειακή ετικέτα {product_identity}", "document_role"
    # A source-provided visible-view caption is the only free text we reuse.
    if source_alt and len(source_alt) >= 4 and not _same_text(source_alt, product_identity):
        return source_alt, "source_alt"
    return f"{product_identity} – πρόσθετη εικόνα {position}", "position_fallback"


def _same_text(left: str, right: str) -> bool:
    return normalize_for_match(left) == normalize_for_match(right)


def plan_gallery_assets(
    *, model: str, image_slug_candidate: str, images: Iterable[Mapping[str, Any]],
    product_identity: str, published_image: str = "", published_additional_image: str = "",
) -> list[dict[str, Any]]:
    """Plan ordered assets without mutating locked/published OpenCart paths."""
    published_paths = [normalize_whitespace(published_image), *_split_additional(published_additional_image)]
    seen_hashes: set[str] = set()
    planned: list[dict[str, Any]] = []
    for fallback, raw in enumerate(images, start=1):
        image = dict(raw)
        position = int(image.get("position") or fallback)
        filename_candidate = image_filename(image_slug_candidate, position)
        published = published_paths[position - 1] if position <= len(published_paths) else ""
        local_path = normalize_whitespace(str(image.get("local_path") or ""))
        legacy_filename = normalize_whitespace(str(image.get("local_filename") or ""))
        # A freshly downloaded candidate carries filename_candidate.  A local
        # filename without that marker is a pre-Phase-2 legacy fallback.
        is_legacy = bool(
            legacy_filename
            and not normalize_whitespace(str(image.get("filename_candidate") or ""))
            and legacy_filename != filename_candidate
        )
        legacy_path = _image_path(model, legacy_filename) if is_legacy and bool(image.get("jpeg_valid", False)) else ""
        payload_hash = normalize_whitespace(str(image.get("content_hash") or ""))
        duplicate = bool(payload_hash and payload_hash in seen_hashes)
        if payload_hash:
            seen_hashes.add(payload_hash)
        alt, alt_source = gallery_alt(product_identity=product_identity, image=image, position=position)
        filename_published = Path(published).name if published else (legacy_filename if legacy_path else "")
        planned.append({
            "source_url": normalize_whitespace(str(image.get("source_url") or image.get("url") or "")),
            "source_alt": normalize_whitespace(str(image.get("source_alt") or image.get("alt") or "")),
            "position": position,
            "role": "main" if position == 1 else "gallery",
            "filename_candidate": filename_candidate,
            "filename_published": filename_published,
            "filename_locked": bool(published),
            "local_path": local_path,
            "public_path": published or legacy_path or _image_path(model, filename_candidate),
            "jpeg_valid": bool(image.get("jpeg_valid", False)),
            "content_hash": payload_hash,
            "width": image.get("width") or 0,
            "height": image.get("height") or 0,
            "alt": alt,
            "alt_source": alt_source,
            "duplicate_content": duplicate,
        })
    return planned


def validate_gallery_assets(assets: Iterable[Mapping[str, Any]]) -> list[str]:
    materialized = list(assets)
    positions = [int(asset.get("position") or 0) for asset in materialized]
    errors: list[str] = []
    if positions and positions != list(range(1, len(positions) + 1)):
        errors.append("gallery_position_sequence_invalid")
    if len(positions) != len(set(positions)):
        errors.append("gallery_duplicate_positions")
    if materialized and str(materialized[0].get("role")) != "main":
        errors.append("gallery_main_not_position_1")
    paths = [str(asset.get("public_path") or "") for asset in materialized]
    if len(paths) != len(set(paths)):
        errors.append("gallery_duplicate_public_paths")
    for asset in materialized:
        filename = str(asset.get("filename_candidate") or "")
        if not IMAGE_FILENAME_RE.fullmatch(filename):
            errors.append(f"gallery_filename_invalid:{filename}")
        if not asset.get("jpeg_valid", False):
            errors.append(f"gallery_jpeg_invalid:{asset.get('position')}")
    return errors


def description_heading(*, brand: str, identity: Mapping[str, Any]) -> str:
    if str(identity.get("family") or "") != "air_conditioner":
        return ""
    series = normalize_whitespace(str(identity.get("commercial_series") or ""))
    btu = normalize_whitespace(str(identity.get("btu") or ""))
    features = [normalize_whitespace(str(value)) for value in identity.get("verified_features", []) if normalize_whitespace(str(value))]
    if identity.get("wifi") is True:
        features.append("Wi-Fi")
    feature = next((value for value in features if value), "")
    head = normalize_whitespace(" ".join(part for part in (brand, series, btu) if part))
    return f"{head} με {feature}" if head and feature else ""


def section_image_alt(section: Mapping[str, Any], product_identity: str) -> tuple[str, str, str]:
    if bool(section.get("decorative")):
        return "", "decorative", "high"
    title = normalize_whitespace(str(section.get("title") or ""))
    body = normalize_whitespace(str(section.get("body_text") or section.get("paragraph") or ""))
    if title and len(title) >= 4:
        return f"{title} στο {product_identity}", "section_title", "high"
    if body:
        return body[:140], "section_body", "medium"
    return "", "missing_evidence", "low"


def normalize_catalog_text(value: str, *, normalize_models: bool = True, normalize_capacity: bool = True) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn").casefold()
    if normalize_models:
        text = re.sub(r"\b(?=[a-z0-9/-]*[a-z])(?=[a-z0-9/-]*\d)[a-z0-9/-]{3,}\b", "<model>", text)
    if normalize_capacity:
        text = re.sub(r"\b\d{1,3}(?:[.,]\d{3})?\s*btu\b", "<capacity>", text)
    return " ".join(re.sub(r"[^\w<>]+", " ", text).split())


def catalog_similarity(value: str, candidates: Iterable[Mapping[str, Any]], *, field: str, current_model: str = "") -> dict[str, Any]:
    normalized = normalize_catalog_text(value)
    nearest: dict[str, Any] = {"model": "", "score": 0.0, "band": "pass", "field": field}
    for candidate in candidates:
        if str(candidate.get("model") or "") == current_model:
            continue
        other = normalize_catalog_text(str(candidate.get(field) or ""))
        if not normalized or not other:
            continue
        score = SequenceMatcher(None, normalized, other).ratio()
        if score > nearest["score"]:
            nearest = {"model": str(candidate.get("model") or ""), "score": round(score, 4), "band": "fail" if score >= .90 else "warn" if score >= .80 else "pass", "field": field}
    return nearest


def recommend_related_products(current: Mapping[str, Any], catalog: Iterable[Mapping[str, Any]], *, limit: int = 4) -> tuple[list[str], list[dict[str, Any]]]:
    current_model = str(current.get("model") or "")
    seen_models: set[str] = set()
    ranked: list[tuple[tuple[Any, ...], str, str]] = []
    current_identity = current.get("seo_identity") if isinstance(current.get("seo_identity"), Mapping) else {}
    for candidate in catalog:
        model = normalize_whitespace(str(candidate.get("model") or ""))
        if not model or model == current_model or model in seen_models or str(candidate.get("status", "1")) in {"0", "false", "inactive"}:
            continue
        seen_models.add(model)
        identity = candidate.get("seo_identity") if isinstance(candidate.get("seo_identity"), Mapping) else {}
        same_series = bool(current_identity.get("commercial_series") and current_identity.get("commercial_series") == identity.get("commercial_series"))
        same_brand = normalize_for_match(str(current.get("manufacturer") or current.get("brand") or "")) == normalize_for_match(str(candidate.get("manufacturer") or candidate.get("brand") or ""))
        same_category = normalize_for_match(str(current.get("category") or "")) == normalize_for_match(str(candidate.get("category") or ""))
        different_spec = bool(current_identity.get("btu") and current_identity.get("btu") != identity.get("btu")) or str(current.get("mpn") or "") != str(candidate.get("mpn") or "")
        if not (same_series or (same_brand and same_category) or same_category):
            continue
        reason = "same_series" if same_series else "same_brand_category" if same_brand and same_category else "comparable_category"
        ranked.append(((0 if same_series else 1, 0 if same_brand else 1, 0 if different_spec else 1, model), model, reason))
    ranked.sort(key=lambda item: item[0])
    selected = ranked[:limit]
    return [model for _, model, _ in selected], [{"model": model, "reason": reason} for _, model, reason in selected]
