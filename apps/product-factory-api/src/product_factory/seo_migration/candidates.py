from __future__ import annotations

"""Offline loading of Phase 1-3 candidate artifacts.

Candidate discovery is deliberately explicit and filesystem-only.  Nothing in
this module treats ``products/`` as published state or contacts OpenCart.
"""

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


MODEL_RE = re.compile(r"^[0-9]{6}$")


class CandidateLoadError(ValueError):
    pass


def load_candidate_catalog(candidate_dir: Path | str) -> dict[str, dict[str, Any]]:
    root = Path(candidate_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise CandidateLoadError(f"Candidate directory not found: {root}")

    csv_paths = sorted(path for path in root.rglob("*.csv") if path.is_file())
    candidates: dict[str, dict[str, Any]] = {}
    for csv_path in csv_paths:
        for row, headers in _read_csv(csv_path):
            model = str(row.get("model") or "").strip()
            if not MODEL_RE.fullmatch(model):
                continue
            if model in candidates:
                raise CandidateLoadError(
                    f"Duplicate candidate model {model}: "
                    f"{candidates[model]['evidence']['csv']} and {_relative(csv_path, root)}"
                )
            candidates[model] = _candidate_from_row(
                model=model,
                row=row,
                headers=headers,
                csv_path=csv_path,
                root=root,
            )

    if not candidates:
        raise CandidateLoadError(f"No six-digit candidate CSV rows found under: {root}")

    json_index = _index_json_artifacts(root)
    for model, candidate in candidates.items():
        _attach_artifacts(candidate, model=model, root=root, index=json_index)
    return dict(sorted(candidates.items()))


def candidate_catalog_hash(candidates: Mapping[str, Mapping[str, Any]]) -> str:
    payload = [
        {
            "model": model,
            "values": candidate.get("values", {}),
            "availability": candidate.get("availability", []),
            "artifact_hashes": candidate.get("artifact_hashes", {}),
        }
        for model, candidate in sorted(candidates.items())
    ]
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _read_csv(path: Path) -> list[tuple[dict[str, str], list[str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = [str(value or "").strip() for value in (reader.fieldnames or [])]
            return [
                (
                    {str(key or "").strip(): str(value or "") for key, value in row.items()},
                    headers,
                )
                for row in reader
            ]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise CandidateLoadError(f"Could not read candidate CSV {path}: {exc}") from exc


def _candidate_from_row(
    *,
    model: str,
    row: Mapping[str, str],
    headers: list[str],
    csv_path: Path,
    root: Path,
) -> dict[str, Any]:
    filters = {
        header: str(row.get(header) or "")
        for header in sorted(headers)
        if header.startswith("filter_group:")
    }
    additional = _split_multi(row.get("additional_image", ""), ":::")
    related = _split_related(row.get("related_product", ""))
    identifier_values = {
        key: str(row.get(key) or "").strip()
        for key in ("ean", "gtin", "upc", "jan", "isbn")
        if key in headers
    }
    values: dict[str, Any] = {
        "name": str(row.get("name") or ""),
        "description": str(row.get("description") or ""),
        "meta_title": str(row.get("meta_title") or ""),
        "meta_description": str(row.get("meta_description") or ""),
        "meta_keywords": str(
            row.get("meta_keywords") or row.get("meta_keyword") or ""
        ),
        "category": str(row.get("category") or ""),
        "filters": filters,
        "mpn": str(row.get("mpn") or ""),
        "identifiers": identifier_values,
        "related_products": related,
        "main_image": str(row.get("image") or row.get("main_image") or ""),
        "additional_images": additional,
        "seo_keyword": str(row.get("seo_keyword") or ""),
        "canonical_url": str(
            row.get("canonical_url") or row.get("product_url") or ""
        ),
        "manufacturer": str(row.get("manufacturer") or ""),
        "status": str(row.get("status") or ""),
        "price": str(row.get("price") or ""),
        "quantity": str(row.get("quantity") or ""),
        "stock_status": str(row.get("stock_status") or ""),
    }
    availability = {
        "name" if "name" in headers else "",
        "description" if "description" in headers else "",
        "meta_title" if "meta_title" in headers else "",
        "meta_description" if "meta_description" in headers else "",
        "meta_keywords"
        if ("meta_keywords" in headers or "meta_keyword" in headers)
        else "",
        "category" if "category" in headers else "",
        "filters" if filters else "",
        "mpn" if "mpn" in headers else "",
        "identifiers" if identifier_values else "",
        "related_products" if "related_product" in headers else "",
        "main_image" if ("image" in headers or "main_image" in headers) else "",
        "additional_images" if "additional_image" in headers else "",
        "seo_keyword" if "seo_keyword" in headers else "",
        "canonical_url"
        if ("canonical_url" in headers or "product_url" in headers)
        else "",
        "manufacturer" if "manufacturer" in headers else "",
        "status" if "status" in headers else "",
        "price" if "price" in headers else "",
        "quantity" if "quantity" in headers else "",
        "stock_status" if "stock_status" in headers else "",
    }
    return {
        "model": model,
        "values": values,
        "raw_row": dict(row),
        "headers": headers,
        "availability": sorted(value for value in availability if value),
        "normalized": {},
        "phase2": {},
        "phase3": {},
        "structured_data_manifest": None,
        "product_feed_manifest": None,
        "seo_health": None,
        "evidence": {"csv": _relative(csv_path, root)},
        "artifact_hashes": {"csv": _sha256_file(csv_path)},
    }


def _index_json_artifacts(root: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for path in sorted(item for item in root.rglob("*.json") if item.is_file()):
        index.setdefault(path.name, []).append(path)
    return index


def _attach_artifacts(
    candidate: dict[str, Any],
    *,
    model: str,
    root: Path,
    index: Mapping[str, list[Path]],
) -> None:
    artifact_specs = {
        "normalized": f"{model}.normalized.json",
        "structured_data_manifest": f"{model}.product_structured_data.json",
        "product_feed_manifest": f"{model}.product_feed.json",
        "seo_health": f"{model}.seo_health.json",
        "product_identity": f"{model}.product_identity.json",
    }
    for key, filename in artifact_specs.items():
        paths = list(index.get(filename, []))
        if not paths:
            continue
        selected = sorted(paths, key=_artifact_preference)[0]
        payload = _read_json(selected)
        candidate[key] = payload
        candidate["evidence"][key] = _relative(selected, root)
        candidate["artifact_hashes"][key] = _sha256_file(selected)

    normalized = candidate.get("normalized")
    if not isinstance(normalized, Mapping):
        normalized = {}
        candidate["normalized"] = normalized
    deterministic = normalized.get("deterministic_product", {})
    deterministic = deterministic if isinstance(deterministic, Mapping) else {}
    csv_row = normalized.get("csv_row", {})
    if isinstance(csv_row, Mapping):
        # A candidate normalized artifact can contain dynamic filter columns that
        # are not present in older CSV serializers.
        normalized_filters = {
            str(key): value
            for key, value in sorted(csv_row.items())
            if str(key).startswith("filter_group:")
        }
        if normalized_filters:
            candidate["values"]["filters"] = normalized_filters
            _mark_available(candidate, "filters")

    phase2_assets = normalized.get("image_assets", deterministic.get("image_assets", []))
    phase2_sections = normalized.get(
        "presentation_section_image_metadata",
        deterministic.get("presentation_section_image_metadata", []),
    )
    image_assets = list(phase2_assets) if isinstance(phase2_assets, list) else []
    sections = list(phase2_sections) if isinstance(phase2_sections, list) else []
    links = normalized.get("internal_links", deterministic.get("internal_links", {}))
    links = dict(links) if isinstance(links, Mapping) else {}
    candidate["phase2"] = {
        "image_assets": image_assets,
        "sections": sections,
        "internal_links": links,
        "catalog_similarity": dict(normalized.get("catalog_similarity", {}))
        if isinstance(normalized.get("catalog_similarity"), Mapping)
        else {},
        "description_heading": str(
            normalized.get("description_heading")
            or deterministic.get("description_heading")
            or ""
        ),
        "catalog_available": bool(normalized.get("catalog_similarity")),
    }
    if image_assets:
        candidate["values"]["image_alt_metadata"] = [
            {
                "position": asset.get("position"),
                "path": asset.get("public_path"),
                "alt": asset.get("alt"),
                "source": asset.get("alt_source"),
            }
            for asset in image_assets
        ]
        candidate["values"]["gallery_candidates"] = _gallery_candidates(
            model, image_assets, candidate["values"]
        )
        _mark_available(candidate, "image_alt_metadata", "gallery_candidates")

    seo_identity = deterministic.get("seo_identity", {})
    seo_identity = seo_identity if isinstance(seo_identity, Mapping) else {}
    slug_candidate = str(
        deterministic.get("seo_keyword_candidate")
        or seo_identity.get("seo_keyword_candidate")
        or ""
    )
    if slug_candidate:
        candidate["values"]["seo_keyword_candidate"] = slug_candidate
        _mark_available(candidate, "seo_keyword_candidate")

    product_identity = candidate.get("product_identity")
    if not isinstance(product_identity, Mapping):
        product_identity = deterministic.get("product_identity", {})
    phase3 = normalized.get("phase3", {})
    phase3 = dict(phase3) if isinstance(phase3, Mapping) else {}
    if product_identity:
        phase3["identity"] = dict(product_identity)
        if isinstance(deterministic, dict):
            deterministic["product_identity"] = dict(product_identity)
    if candidate.get("structured_data_manifest") is not None:
        phase3["structured_data"] = candidate["structured_data_manifest"]
        phase3["structured_data_enabled"] = True
    if candidate.get("product_feed_manifest") is not None:
        phase3["feed"] = candidate["product_feed_manifest"]
        phase3["product_feed_enabled"] = True
    if phase3:
        phase3.setdefault("enabled", True)
    candidate["phase3"] = phase3
    candidate["deterministic_product"] = dict(deterministic)

    if candidate.get("structured_data_manifest") is not None:
        candidate["values"]["structured_data_manifest"] = candidate[
            "structured_data_manifest"
        ]
        _mark_available(candidate, "structured_data_manifest")
    if candidate.get("product_feed_manifest") is not None:
        candidate["values"]["product_feed_manifest"] = candidate[
            "product_feed_manifest"
        ]
        _mark_available(candidate, "product_feed_manifest")


def _gallery_candidates(
    model: str,
    assets: list[Mapping[str, Any]],
    values: Mapping[str, Any],
) -> list[dict[str, Any]]:
    current_paths = [
        str(values.get("main_image") or ""),
        *[str(value) for value in values.get("additional_images", [])],
    ]
    result: list[dict[str, Any]] = []
    for fallback, asset in enumerate(assets, start=1):
        position = int(asset.get("position") or fallback)
        current = current_paths[position - 1] if position <= len(current_paths) else ""
        filename = str(asset.get("filename_candidate") or "")
        if filename:
            candidate_path = f"catalog/01_main/{model}/{filename}"
        else:
            candidate_path = str(asset.get("public_path") or "")
        result.append(
            {
                "position": position,
                "role": "main" if position == 1 else "gallery",
                "current_path": current,
                "candidate_path": candidate_path,
                "local_path": str(asset.get("local_path") or ""),
                "content_hash": str(asset.get("content_hash") or ""),
                "current_source_hash": str(
                    asset.get("current_source_hash")
                    or asset.get("published_source_hash")
                    or ""
                ),
                "jpeg_valid": bool(asset.get("jpeg_valid", False)),
                "alt": str(asset.get("alt") or ""),
            }
        )
    return result


def _artifact_preference(path: Path) -> tuple[int, int, str]:
    parts = {part.casefold() for part in path.parts}
    return (
        0 if "candidate" in parts else 1,
        len(path.parts),
        str(path).casefold(),
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateLoadError(f"Could not read candidate JSON {path}: {exc}") from exc


def _mark_available(candidate: dict[str, Any], *fields: str) -> None:
    candidate["availability"] = sorted(
        set(candidate.get("availability", [])) | set(fields)
    )


def _split_multi(value: object, separator: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(separator) if part.strip()]


def _split_related(value: object) -> list[str]:
    text = str(value or "").replace(":::", ",")
    return [part.strip() for part in text.split(",") if part.strip()]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.name
