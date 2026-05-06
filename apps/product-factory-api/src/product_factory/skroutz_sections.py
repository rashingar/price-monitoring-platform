from __future__ import annotations

from html import escape
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from .normalize import make_absolute_url, normalize_for_match, normalize_whitespace

PLACEHOLDER_IMAGE_MARKERS = (
    "transparent.gif",
    "blank.gif",
    "spacer.gif",
    "about:blank",
    "data:image/gif",
    "data:,",
)
IMAGE_DATA_ATTRS = (
    "data-src",
    "data-srcset",
    "data-original",
    "data-fallback-src",
    "data-lazy-media-src-value",
    "data-lazy-media-srcset-value",
)
SKIPPED_SECTION_TITLES = {
    normalize_for_match("Με μια ματιά"),
    normalize_for_match("Οι χρήστες είπαν:"),
    normalize_for_match("Οι χρηστες ειπαν:"),
}


def is_placeholder_image_url(url: str | None) -> bool:
    normalized = normalize_whitespace(url).lower()
    if not normalized:
        return True
    return any(marker in normalized for marker in PLACEHOLDER_IMAGE_MARKERS)


def resolve_skroutz_section_image_url(record: dict[str, Any], base_url: str = "") -> str:
    for raw_value in _ordered_record_candidates(record):
        candidate = _normalize_image_candidate(raw_value, base_url)
        if candidate and not is_placeholder_image_url(candidate):
            return candidate
    return ""


def extract_skroutz_section_window(html: str, base_url: str = "") -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    candidates: list[dict[str, Any]] = []
    duplicates_skipped = 0
    seen_signatures: set[tuple[str, ...]] = set()

    for container_index, container in enumerate(soup.select("div.sku-description")):
        sections = _extract_section_blocks_from_container(container, base_url)
        if not sections:
            continue
        signature = tuple(normalize_for_match(block["title"]) for block in sections)
        if signature in seen_signatures:
            duplicates_skipped += 1
            continue
        seen_signatures.add(signature)
        first_heading = container.find(["h1", "h2", "h3", "h4"])
        headings = container.find_all(["h1", "h2", "h3", "h4"])
        last_heading = headings[-1] if headings else first_heading
        candidates.append(
            {
                "container_index": container_index,
                "sections": sections,
                "container_html": str(container),
                "start_anchor": _find_adjacent_heading_text(first_heading, backward=True) if isinstance(first_heading, Tag) else "",
                "stop_anchor": _find_adjacent_heading_text(last_heading, backward=False) if isinstance(last_heading, Tag) else "",
                "signature": signature,
            }
        )

    if not candidates:
        return {
            "sections": [],
            "warnings": ["skroutz_section_window_not_found"],
            "window": {
                "candidate_count": 0,
                "duplicate_signatures_skipped": duplicates_skipped,
                "selected_container_index": None,
                "start_anchor": "",
                "stop_anchor": "",
                "title_signature": [],
            },
        }

    selected = max(candidates, key=lambda candidate: (len(candidate["sections"]), candidate["container_index"]))
    return {
        "sections": selected["sections"],
        "container_html": selected["container_html"],
        "warnings": ["skroutz_duplicate_section_windows_deduped"] if duplicates_skipped else [],
        "window": {
            "candidate_count": len(candidates),
            "duplicate_signatures_skipped": duplicates_skipped,
            "selected_container_index": selected["container_index"],
            "start_anchor": selected["start_anchor"],
            "stop_anchor": selected["stop_anchor"],
            "title_signature": [block["title"] for block in selected["sections"]],
        },
    }


def build_skroutz_presentation_source_html(sections: list[dict[str, str]]) -> str:
    parts = ['<div class="sku-description">', '<div class="rich-components">']
    for index, section in enumerate(sections, start=1):
        section_class = "two-column order-reverse" if index % 2 == 0 else "two-column"
        parts.append(f'<section class="{section_class}">')
        parts.append('<div class="column">')
        parts.append(f"<h2>{escape(section['title'])}</h2>")
        parts.append(f'<div class="body-text"><p>{escape(section["paragraph"])}</p></div>')
        parts.append("</div>")
        if section.get("image_url"):
            parts.append('<figure class="column">')
            parts.append(
                f'<img alt="{escape(section["title"], quote=True)}" src="{escape(section["image_url"], quote=True)}" />'
            )
            parts.append("</figure>")
        parts.append("</section>")
    parts.append("</div>")
    parts.append("</div>")
    return "".join(parts)


