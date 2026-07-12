import csv
from pathlib import Path

import pytest

from tools.opencart_upload_images import (
    UploadError,
    build_plan,
    chunked_file_paths,
    validate_besco_files,
)


def test_chunked_file_paths_splits_large_besco_uploads_into_batches_under_21() -> None:
    paths = [f"besco{i}.jpg" for i in range(1, 36)]

    batches = chunked_file_paths(paths, 20)

    assert len(batches) == 2
    assert len(batches[0]) == 20
    assert len(batches[1]) == 15
    assert all(len(batch) < 21 for batch in batches)
    assert batches[0][0] == "besco1.jpg"
    assert batches[1][-1] == "besco35.jpg"


def test_validate_besco_files_allows_sparse_video_first_section_names(tmp_path) -> None:
    besco_dir = tmp_path / "bescos"
    besco_dir.mkdir()
    for name in ["besco2.jpg", "besco3.jpg", "besco10.jpg"]:
        (besco_dir / name).write_bytes(b"jpg")

    files = validate_besco_files(besco_dir)

    assert [path.name for path in files] == ["besco2.jpg", "besco3.jpg", "besco10.jpg"]


def test_validate_besco_files_rejects_non_section_numbered_names(tmp_path) -> None:
    besco_dir = tmp_path / "bescos"
    besco_dir.mkdir()
    (besco_dir / "besco2.jpg").write_bytes(b"jpg")
    (besco_dir / "hero.jpg").write_bytes(b"jpg")

    with pytest.raises(UploadError, match="section-numbered"):
        validate_besco_files(besco_dir)


def test_upload_plan_uses_only_csv_referenced_phase2_gallery_assets(tmp_path) -> None:
    from PIL import Image

    model = "123456"
    gallery = tmp_path / "work" / "123456" / "scrape" / "gallery"
    gallery.mkdir(parents=True)
    filenames = [
        "midea-solunar-ef-12rd1h-klimatistiko-12000-btu-1.jpg",
        "midea-solunar-ef-12rd1h-klimatistiko-12000-btu-2.jpg",
        "unrelated-gallery-image.jpg",
    ]
    for filename in filenames:
        Image.new("RGB", (1, 1), "white").save(
            gallery / filename,
            format="JPEG",
        )
    product_file = tmp_path / "products" / f"{model}.csv"
    product_file.parent.mkdir()
    with product_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["model", "image", "additional_image"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "model": model,
                "image": f"catalog/01_main/{model}/{filenames[0]}",
                "additional_image": f"catalog/01_main/{model}/{filenames[1]}",
            }
        )

    plan = build_plan(
        tmp_path,
        model,
        "https://www.etranoulis.gr",
        current_job_product_file=product_file,
    )

    assert [Path(path).name for path in plan["gallery"]["local_files"]] == filenames[:2]
    assert plan["gallery"]["main_image"] == f"catalog/01_main/{model}/{filenames[0]}"
    assert plan["gallery"]["additional_image"] == f"catalog/01_main/{model}/{filenames[1]}"
    assert filenames[2] not in plan["gallery"]["local_files"]

    (gallery / filenames[1]).write_bytes(b"RIFFxxxxWEBP")
    with pytest.raises(UploadError, match="invalid JPEG bytes"):
        build_plan(
            tmp_path,
            model,
            "https://www.etranoulis.gr",
            current_job_product_file=product_file,
        )
