import pytest

from tools.opencart_upload_images import (
    UploadError,
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
