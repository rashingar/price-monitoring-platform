from __future__ import annotations

from io import BytesIO

try:
    import pillow_avif  # noqa: F401
except Exception:  # pragma: no cover - optional runtime support
    pillow_avif = None

from PIL import Image

BESCO_MAX_WIDTH = 600
BESCO_MAX_HEIGHT = 400
JPEG_QUALITY = 90


class ImageConversionError(RuntimeError):
    pass


def _has_alpha(image: Image.Image) -> bool:
    if image.mode in {"RGBA", "LA"}:
        return True
    if image.mode == "P":
        return "transparency" in image.info
    return False


def _prepare_for_jpg(image: Image.Image) -> Image.Image:
    if not _has_alpha(image):
        return image.convert("RGB")

    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def _resize_within_bounds(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    width, height = image.size
    if width <= 0 or height <= 0:
        return image

    scale = min(max_width / width, max_height / height, 1)
    if scale >= 1:
        return image

    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.LANCZOS)


def convert_image_bytes_to_jpg(payload: bytes, *, resize_for_besco: bool = False) -> bytes:
    try:
        with Image.open(BytesIO(payload)) as image:
            working = image.copy()
    except Exception as exc:  # pragma: no cover - exercised via caller contract
        raise ImageConversionError(f"unsupported_or_corrupt_image:{exc}") from exc

    if resize_for_besco:
        working = _resize_within_bounds(working, BESCO_MAX_WIDTH, BESCO_MAX_HEIGHT)

    prepared = _prepare_for_jpg(working)
    output = BytesIO()
    prepared.save(output, format="JPEG", quality=JPEG_QUALITY)
    return output.getvalue()
