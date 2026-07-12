from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from product_factory.publish_gallery_assets import (
    PublishGalleryResolutionError,
    resolve_publish_gallery_assets,
)


MODEL = "000003"


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    work_root = tmp_path / "work"
    gallery = work_root / MODEL / "scrape" / "gallery"
    gallery.mkdir(parents=True)
    csv_path = tmp_path / "products" / f"{MODEL}.csv"
    csv_path.parent.mkdir()
    return work_root, gallery, csv_path


def _write_csv(csv_path: Path, rows: list[dict[str, str]]) -> None:
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["model", "image", "additional_image"])
        writer.writeheader()
        writer.writerows(rows)


def _public_path(filename: str) -> str:
    return f"catalog/01_main/{MODEL}/{filename}"


def _write_image(path: Path, image_format: str = "JPEG") -> None:
    Image.new("RGB", (2, 2), "white").save(path, format=image_format)


@pytest.mark.parametrize(
    "filename",
    [
        "toyotomi-erai-otn-otg-24qinv-klimatistiko-24000-btu-1.jpg",
        f"{MODEL}-1.jpg",
    ],
)
def test_resolver_accepts_descriptive_and_legacy_csv_filenames(
    tmp_path: Path, filename: str
) -> None:
    work_root, gallery, csv_path = _paths(tmp_path)
    _write_image(gallery / filename)
    _write_csv(csv_path, [{"model": MODEL, "image": _public_path(filename), "additional_image": ""}])

    assets = resolve_publish_gallery_assets(MODEL, csv_path, work_root)

    assert [(asset.role, asset.position, asset.filename) for asset in assets] == [
        ("main", 1, filename)
    ]


def test_resolver_preserves_additional_csv_order_and_supports_etranoulis_urls(
    tmp_path: Path,
) -> None:
    work_root, gallery, csv_path = _paths(tmp_path)
    filenames = ["descriptive-1.jpg", "descriptive-2.jpg", "descriptive-3.jpg"]
    for filename in filenames:
        _write_image(gallery / filename)
    full_url = f"https://www.etranoulis.gr/image/{_public_path(filenames[0])}"
    _write_csv(
        csv_path,
        [
            {
                "model": MODEL,
                "image": full_url,
                "additional_image": ":::".join(
                    [f"image/{_public_path(filenames[1])}", f"/{_public_path(filenames[2])}"]
                ),
            }
        ],
    )

    assets = resolve_publish_gallery_assets(MODEL, csv_path, work_root)

    assert [asset.filename for asset in assets] == filenames
    assert [asset.position for asset in assets] == [1, 2, 3]
    assert assets[0].csv_public_path == full_url


def test_publish_preflight_uses_the_csv_reference_not_a_legacy_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from product_factory.services import publish_execution

    work_root, gallery, csv_path = _paths(tmp_path)
    descriptive = "toyotomi-erai-otn-otg-24qinv-klimatistiko-24000-btu-1.jpg"
    _write_image(gallery / descriptive)
    _write_csv(csv_path, [{"model": MODEL, "image": _public_path(descriptive), "additional_image": ""}])
    script_path = tmp_path / "tools" / "run_opencart_pipeline.sh"
    script_path.parent.mkdir()
    script_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    monkeypatch.setattr(publish_execution.shutil, "which", lambda _name: "/usr/bin/bash")
    monkeypatch.setattr(
        publish_execution.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    stage, message, bash_path = publish_execution._preflight_publish_environment(
        model=MODEL,
        script_path=script_path,
        published_csv_path=csv_path,
        work_root=work_root,
        repo_root=tmp_path,
    )

    assert (stage, message, bash_path) == (None, None, "/usr/bin/bash")
    assert not (gallery / f"{MODEL}-1.jpg").exists()


def test_resolver_rejects_missing_main_or_additional_assets(tmp_path: Path) -> None:
    work_root, gallery, csv_path = _paths(tmp_path)
    _write_image(gallery / "main.jpg")
    _write_csv(
        csv_path,
        [
            {
                "model": MODEL,
                "image": _public_path("main.jpg"),
                "additional_image": _public_path("missing.jpg"),
            }
        ],
    )

    with pytest.raises(PublishGalleryResolutionError, match="missing additional gallery image 2"):
        resolve_publish_gallery_assets(MODEL, csv_path, work_root)

    _write_csv(csv_path, [{"model": MODEL, "image": _public_path("missing.jpg"), "additional_image": ""}])
    with pytest.raises(PublishGalleryResolutionError, match="missing main gallery image"):
        resolve_publish_gallery_assets(MODEL, csv_path, work_root)


@pytest.mark.parametrize("image_format", ["PNG", "WEBP"])
def test_resolver_rejects_renamed_non_jpeg_bytes(
    tmp_path: Path, image_format: str
) -> None:
    work_root, gallery, csv_path = _paths(tmp_path)
    filename = "renamed.jpg"
    _write_image(gallery / filename, image_format)
    _write_csv(csv_path, [{"model": MODEL, "image": _public_path(filename), "additional_image": ""}])

    with pytest.raises(PublishGalleryResolutionError, match="invalid JPEG bytes"):
        resolve_publish_gallery_assets(MODEL, csv_path, work_root)


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("", "empty main gallery image"),
        (f"catalog/01_main/999999/main.jpg", "mismatched product-code folder"),
        (f"catalog/01_main/{MODEL}/../main.jpg", "unsafe main gallery image path"),
        (f"catalog/01_main/{MODEL}/main.png", "non-JPG main gallery image path"),
    ],
)
def test_resolver_rejects_unsafe_or_invalid_main_csv_paths(
    tmp_path: Path, image: str, expected: str
) -> None:
    work_root, _gallery, csv_path = _paths(tmp_path)
    _write_csv(csv_path, [{"model": MODEL, "image": image, "additional_image": ""}])

    with pytest.raises(PublishGalleryResolutionError, match=expected):
        resolve_publish_gallery_assets(MODEL, csv_path, work_root)


def test_resolver_rejects_duplicate_references_and_invalid_csv_rows(tmp_path: Path) -> None:
    work_root, gallery, csv_path = _paths(tmp_path)
    _write_image(gallery / "main.jpg")
    main_path = _public_path("main.jpg")
    _write_csv(
        csv_path,
        [{"model": MODEL, "image": main_path, "additional_image": main_path}],
    )
    with pytest.raises(PublishGalleryResolutionError, match="duplicate gallery image reference"):
        resolve_publish_gallery_assets(MODEL, csv_path, work_root)

    _write_csv(csv_path, [{"model": "000004", "image": main_path, "additional_image": ""}])
    with pytest.raises(PublishGalleryResolutionError, match="no CSV row found"):
        resolve_publish_gallery_assets(MODEL, csv_path, work_root)

    _write_csv(
        csv_path,
        [
            {"model": MODEL, "image": main_path, "additional_image": ""},
            {"model": MODEL, "image": main_path, "additional_image": ""},
        ],
    )
    with pytest.raises(PublishGalleryResolutionError, match="multiple CSV rows found"):
        resolve_publish_gallery_assets(MODEL, csv_path, work_root)
