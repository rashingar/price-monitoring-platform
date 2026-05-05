from tools.opencart_upload_images import chunked_file_paths


def test_chunked_file_paths_splits_large_besco_uploads_into_batches_under_21() -> None:
    paths = [f"besco{i}.jpg" for i in range(1, 36)]

    batches = chunked_file_paths(paths, 20)

    assert len(batches) == 2
    assert len(batches[0]) == 20
    assert len(batches[1]) == 15
    assert all(len(batch) < 21 for batch in batches)
    assert batches[0][0] == "besco1.jpg"
    assert batches[1][-1] == "besco35.jpg"
