from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from .image_pipeline import (
    ImageConversionError,
    convert_image_bytes_to_jpg,
    convert_pdf_first_image_to_jpg,
)
from .models import FetchResult, GalleryImage
from .normalize import normalize_for_match, normalize_whitespace
from .seo_phase2 import image_content_hash, is_jpeg_bytes
from .skroutz_sections import SKIPPED_SECTION_TITLES, resolve_skroutz_section_image_url
from .utils import ensure_directory, guess_extension, write_bytes

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 ElectronetSingleImport/0.1"
)
CRAWL_TIMEOUT = httpx.Timeout(30.0, connect=10.0, read=30.0)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    pass


class RobotsDisallowedError(FetchError):
    pass


class ElectronetFetcher:
    def __init__(
        self, user_agent: str = USER_AGENT, timeout: httpx.Timeout = CRAWL_TIMEOUT
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout

    def _robots_allowed(self, url: str) -> tuple[bool, str]:
        parts = urlsplit(url)
        robots_url = urljoin(f"{parts.scheme}://{parts.netloc}", "/robots.txt")
        parser = RobotFileParser()
        try:
            with httpx.Client(
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
                follow_redirects=True,
            ) as client:
                response = client.get(robots_url)
                if response.status_code >= 400 or not response.text.strip():
                    return True, "robots_unavailable"
                parser.parse(response.text.splitlines())
                return parser.can_fetch(self.user_agent, url), robots_url
        except Exception:
            return True, "robots_unavailable"

    def _base_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        }

    def fetch_httpx(self, url: str) -> FetchResult:
        allowed, robots_info = self._robots_allowed(url)
        if not allowed:
            raise RobotsDisallowedError(f"Robots.txt disallows scraping for: {url}")

        last_error: Exception | None = None
        for attempt in range(1, 5):
            time.sleep(random.uniform(0.15, 0.55))
            try:
                with httpx.Client(
                    timeout=self.timeout,
                    follow_redirects=True,
                    headers=self._base_headers(),
                ) as client:
                    response = client.get(url)
                if response.status_code in RETRYABLE_STATUS:
                    last_error = FetchError(f"HTTP {response.status_code} for {url}")
                    time.sleep((2 ** (attempt - 1)) + random.uniform(0.0, 0.35))
                    continue
                response.raise_for_status()
                return FetchResult(
                    url=url,
                    final_url=str(response.url),
                    html=response.text,
                    status_code=response.status_code,
                    method="httpx",
                    fallback_used=False,
                    response_headers={
                        **dict(response.headers),
                        "x-robots-source": robots_info,
                    },
                )
            except Exception as exc:
                last_error = exc
                if attempt < 4:
                    time.sleep((2 ** (attempt - 1)) + random.uniform(0.0, 0.35))
        raise FetchError(f"HTTP fetch failed for {url}: {last_error}")

    def fetch_playwright(self, url: str) -> FetchResult:
        allowed, robots_info = self._robots_allowed(url)
        if not allowed:
            raise RobotsDisallowedError(f"Robots.txt disallows scraping for: {url}")
        try:
            from playwright.sync_api import sync_playwright
        except (
            Exception
        ) as exc:  # pragma: no cover - import path is environment-dependent
            raise FetchError(f"Playwright is not available: {exc}") from exc

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=self.user_agent, locale="el-GR"
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    # Some vendor pages keep background requests open after the
                    # product DOM is usable.
                    pass
                html = page.content()
                final_url = page.url
                browser.close()
            return FetchResult(
                url=url,
                final_url=final_url,
                html=html,
                status_code=200,
                method="playwright",
                fallback_used=True,
                response_headers={"x-robots-source": robots_info},
            )
        except Exception as exc:
            raise FetchError(f"Playwright fetch failed for {url}: {exc}") from exc

    def extract_skroutz_section_image_records(self, url: str) -> dict[str, object]:
        allowed, robots_info = self._robots_allowed(url)
        if not allowed:
            raise RobotsDisallowedError(f"Robots.txt disallows scraping for: {url}")
        try:
            from playwright.sync_api import sync_playwright
        except (
            Exception
        ) as exc:  # pragma: no cover - import path is environment-dependent
            raise FetchError(f"Playwright is not available: {exc}") from exc

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=self.user_agent, locale="el-GR"
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    # Skroutz pages may keep background requests open indefinitely.
                    pass
                page.wait_for_timeout(3000)

                container_locator = page.locator("div.sku-description")
                container_count = container_locator.count()
                if container_count == 0:
                    raise FetchError("skroutz_section_containers_not_found")

                container_meta: list[dict[str, object]] = []
                for index in range(container_count):
                    meta = container_locator.nth(index).evaluate(
                        """
(el, index) => {
  const rect = el.getBoundingClientRect();
  const titles = Array.from(el.querySelectorAll('div.rich-components section h2, div.rich-components section h3, div.rich-components section h4'))
    .map(node => (node.textContent || '').replace(/\\s+/g, ' ').trim())
    .filter(Boolean);
  return {
    dom_index: index,
    title_count: titles.length,
    titles,
    width: rect.width,
    height: rect.height,
    visible_area: Math.max(rect.width, 0) * Math.max(rect.height, 0),
  };
}
""",
                        index,
                    )
                    if meta.get("title_count"):
                        container_meta.append(meta)

                selected_container = self._select_best_skroutz_section_container(
                    container_meta
                )
                if selected_container is None:
                    raise FetchError("skroutz_section_window_not_found")

                selected_dom_index = int(selected_container["dom_index"])
                sections_locator = container_locator.nth(selected_dom_index).locator(
                    "div.rich-components section"
                )
                section_count = sections_locator.count()
                sections: list[dict[str, object]] = []
                for section_index in range(section_count):
                    section_locator = sections_locator.nth(section_index)
                    section_locator.scroll_into_view_if_needed(timeout=10000)
                    page.wait_for_timeout(500)
                    title_locator = section_locator.locator("h2, h3, h4").first
                    if title_locator.count() == 0:
                        continue
                    title = normalize_whitespace(
                        title_locator.inner_text(timeout=10000)
                    )
                    if not title:
                        continue
                    if normalize_for_match(title) in SKIPPED_SECTION_TITLES:
                        continue
                    body = ""
                    body_locator = section_locator.locator(".body-text")
                    if body_locator.count():
                        body = normalize_whitespace(
                            body_locator.first.inner_text(timeout=10000)
                        )

                    image_locator = section_locator.locator("img").first
                    if image_locator.count() == 0:
                        sections.append(
                            {
                                "position": section_index + 1,
                                "title": title,
                                "body": body,
                                "image_record": {},
                                "resolved_image_url": "",
                            }
                        )
                        continue

                    image_record = image_locator.evaluate("""
(el) => {
  const collectAttrs = (node) => {
    const out = {};
    if (!node) {
      return out;
    }
    for (const attr of Array.from(node.attributes)) {
      if (attr.name === 'src' || attr.name === 'srcset' || attr.name.startsWith('data-')) {
        out[attr.name] = attr.value;
      }
    }
    return out;
  };
  const picture = el.closest('picture');
  const figure = el.closest('figure');
  return {
    currentSrc: el.currentSrc || '',
    img_attrs: collectAttrs(el),
    lazy_attrs: collectAttrs(figure),
    ancestor_data_attrs: collectAttrs(el.parentElement),
    source_srcsets: picture ? Array.from(picture.querySelectorAll('source')).map((node) => node.getAttribute('srcset') || '').filter(Boolean) : [],
    natural_width: el.naturalWidth || 0,
    natural_height: el.naturalHeight || 0,
  };
}
""")
                    sections.append(
                        {
                            "position": section_index + 1,
                            "title": title,
                            "body": body,
                            "image_record": image_record,
                            "resolved_image_url": resolve_skroutz_section_image_url(
                                image_record, base_url=page.url
                            ),
                        }
                    )

                browser.close()
            return {
                "response_headers": {"x-robots-source": robots_info},
                "window": {
                    "candidate_count": len(container_meta),
                    "selected_container_index": selected_dom_index,
                    "duplicate_signatures_skipped": self._count_duplicate_signatures(
                        container_meta
                    ),
                },
                "containers": container_meta,
                "sections": sections,
            }
        except FetchError:
            raise
        except Exception as exc:
            raise FetchError(
                f"Skroutz section image extraction failed for {url}: {exc}"
            ) from exc

    def fetch_binary(self, url: str) -> tuple[bytes, str]:
        allowed, _ = self._robots_allowed(url)
        if not allowed:
            raise RobotsDisallowedError(f"Robots.txt disallows scraping for: {url}")

        last_error: Exception | None = None
        for attempt in range(1, 5):
            time.sleep(random.uniform(0.10, 0.30))
            try:
                with httpx.Client(
                    timeout=self.timeout,
                    follow_redirects=True,
                    headers={**self._base_headers(), "Accept": "image/*,*/*;q=0.8"},
                ) as client:
                    response = client.get(url)
                if response.status_code in RETRYABLE_STATUS:
                    last_error = FetchError(f"HTTP {response.status_code} for {url}")
                    time.sleep((2 ** (attempt - 1)) + random.uniform(0.0, 0.25))
                    continue
                response.raise_for_status()
                return response.content, response.headers.get("content-type", "")
            except Exception as exc:
                last_error = exc
                if attempt < 4:
                    time.sleep((2 ** (attempt - 1)) + random.uniform(0.0, 0.25))
        raise FetchError(f"Binary fetch failed for {url}: {last_error}")

    def download_gallery_images(
        self,
        images: list[GalleryImage],
        model: str,
        output_dir: str | Path,
        requested_photos: int | None = None,
        image_slug: str = "",
        require_jpeg_validation: bool = False,
    ) -> tuple[list[GalleryImage], list[str], list[str]]:
        return self._download_images(
            images=images,
            output_dir=output_dir,
            output_subdir="gallery",
            requested_count=requested_photos,
            shortage_warning="gallery_images_less_than_requested_photos",
            non_jpg_warning_prefix="gallery_image_non_jpg_saved",
            filename_builder=lambda position, ext: (
                f"{image_slug}-{position}.jpg" if image_slug else f"{model}-{position}{ext}"
            ),
            require_jpeg_validation=require_jpeg_validation,
        )

    def download_besco_images(
        self,
        images: list[GalleryImage],
        output_dir: str | Path,
        requested_sections: int | None = None,
    ) -> tuple[list[GalleryImage], list[str], list[str]]:
        return self._download_images(
            images=images,
            output_dir=output_dir,
            output_subdir="bescos",
            requested_count=requested_sections,
            shortage_warning="besco_images_less_than_requested_sections",
            non_jpg_warning_prefix="besco_image_non_jpg_saved",
            filename_builder=lambda position, ext: f"besco{position}{ext}",
        )

    def _download_images(
        self,
        images: list[GalleryImage],
        output_dir: str | Path,
        output_subdir: str,
        requested_count: int | None,
        shortage_warning: str,
        non_jpg_warning_prefix: str,
        filename_builder: Callable[[int, str], str],
        require_jpeg_validation: bool = False,
    ) -> tuple[list[GalleryImage], list[str], list[str]]:
        target_dir = ensure_directory(Path(output_dir) / output_subdir)
        for existing_file in target_dir.iterdir():
            if existing_file.is_file() and existing_file.suffix.lower() in {
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".gif",
                ".pdf",
            }:
                existing_file.unlink()
        selected = images
        if requested_count is not None and requested_count > 0:
            selected = images[:requested_count]

        warnings: list[str] = []
        written_files: list[str] = []
        downloaded: list[GalleryImage] = []

        if requested_count and len(images) < requested_count:
            warnings.append(shortage_warning)

        for fallback_position, image in enumerate(selected, start=1):
            asset_position = image.position if image.position > 0 else fallback_position
            payload, content_type = self.fetch_binary(image.url)
            ext = guess_extension(content_type, image.url)
            preserve_besco_gif = output_subdir == "bescos" and ext == ".gif"
            is_pdf = ext == ".pdf" or "application/pdf" in content_type.lower()
            if is_pdf:
                try:
                    payload = convert_pdf_first_image_to_jpg(
                        payload,
                        resize_for_besco=output_subdir == "bescos",
                    )
                    ext = ".jpg"
                    content_type = "image/jpeg"
                except ImageConversionError as exc:
                    warnings.append(f"{non_jpg_warning_prefix}:{asset_position}:{ext}")
                    warnings.append(
                        f"image_conversion_failed:{output_subdir}:{asset_position}:{ext}:{exc}"
                    )
            elif (ext != ".jpg" or (require_jpeg_validation and not is_jpeg_bytes(payload))) and not preserve_besco_gif:
                try:
                    payload = convert_image_bytes_to_jpg(
                        payload,
                        resize_for_besco=output_subdir == "bescos",
                    )
                    ext = ".jpg"
                    content_type = "image/jpeg"
                except ImageConversionError as exc:
                    warnings.append(f"{non_jpg_warning_prefix}:{asset_position}:{ext}")
                    warnings.append(
                        f"image_conversion_failed:{output_subdir}:{asset_position}:{ext}:{exc}"
                    )
            if output_subdir == "gallery" and require_jpeg_validation and not is_jpeg_bytes(payload):
                warnings.append(f"image_jpeg_validation_failed:{output_subdir}:{asset_position}")
                continue
            filename_position = asset_position
            filename = filename_builder(filename_position, ext)
            local_path = target_dir / filename
            write_bytes(local_path, payload)
            downloaded_image = GalleryImage(
                url=image.url,
                alt=image.alt,
                position=asset_position,
                local_filename=filename,
                local_path=str(local_path),
                content_type=content_type,
                downloaded=True,
                source_url=image.url,
                source_alt=image.alt,
                role="main" if asset_position == 1 else "gallery",
                filename_candidate=filename if output_subdir == "gallery" else "",
                public_path=(
                    f"catalog/01_main/{Path(output_dir).name}/{filename}"
                    if output_subdir == "gallery" else ""
                ),
                jpeg_valid=is_jpeg_bytes(payload),
                content_hash=image_content_hash(payload),
                width=_image_size(payload)[0],
                height=_image_size(payload)[1],
            )
            downloaded.append(downloaded_image)
            written_files.append(str(local_path))
        return downloaded, warnings, written_files


