from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import FetchResult, GalleryImage, ParsedProduct


@dataclass(slots=True)
class SourceAcquisitionResult:
    model_dir: Path
    source: str
    provider_id: str
    fetch: FetchResult
    parsed: ParsedProduct
    extracted_gallery_count: int = 0
    requested_gallery_photos: int = 0
    downloaded_gallery: list[GalleryImage] = field(default_factory=list)
    gallery_warnings: list[str] = field(default_factory=list)
    gallery_files: list[str] = field(default_factory=list)
    snapshot_provenance: dict[str, Any] = field(default_factory=dict)
