from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .seo_phase2 import is_jpeg_bytes


OPEN_CART_GALLERY_PREFIX = ("catalog", "01_main")
ETRANOULIS_IMAGE_HOSTS = {"etranoulis.gr", "www.etranoulis.gr"}


class PublishGalleryResolutionError(RuntimeError):
    """Raised when a rendered CSV does not safely resolve to prepared images."""


@dataclass(frozen=True)
class ResolvedPublishImage:
    role: str
    position: int
    csv_public_path: str
    filename: str
    local_path: Path


def resolve_publish_gallery_assets(
    model: str,
    published_csv_path: Path,
    work_root: Path,
) -> list[ResolvedPublishImage]:
    """Resolve and validate the gallery assets explicitly referenced by one CSV row."""

    csv_path = Path(published_csv_path)
    if not csv_path.exists() or not csv_path.is_file():
        raise PublishGalleryResolutionError(
            f"current job product CSV does not exist: {csv_path}"
        )
    if csv_path.stat().st_size <= 0:
        raise PublishGalleryResolutionError(
            f"current job product CSV is empty: {csv_path}"
        )

    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise PublishGalleryResolutionError(
            f"could not read current job product CSV {csv_path}: {exc}"
        ) from exc

    for field in ("model", "image"):
        if field not in fieldnames:
            raise PublishGalleryResolutionError(
                f"current job product CSV is missing required column: {field}"
            )

    matching_rows = [row for row in rows if row.get("model") == model]
    if not matching_rows:
        raise PublishGalleryResolutionError(f"no CSV row found for model {model}")
    if len(matching_rows) > 1:
        raise PublishGalleryResolutionError(
            f"multiple CSV rows found for model {model}"
        )

    row = matching_rows[0]
    main_reference = str(row.get("image") or "").strip()
    if not main_reference:
        raise PublishGalleryResolutionError(
            f"empty main gallery image referenced by CSV for model {model}"
        )

    references: list[tuple[str, int, str]] = [("main", 1, main_reference)]
    additional_value = str(row.get("additional_image") or "")
    if additional_value.strip():
        for position, reference in enumerate(additional_value.split(":::"), start=2):
            normalized_reference = reference.strip()
            if not normalized_reference:
                raise PublishGalleryResolutionError(
                    "unsafe additional gallery image path in CSV: "
                    f"{additional_value}"
                )
            references.append(("additional", position, normalized_reference))

    gallery_root = (Path(work_root) / model / "scrape" / "gallery").resolve()
    resolved: list[ResolvedPublishImage] = []
    seen_local_paths: set[Path] = set()
    for role, position, reference in references:
        filename = _filename_from_public_path(
            reference, model=model, role=role, position=position
        )
        local_path = (gallery_root / filename).resolve()
        if not _is_within(local_path, gallery_root):
            raise PublishGalleryResolutionError(
                f"unsafe {_role_label(role, position)} path in CSV: {reference}"
            )
        if local_path in seen_local_paths:
            raise PublishGalleryResolutionError(
                "duplicate gallery image reference in CSV: "
                f"{reference} ({_role_label(role, position)})"
            )
        seen_local_paths.add(local_path)
        _validate_local_asset(
            local_path, reference=reference, role=role, position=position
        )
        resolved.append(
            ResolvedPublishImage(
                role=role,
                position=position,
                csv_public_path=reference,
                filename=filename,
                local_path=local_path,
            )
        )
    return resolved


def _filename_from_public_path(
    reference: str,
    *,
    model: str,
    role: str,
    position: int,
) -> str:
    try:
        candidate = _path_from_csv_reference(reference)
    except PublishGalleryResolutionError as exc:
        raise PublishGalleryResolutionError(
            f"unsafe {_role_label(role, position)} path in CSV: {reference}"
        ) from exc
    if "\\" in candidate or "\x00" in candidate:
        raise PublishGalleryResolutionError(
            f"unsafe {_role_label(role, position)} path in CSV: {reference}"
        )
    parts = [part for part in candidate.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise PublishGalleryResolutionError(
            f"unsafe {_role_label(role, position)} path in CSV: {reference}"
        )
    if parts[:1] == ["image"]:
        parts = parts[1:]
    if len(parts) != 4 or tuple(parts[:2]) != OPEN_CART_GALLERY_PREFIX:
        raise PublishGalleryResolutionError(
            f"unsafe {_role_label(role, position)} path in CSV: {reference}"
        )
    if parts[2] != model:
        raise PublishGalleryResolutionError(
            "mismatched product-code folder for "
            f"{_role_label(role, position)} in CSV: {reference}"
        )
    filename = parts[3]
    if not filename or filename in {".", ".."} or Path(filename).name != filename:
        raise PublishGalleryResolutionError(
            f"unsafe {_role_label(role, position)} path in CSV: {reference}"
        )
    if Path(filename).suffix.lower() != ".jpg":
        raise PublishGalleryResolutionError(
            f"non-JPG {_role_label(role, position)} path in CSV: {reference}"
        )
    return filename


def _path_from_csv_reference(reference: str) -> str:
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc:
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme not in {"http", "https"}
            or host not in ETRANOULIS_IMAGE_HOSTS
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise PublishGalleryResolutionError(
                f"unsafe gallery image path in CSV: {reference}"
            )
        return unquote(parsed.path)
    return unquote(reference)


def _validate_local_asset(
    local_path: Path,
    *,
    reference: str,
    role: str,
    position: int,
) -> None:
    label = _role_label(role, position)
    if not local_path.exists() or not local_path.is_file():
        raise PublishGalleryResolutionError(
            f"missing {label} referenced by CSV: {reference}"
        )
    if local_path.stat().st_size <= 0:
        raise PublishGalleryResolutionError(
            f"empty {label} referenced by CSV: {reference}"
        )
    if local_path.suffix.lower() != ".jpg":
        raise PublishGalleryResolutionError(
            f"non-JPG {label} referenced by CSV: {reference}"
        )
    try:
        payload = local_path.read_bytes()
    except OSError as exc:
        raise PublishGalleryResolutionError(
            f"could not read {label} referenced by CSV: {reference}: {exc}"
        ) from exc
    if not is_jpeg_bytes(payload):
        raise PublishGalleryResolutionError(
            f"invalid JPEG bytes for {label} referenced by CSV: {reference}"
        )


def _role_label(role: str, position: int) -> str:
    return "main gallery image" if role == "main" else f"additional gallery image {position}"


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True
