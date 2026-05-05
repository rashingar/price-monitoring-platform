import io
from pathlib import Path

from PIL import Image

from pipeline.fetcher import ElectronetFetcher
from pipeline.models import GalleryImage


class StubFetcher(ElectronetFetcher):
    def fetch_binary(self, url: str) -> tuple[bytes, str]:
        return b"binary-image", "image/jpeg"


class ConvertingStubFetcher(ElectronetFetcher):
    def fetch_binary(self, url: str) -> tuple[bytes, str]:
        image = Image.new("RGBA", (1200, 800), (0, 128, 255, 180))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue(), "image/png"


class GifStubFetcher(ElectronetFetcher):
    def fetch_binary(self, url: str) -> tuple[bytes, str]:
        image = Image.new("P", (64, 64))
        buffer = io.BytesIO()
        image.save(buffer, format="GIF")
        return buffer.getvalue(), "image/gif"



def test_gallery_images_saved_in_model_folder_with_business_names(tmp_path: Path) -> None:
    fetcher = StubFetcher()
    images = [
        GalleryImage(url="https://www.electronet.gr/image/one.jpg", alt="one", position=1),
        GalleryImage(url="https://www.electronet.gr/image/two.jpg", alt="two", position=2),
    ]

    downloaded, warnings, files_written = fetcher.download_gallery_images(
        images=images,
        model="234385",
        output_dir=tmp_path / "234385",
        requested_photos=2,
    )

    assert warnings == []
    assert [item.local_filename for item in downloaded] == ["234385-1.jpg", "234385-2.jpg"]
    assert all((tmp_path / "234385" / "gallery" / name).exists() for name in ["234385-1.jpg", "234385-2.jpg"])
    assert files_written == [
        str(tmp_path / "234385" / "gallery" / "234385-1.jpg"),
        str(tmp_path / "234385" / "gallery" / "234385-2.jpg"),
    ]


def test_besco_images_saved_in_bescos_subfolder_with_section_names(tmp_path: Path) -> None:
    fetcher = StubFetcher()
    images = [
        GalleryImage(url="https://www.electronet.gr/image/one.jpg", alt="one", position=1),
        GalleryImage(url="https://www.electronet.gr/image/three.jpg", alt="three", position=3),
    ]

    downloaded, warnings, files_written = fetcher.download_besco_images(
        images=images,
        output_dir=tmp_path / "234385",
        requested_sections=3,
    )

    assert warnings == ["besco_images_less_than_requested_sections"]
    assert [item.local_filename for item in downloaded] == ["besco1.jpg", "besco3.jpg"]
    assert all((tmp_path / "234385" / "bescos" / name).exists() for name in ["besco1.jpg", "besco3.jpg"])
    assert files_written == [
        str(tmp_path / "234385" / "bescos" / "besco1.jpg"),
        str(tmp_path / "234385" / "bescos" / "besco3.jpg"),
    ]


def test_gallery_non_jpg_images_are_converted_to_jpg(tmp_path: Path) -> None:
    fetcher = ConvertingStubFetcher()
    images = [GalleryImage(url="https://www.electronet.gr/image/one.png", alt="one", position=1)]

    downloaded, warnings, files_written = fetcher.download_gallery_images(
        images=images,
        model="234385",
        output_dir=tmp_path / "234385",
        requested_photos=1,
    )

    assert warnings == []
    assert [item.local_filename for item in downloaded] == ["234385-1.jpg"]
    assert downloaded[0].content_type == "image/jpeg"
    assert (tmp_path / "234385" / "gallery" / "234385-1.jpg").exists()
    assert files_written == [str(tmp_path / "234385" / "gallery" / "234385-1.jpg")]


def test_besco_non_jpg_images_are_converted_and_resized_to_jpg(tmp_path: Path) -> None:
    fetcher = ConvertingStubFetcher()
    images = [GalleryImage(url="https://www.electronet.gr/image/one.png", alt="one", position=1)]

    downloaded, warnings, _files_written = fetcher.download_besco_images(
        images=images,
        output_dir=tmp_path / "234385",
        requested_sections=1,
    )

    saved_path = tmp_path / "234385" / "bescos" / "besco1.jpg"
    with Image.open(saved_path) as saved:
        assert saved.format == "JPEG"
        assert saved.width <= 600
        assert saved.height <= 400

    assert warnings == []
    assert [item.local_filename for item in downloaded] == ["besco1.jpg"]
    assert downloaded[0].content_type == "image/jpeg"


def test_besco_gif_images_are_preserved_as_gif(tmp_path: Path) -> None:
    fetcher = GifStubFetcher()
    images = [GalleryImage(url="https://www.electronet.gr/image/anim.gif", alt="anim", position=1)]

    downloaded, warnings, files_written = fetcher.download_besco_images(
        images=images,
        output_dir=tmp_path / "234385",
        requested_sections=1,
    )

    assert warnings == []
    assert [item.local_filename for item in downloaded] == ["besco1.gif"]
    assert downloaded[0].content_type == "image/gif"
    assert (tmp_path / "234385" / "bescos" / "besco1.gif").exists()
    assert files_written == [str(tmp_path / "234385" / "bescos" / "besco1.gif")]