def _ordered_record_candidates(record: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    current_src = record.get("currentSrc")
    if isinstance(current_src, str) and current_src:
        candidates.append(current_src)

    for group_name in ["lazy_attrs", "ancestor_data_attrs", "img_attrs"]:
        group = record.get(group_name)
        if isinstance(group, dict):
            for key in IMAGE_DATA_ATTRS:
                value = group.get(key)
                if isinstance(value, str) and value:
                    candidates.append(_extract_best_srcset_url(value) if "srcset" in key else value)

    img_attrs = record.get("img_attrs")
    if isinstance(img_attrs, dict):
        src = img_attrs.get("src")
        if isinstance(src, str) and src:
            candidates.append(src)
        srcset = img_attrs.get("srcset")
        if isinstance(srcset, str) and srcset:
            candidates.append(_extract_best_srcset_url(srcset))

    for value in record.get("source_srcsets", []) if isinstance(record.get("source_srcsets"), list) else []:
        if isinstance(value, str) and value:
            candidates.append(_extract_best_srcset_url(value))

    return [candidate for candidate in candidates if candidate]


def _normalize_image_candidate(value: str, base_url: str) -> str:
    normalized = normalize_whitespace(value)
    if not normalized:
        return ""
    return make_absolute_url(_extract_best_srcset_url(normalized), base_url)


def _extract_best_srcset_url(value: str) -> str:
    parts = [normalize_whitespace(part) for part in value.split(",") if normalize_whitespace(part)]
    if not parts:
        return ""
    best = parts[-1]
    return normalize_whitespace(best.split(" ")[0])


def _extract_section_blocks_from_container(container: Tag, base_url: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    rich_components = container.select_one("div.rich-components")
    root = rich_components if isinstance(rich_components, Tag) else container
    for section in root.select("section.two-column, section[class*='two-column'], section.one-column, section[class*='one-column']"):
        block = _extract_section_block(section, base_url)
        if block:
            blocks.append(block)
    return blocks


def _extract_section_block(section: Tag, base_url: str) -> dict[str, Any] | None:
    title_node = section.find(["h1", "h2", "h3", "h4"])
    title = normalize_whitespace(title_node.get_text(" ", strip=True) if isinstance(title_node, Tag) else "")
    if not title:
        return None
    if normalize_for_match(title) in SKIPPED_SECTION_TITLES:
        return None

    body = _extract_section_body(section)
    if not body:
        return None

    static_candidates = _extract_static_image_candidates(section, base_url)
    return {
        "title": title,
        "paragraph": body,
        "image_url": next((candidate for candidate in static_candidates if not is_placeholder_image_url(candidate)), ""),
        "image_candidates": static_candidates,
    }


def _extract_section_body(section: Tag) -> str:
    body_root = section.select_one(".body-text")
    if isinstance(body_root, Tag):
        return normalize_whitespace(body_root.get_text(" ", strip=True))

    column = section.select_one("div.column")
    if not isinstance(column, Tag):
        return ""

    clone_soup = BeautifulSoup(str(column), "lxml")
    clone = clone_soup.find("div")
    if not isinstance(clone, Tag):
        return ""

    for heading in clone.find_all(["h1", "h2", "h3", "h4"]):
        heading.decompose()

    for image_like in clone.find_all(["img", "figure", "picture"]):
        image_like.decompose()

    texts: list[str] = []
    for child in clone.children:
        if isinstance(child, NavigableString):
            text = normalize_whitespace(str(child))
        elif isinstance(child, Tag):
            text = normalize_whitespace(child.get_text(" ", strip=True))
        else:
            text = ""
        if text:
            texts.append(text)
    return normalize_whitespace(" ".join(texts))


def _extract_static_image_candidates(section: Tag, base_url: str) -> list[str]:
    urls: list[str] = []
    image = section.find("img")
    if isinstance(image, Tag):
        urls.extend(_collect_tag_image_candidates(image, base_url))

    figure = section.find("figure")
    if isinstance(figure, Tag):
        urls.extend(_collect_tag_image_candidates(figure, base_url))

    for source in section.find_all("source"):
        if isinstance(source, Tag):
            urls.extend(_collect_tag_image_candidates(source, base_url))

    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def _collect_tag_image_candidates(tag: Tag, base_url: str) -> list[str]:
    values: list[str] = []
    for attr_name in ("src", "srcset", *IMAGE_DATA_ATTRS):
        raw = tag.get(attr_name)
        if not isinstance(raw, str) or not normalize_whitespace(raw):
            continue
        candidate = _normalize_image_candidate(raw, base_url)
        if candidate:
            values.append(candidate)
    return values


def _find_adjacent_heading_text(node: Tag, backward: bool) -> str:
    cursor = node.find_previous if backward else node.find_next
    candidate = cursor(lambda item: isinstance(item, Tag) and item.name in {"h1", "h2", "h3", "h4"})
    while isinstance(candidate, Tag):
        text = normalize_whitespace(candidate.get_text(" ", strip=True))
        if text:
            return text
        candidate = candidate.find_previous(lambda item: isinstance(item, Tag) and item.name in {"h1", "h2", "h3", "h4"}) if backward else candidate.find_next(lambda item: isinstance(item, Tag) and item.name in {"h1", "h2", "h3", "h4"})
    return ""