def _image_size(payload: bytes) -> tuple[int, int]:
    try:
        from PIL import Image
        from io import BytesIO
        with Image.open(BytesIO(payload)) as image:
            return image.size
    except Exception:
        return 0, 0

    def _select_best_skroutz_section_container(
        self, containers: list[dict[str, object]]
    ) -> dict[str, object] | None:
        unique_by_signature: dict[tuple[str, ...], dict[str, object]] = {}
        for container in containers:
            titles = container.get("titles", [])
            signature = tuple(
                normalize_whitespace(str(title))
                for title in titles
                if normalize_whitespace(str(title))
            )
            if not signature:
                continue
            existing = unique_by_signature.get(signature)
            if existing is None or self._skroutz_container_sort_key(
                container
            ) > self._skroutz_container_sort_key(existing):
                unique_by_signature[signature] = container
        if not unique_by_signature:
            return None
        return max(unique_by_signature.values(), key=self._skroutz_container_sort_key)

    def _count_duplicate_signatures(self, containers: list[dict[str, object]]) -> int:
        seen: set[tuple[str, ...]] = set()
        duplicates = 0
        for container in containers:
            titles = container.get("titles", [])
            signature = tuple(
                normalize_whitespace(str(title))
                for title in titles
                if normalize_whitespace(str(title))
            )
            if not signature:
                continue
            if signature in seen:
                duplicates += 1
                continue
            seen.add(signature)
        return duplicates

    def _skroutz_container_sort_key(
        self, container: dict[str, object]
    ) -> tuple[float, int, int]:
        visible_area = float(container.get("visible_area", 0) or 0)
        title_count = int(container.get("title_count", 0) or 0)
        dom_index = int(container.get("dom_index", 0) or 0)
        return (visible_area, title_count, dom_index)
