from __future__ import annotations

import re
from html import escape

from bs4 import BeautifulSoup, Tag

from .intro_text_markup import render_intro_text_markup_html, strip_intro_text_markup
from .models import SpecSection
from .normalize import (
    make_absolute_url,
    normalize_for_match,
    normalize_whitespace,
    split_visible_lines,
)

GENDER_SUFFIX = {"fem": "ες", "neut": "α", "masc": "ους"}
TV_CTA_LABEL = normalize_for_match("Τηλεοράσεις")
TV_CTA_TEXT = "Δείτε περισσότερες Τηλεοράσεις εδώ"


def build_deterministic_cta(gender: str, plural_label: str) -> str:
    suffix = GENDER_SUFFIX.get(gender, "α")
    label = normalize_whitespace(plural_label)
    if not label:
        return "Δείτε περισσότερα εδώ"
    if normalize_for_match(label) == TV_CTA_LABEL:
        return TV_CTA_TEXT
    return f"Δείτε περισσότερ{suffix} {label} εδώ"


def default_cta_text(cta_label: str) -> str:
    label = normalize_whitespace(cta_label)
    if normalize_for_match(label) == TV_CTA_LABEL:
        return TV_CTA_TEXT
    return f"Δείτε περισσότερα {label} εδώ" if label else "Δείτε περισσότερα εδώ"


def resolve_cta_text(cta_text: str, cta_label: str) -> str:
    normalized = normalize_whitespace(cta_text)
    if not normalized:
        return default_cta_text(cta_label)
    generic_values = {
        normalize_for_match("Δείτε περισσότερα"),
        normalize_for_match("Δείτε περισσότερα εδώ"),
    }
    if normalize_for_match(normalized) in generic_values:
        return default_cta_text(cta_label)
    return normalized


def build_characteristics_html(spec_sections: list[SpecSection]) -> str:
    if not spec_sections:
        return ""
    parts = ['<table class="table table-bordered">']
    for section in spec_sections:
        parts.append("<thead>")
        parts.append("<tr>")
        parts.append(f'<td colspan="2"><strong>{escape(section.section)}</strong></td>')
        parts.append("</tr>")
        parts.append("</thead>")
        parts.append("<tbody>")
        for item in section.items:
            label = escape(_normalize_characteristics_label(item.label))
            value = escape(_normalize_characteristics_value(item.label, item.value))
            parts.append("<tr>")
            parts.append(f"<td>{label}</td>")
            parts.append(f'<td style="text-align:right;"><strong>{value}</strong></td>')
            parts.append("</tr>")
        parts.append("</tbody>")
    parts.append("</table>")
    return "".join(parts)


def _normalize_characteristics_label(label: str) -> str:
    normalized = normalize_whitespace(label)
    if normalized.startswith("Υψος "):
        normalized = normalized.replace("Υψος ", "Ύψος ", 1)
    if normalized.count("(") == normalized.count(")") + 1:
        normalized += ")"
    return normalized


def _normalize_characteristics_value(label: str, value: str | None) -> str:
    normalized = normalize_whitespace(value)
    if not normalized:
        return "-"
    label_key = normalize_for_match(label)
    if label_key == normalize_for_match("Επιπλέον Χαρακτηριστικά") and (
        "," in normalized or len(normalized.split()) > 3
    ):
        return "-"
    if "σε εκατοστα" in label_key and re.fullmatch(r"\d+(?:[.,]\d+)?", normalized):
        numeric = float(normalized.replace(",", "."))
        return f"{numeric:.2f}"
    return re.sub(r"(?<=\d)\s*[xX]\s*(?=\d)", " × ", normalized)


def build_description_html(
    product_name: str,
    hero_summary: str,
    presentation_source_html: str,
    presentation_source_text: str,
    model: str,
    sections_requested: int,
    cta_url: str,
    cta_label: str,
    besco_filenames_by_section: dict[int, str] | None = None,
    base_url: str = "",
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not product_name:
        return "", ["description_not_built_from_source"]
    if not cta_url:
        return "", ["description_not_built_from_source", "cta_url_unresolved"]

    intro = normalize_whitespace(hero_summary)
    blocks = extract_presentation_blocks(
        presentation_source_html, presentation_source_text, base_url=base_url
    )
    if not intro and blocks:
        intro = blocks[0]["paragraph"]
    if not intro:
        return "", ["description_not_built_from_source"]

    selected_blocks = []
    if sections_requested > 0:
        selected_blocks = blocks[:sections_requested]
        if not selected_blocks:
            return "", ["description_not_built_from_source"]
        if len(selected_blocks) < sections_requested:
            warnings.append("requested_sections_exceed_source_sections")
    use_besco_asset_map = besco_filenames_by_section is not None
    besco_filenames_by_section = besco_filenames_by_section or {}

    cta_text = default_cta_text(cta_label)
    out = ['<div class="etr-desc">']
    out.append(
        f'<h2 style="text-align:center"><span style="font-size:36px"><strong>{escape(product_name)}</strong></span></h2>'
    )
    out.append("")
    out.append(
        '<p style="margin-left:auto; margin-right:auto; text-align:left"><span style="font-size:24px">'
    )
    out.append(escape(intro))
    out.append("</span></p>")
    out.append("")
    out.append(
        '<div style="margin-bottom:20px; margin-left:auto; margin-right:auto; margin-top:20px; text-align:center">'
    )
    out.append(
        f'<a href="{escape(cta_url, quote=True)}" style="font-size: 20px; padding: 12px 28px; background-color: #03BABE; color: #F7FCFC; border-radius: 12px; text-decoration: none;">{escape(cta_text)}</a>'
    )
    out.append("</div>")
    out.append("")
    out.append("<hr />")
    out.append('<div class="etr-desc">')
    out.append("")
    for media_html in extract_presentation_media_blocks(
        presentation_source_html, base_url=base_url
    ):
        out.append(media_html)
        out.append("")

    for idx, block in enumerate(selected_blocks, start=1):
        cls = "etr-sec rev" if idx % 2 == 0 else "etr-sec"
        out.append(f"  <!-- SECTION {idx} -->")
        out.append(f'  <div class="{cls}">')
        out.append('    <div class="etr-text">')
        out.append(
            f'      <h2><span style="font-size:24px"><strong>{escape(block["title"])}</strong></span></h2>'
        )
        out.append(
            _render_section_body_html(
                block.get("body_html", ""), str(block.get("paragraph", ""))
            )
        )
        out.append("    </div>")
        default_besco_filename = f"besco{idx}.jpg"
        besco_filename = besco_filenames_by_section.get(
            idx, "" if use_besco_asset_map else default_besco_filename
        )
        media_html = _render_section_media_html(
            str(block.get("media_html", "")), align_right=idx % 2 == 0
        )
        if besco_filename:
            out.append('    <div class="etr-img">')
            img_style = (
                ' style="display:block; margin-left:auto; margin-right:0;"'
                if idx % 2 == 0
                else ""
            )
            out.append(
                f'      <img alt="{escape(block["title"], quote=True)}" src="https://www.etranoulis.gr/image/catalog/01_bescos/{escape(model, quote=True)}/{escape(besco_filename, quote=True)}"{img_style} />'
            )
            out.append("    </div>")
        elif media_html:
            out.append('    <div class="etr-img">')
            out.append(media_html)
            out.append("    </div>")
        out.append("  </div>")
        out.append("")

    out.append("</div>")
    out.append("</div>")
    return "\n".join(out), warnings


def build_description_html_from_llm(
    product_name: str,
    model: str,
    cta_url: str,
    cta_label: str,
    intro_html: str,
    cta_text: str,
    sections: list[dict[str, str]],
    besco_filenames_by_section: dict[int, str] | None = None,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not product_name:
        return "", ["description_not_built_from_llm"]
    if not cta_url:
        return "", ["description_not_built_from_llm", "cta_url_unresolved"]
    if not normalize_whitespace(intro_html):
        return "", ["description_not_built_from_llm", "llm_intro_missing"]

    use_besco_asset_map = besco_filenames_by_section is not None
    besco_filenames_by_section = besco_filenames_by_section or {}
    out = ['<div class="etr-desc">']
    out.append(
        f'<h2 style="text-align:center"><span style="font-size:36px"><strong>{escape(product_name)}</strong></span></h2>'
    )
    out.append("")
    out.append(
        '<p style="margin-left:auto; margin-right:auto; text-align:left"><span style="font-size:24px">'
    )
    out.append(intro_html.strip())
    out.append("</span></p>")
    out.append("")
    out.append(
        '<div style="margin-bottom:20px; margin-left:auto; margin-right:auto; margin-top:20px; text-align:center">'
    )
    out.append(
        f'<a href="{escape(cta_url, quote=True)}" style="font-size: 20px; padding: 12px 28px; background-color: #03BABE; color: #F7FCFC; border-radius: 12px; text-decoration: none;">{escape(resolve_cta_text(cta_text, cta_label))}</a>'
    )
    out.append("</div>")
    out.append("")
    out.append("<hr />")
    out.append('<div class="etr-desc">')
    out.append("")

    for idx, block in enumerate(sections, start=1):
        title = normalize_whitespace(block.get("title"))
        body_html = (block.get("body_html") or "").strip()
        if not title or not normalize_whitespace(body_html):
            warnings.append(f"llm_section_incomplete:{idx}")
            continue
        cls = "etr-sec rev" if idx % 2 == 0 else "etr-sec"
        out.append(f"  <!-- SECTION {idx} -->")
        out.append(f'  <div class="{cls}">')
        out.append('    <div class="etr-text">')
        out.append(
            f'      <h2><span style="font-size:24px"><strong>{escape(title)}</strong></span></h2>'
        )
        out.append(f'      <p><span style="font-size:22px">{body_html}</span></p>')
        out.append("    </div>")
        default_besco_filename = f"besco{idx}.jpg"
        besco_filename = besco_filenames_by_section.get(
            idx, "" if use_besco_asset_map else default_besco_filename
        )
        media_html = _render_section_media_html(
            str(block.get("media_html", "")), align_right=idx % 2 == 0
        )
        if besco_filename:
            out.append('    <div class="etr-img">')
            img_style = (
                ' style="display:block; margin-left:auto; margin-right:0;"'
                if idx % 2 == 0
                else ""
            )
            out.append(
                f'      <img alt="{escape(title, quote=True)}" src="https://www.etranoulis.gr/image/catalog/01_bescos/{escape(model, quote=True)}/{escape(besco_filename, quote=True)}"{img_style} />'
            )
            out.append("    </div>")
        elif media_html:
            out.append('    <div class="etr-img">')
            out.append(media_html)
            out.append("    </div>")
        out.append("  </div>")
        out.append("")

    out.append("</div>")
    out.append("</div>")
    return "\n".join(out), warnings


def build_description_html_from_intro_and_sections(
    product_name: str,
    model: str,
    cta_url: str,
    cta_text: str,
    intro_text: str,
    sections: list[dict[str, str]],
    besco_filenames_by_section: dict[int, str] | None = None,
    presentation_source_html: str = "",
    presentation_source_text: str = "",
    base_url: str = "",
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not product_name:
        return "", ["description_not_built_from_split"]
    if not cta_url:
        return "", ["description_not_built_from_split", "cta_url_unresolved"]
    if not normalize_whitespace(strip_intro_text_markup(intro_text)):
        return "", ["description_not_built_from_split", "llm_intro_missing"]
    intro_html, intro_markup_warnings = render_intro_text_markup_html(intro_text)
    warnings.extend(intro_markup_warnings)

    use_besco_asset_map = besco_filenames_by_section is not None
    besco_filenames_by_section = besco_filenames_by_section or {}
    out = ['<div class="etr-desc">']
    out.append(
        f'<h2 style="text-align:center"><span style="font-size:36px"><strong>{escape(product_name)}</strong></span></h2>'
    )
    out.append("")
    out.append(
        '<p style="margin-left:auto; margin-right:auto; text-align:left"><span style="font-size:24px">'
    )
    out.append(intro_html)
    out.append("</span></p>")
    out.append("")
    out.append(
        '<div style="margin-bottom:20px; margin-left:auto; margin-right:auto; margin-top:20px; text-align:center">'
    )
    out.append(
        f'<a href="{escape(cta_url, quote=True)}" style="font-size: 20px; padding: 12px 28px; background-color: #03BABE; color: #F7FCFC; border-radius: 12px; text-decoration: none;">{escape(cta_text)}</a>'
    )
    out.append("</div>")
    out.append("")
    out.append("<hr />")
    out.append('<div class="etr-desc">')
    out.append("")
    source_blocks = extract_presentation_blocks(
        presentation_source_html=presentation_source_html,
        presentation_source_text=presentation_source_text,
        base_url=base_url,
    )
    source_block_map = {
        index: block for index, block in enumerate(source_blocks, start=1)
    }
    for media_html in extract_presentation_media_blocks(
        presentation_source_html, base_url=base_url
    ):
        out.append(media_html)
        out.append("")

    for idx, block in enumerate(sections, start=1):
        title = normalize_whitespace(block.get("title", ""))
        body_text = normalize_whitespace(block.get("body_text", ""))
        cls = "etr-sec rev" if idx % 2 == 0 else "etr-sec"
        source_index = int(block.get("source_index") or idx)
        source_block = source_block_map.get(source_index, {})
        media_html = _render_section_media_html(
            str(source_block.get("media_html") or block.get("media_html", "")),
            align_right=idx % 2 == 0,
        )
        if not title or (not body_text and not media_html):
            warnings.append(f"deterministic_section_incomplete:{idx}")
            continue
        out.append(f"  <!-- SECTION {idx} -->")
        out.append(f'  <div class="{cls}">')
        out.append('    <div class="etr-text">')
        out.append(
            f'      <h2><span style="font-size:24px"><strong>{escape(title)}</strong></span></h2>'
        )
        out.append(
            _render_section_body_html(str(source_block.get("body_html", "")), body_text)
        )
        out.append("    </div>")
        default_besco_filename = f"besco{source_index}.jpg"
        besco_filename = besco_filenames_by_section.get(
            source_index, "" if use_besco_asset_map else default_besco_filename
        )
        if besco_filename:
            out.append('    <div class="etr-img">')
            img_style = (
                ' style="display:block; margin-left:auto; margin-right:0;"'
                if idx % 2 == 0
                else ""
            )
            out.append(
                f'      <img alt="{escape(title, quote=True)}" src="https://www.etranoulis.gr/image/catalog/01_bescos/{escape(model, quote=True)}/{escape(besco_filename, quote=True)}"{img_style} />'
            )
            out.append("    </div>")
        elif media_html:
            out.append('    <div class="etr-img">')
            out.append(media_html)
            out.append("    </div>")
        out.append("  </div>")
        out.append("")

    out.append("</div>")
    out.append("</div>")
    return "\n".join(out), warnings


def extract_presentation_blocks(
    presentation_source_html: str,
    presentation_source_text: str,
    base_url: str = "",
) -> list[dict[str, str]]:
    blocks = _blocks_from_html(presentation_source_html, base_url)
    if blocks:
        return blocks
    return _blocks_from_text(presentation_source_text)


def extract_presentation_media_blocks(
    source_html: str, base_url: str = ""
) -> list[str]:
    if not source_html.strip():
        return []
    soup = BeautifulSoup(source_html, "lxml")
    rendered_blocks: list[str] = []
    for container in soup.select(".ck-text.whole"):
        if not isinstance(container, Tag):
            continue
        if container.find(["video", "iframe"]) is None:
            continue
        rendered = _render_standalone_media_container_html(container, base_url)
        if rendered:
            rendered_blocks.append(rendered)
    return rendered_blocks


def extract_presentation_appendix_blocks(
    source_html: str, base_url: str = ""
) -> list[dict[str, str]]:
    if not source_html.strip():
        return []
    soup = BeautifulSoup(source_html, "lxml")
    appendix_blocks: list[dict[str, str]] = []
    for container in soup.select(".ck-text.inline"):
        if not isinstance(container, Tag):
            continue
        title = _select_presentation_title(container)
        if title:
            continue
        paragraph = _extract_container_body_text(container)
        body_html = _extract_container_body_html(container)
        if not paragraph and not body_html:
            continue
        image_node = container.find("img")
        src = ""
        if isinstance(image_node, Tag):
            src = (
                image_node.get("src")
                or image_node.get("data-src")
                or image_node.get("data-original")
                or ""
            )
        appendix_blocks.append(
            {
                "title": "",
                "paragraph": paragraph,
                "body_html": body_html,
                "image_url": make_absolute_url(src, base_url) if src else "",
            }
        )
    return appendix_blocks


def _blocks_from_html(source_html: str, base_url: str = "") -> list[dict[str, str]]:
    if not source_html.strip():
        return []
    soup = BeautifulSoup(source_html, "lxml")
    container_blocks = _blocks_from_html_containers(soup, base_url)
    if container_blocks:
        return container_blocks
    blocks: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for node in soup.find_all(["h1", "h2", "h3", "h4", "p", "img", "iframe", "video"]):
        if not isinstance(node, Tag):
            continue
        if node.name.startswith("h"):
            text = normalize_whitespace(node.get_text(" ", strip=True))
            if not text:
                continue
            if current and current.get("title") and (
                current.get("paragraph") or current.get("media_html")
            ):
                blocks.append(current)
            current = {"title": text, "paragraph": "", "image_url": ""}
        elif node.name == "p" and current is not None:
            text = normalize_whitespace(node.get_text(" ", strip=True))
            if not text:
                continue
            current["paragraph"] = f"{current['paragraph']} {text}".strip()
        elif (
            node.name == "img" and current is not None and not current.get("image_url")
        ):
            src = node.get("src") or node.get("data-src") or node.get("data-original")
            image_url = make_absolute_url(src, base_url) if src else ""
            if image_url:
                current["image_url"] = image_url
        elif (
            node.name in {"iframe", "video"}
            and current is not None
            and not current.get("image_url")
            and not current.get("media_html")
        ):
            media_html = _extract_container_media_html(node, base_url)
            if media_html:
                current["media_html"] = media_html
    if current and current.get("title") and (
        current.get("paragraph") or current.get("media_html")
    ):
        blocks.append(current)
    return blocks


def _blocks_from_html_containers(
    soup: BeautifulSoup, base_url: str
) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    for container in soup.select(".ck-text.inline"):
        if not isinstance(container, Tag):
            continue
        title = _select_presentation_title(container)
        paragraph = _extract_container_body_text(container)
        body_html = _extract_container_body_html(container)
        image_node = container.find("img")
        src = ""
        if isinstance(image_node, Tag):
            src = (
                image_node.get("src")
                or image_node.get("data-src")
                or image_node.get("data-original")
                or ""
            )
        image_url = make_absolute_url(src, base_url) if src else ""
        media_html = (
            _extract_container_media_html(container, base_url) if not image_url else ""
        )
        if title and paragraph:
            blocks.append(
                {
                    "title": title,
                    "paragraph": paragraph,
                    "image_url": image_url,
                    "body_html": body_html,
                    "media_html": media_html,
                }
            )
    return blocks


def _select_presentation_title(container: Tag) -> str:
    for tag_name in ["h3", "h4", "h2", "h1"]:
        for node in container.find_all(tag_name):
            text = normalize_whitespace(node.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _extract_container_body_text(container: Tag) -> str:
    body_parts: list[str] = []
    paragraph_nodes = [
        node
        for node in container.find_all("p")
        if normalize_whitespace(node.get_text(" ", strip=True))
    ]
    if paragraph_nodes:
        body_parts.extend(
            normalize_whitespace(node.get_text(" ", strip=True))
            for node in paragraph_nodes
        )

    list_item_nodes = [
        node
        for node in container.find_all("li")
        if normalize_whitespace(node.get_text(" ", strip=True))
    ]
    if list_item_nodes:
        body_parts.extend(
            normalize_whitespace(node.get_text(" ", strip=True))
            for node in list_item_nodes
        )

    return normalize_whitespace(" ".join(body_parts))


def _extract_container_body_html(container: Tag) -> str:
    fragments: list[str] = []
    seen: set[int] = set()
    for node in container.find_all(["p", "ul", "ol"]):
        if not isinstance(node, Tag):
            continue
        if node.find_parent(["p", "ul", "ol"]) is not None:
            continue
        if id(node) in seen:
            continue
        seen.add(id(node))
        rendered = _sanitize_body_fragment_html(node)
        if rendered:
            fragments.append(rendered)
    return "\n".join(fragments).strip()


def _sanitize_body_fragment_html(node: Tag) -> str:
    fragment = BeautifulSoup(str(node), "lxml")
    body = fragment.body or fragment
    for tag in body.find_all(True):
        if tag.name not in {
            "p",
            "ul",
            "ol",
            "li",
            "br",
            "strong",
            "em",
            "b",
            "i",
            "span",
        }:
            tag.unwrap()
            continue
        if tag.name in {"p", "ul", "ol"}:
            tag.attrs = {}
        elif tag.name == "li":
            tag.attrs = {}
        elif tag.name == "br":
            tag.attrs = {}
        elif tag.name == "span":
            style = _filter_supported_inline_style(tag.get("style", ""))
            tag.attrs = {"style": style} if style else {}
    return "".join(str(child) for child in body.contents).strip()


def _render_standalone_media_container_html(container: Tag, base_url: str) -> str:
    title = _select_presentation_title(container)
    media_html = _extract_container_media_html(container, base_url)
    rendered_media = _render_section_media_html(media_html, center=True)
    if not rendered_media:
        return ""
    parts = ['<div class="etr-media-block" style="margin:24px auto;">']
    if title:
        parts.append(f'<h2 style="text-align:left">{escape(title)}</h2>')
    parts.append(rendered_media)
    parts.append("</div>")
    return "".join(parts)


def _extract_container_media_html(container: Tag, base_url: str) -> str:
    media_node = (
        container
        if container.name in {"iframe", "video"}
        else container.find(["iframe", "video"])
    )
    if not isinstance(media_node, Tag):
        return ""
    fragment = BeautifulSoup(str(media_node), "lxml")
    media = fragment.find(["iframe", "video"])
    if not isinstance(media, Tag):
        return ""
    for tag in [media, *media.find_all(["source"])]:
        src = tag.get("src")
        if src:
            tag["src"] = make_absolute_url(src, base_url)
    poster = media.get("poster")
    if poster:
        media["poster"] = make_absolute_url(poster, base_url)
    for tag in fragment.find_all(True):
        if tag.name not in {"iframe", "video", "source"}:
            tag.unwrap()
            continue
        if tag.name == "iframe":
            allowed = {
                key: tag.get(key)
                for key in ["src", "title", "allow", "allowfullscreen"]
                if tag.get(key) is not None
            }
            tag.attrs = allowed
        elif tag.name == "video":
            allowed = {
                key: tag.get(key)
                for key in [
                    "src",
                    "poster",
                    "autoplay",
                    "loop",
                    "muted",
                    "playsinline",
                    "controls",
                ]
                if tag.get(key) is not None
            }
            tag.attrs = allowed
        elif tag.name == "source":
            allowed = {
                key: tag.get(key) for key in ["src", "type"] if tag.get(key) is not None
            }
            tag.attrs = allowed
    return str(media).strip()


def _render_section_media_html(
    media_html: str, *, align_right: bool = False, center: bool = False
) -> str:
    if not media_html.strip():
        return ""
    fragment = BeautifulSoup(media_html, "lxml")
    media = fragment.find(["iframe", "video"])
    if not isinstance(media, Tag):
        return ""
    if media.name == "iframe":
        media["style"] = "display:block; width:100%; height:100%; border:0;"
        media["width"] = "750"
        media["height"] = "510"
        media["loading"] = "lazy"
        if media.get("allowfullscreen") is not None:
            media["allowfullscreen"] = ""
    else:
        media["style"] = "display:block; width:100%; height:100%; object-fit:cover;"
        media["width"] = "750"
        media["height"] = "510"
        if media.get("controls") is None and media.get("autoplay") is None:
            media["controls"] = ""
    align_style = ""
    if center:
        align_style = " margin-left:auto; margin-right:auto;"
    elif align_right:
        align_style = " margin-left:auto; margin-right:0;"
    return (
        '      <div class="etr-media" '
        f'style="display:block; width:750px; max-width:100%; aspect-ratio:750/510; overflow:hidden; border-radius:12px;{align_style}">'
        f"{media}"
        "</div>"
    )


def _render_section_body_html(
    body_html: str, body_text: str, *, force_note_style: bool = False
) -> str:
    normalized_html = (
        normalize_whitespace(BeautifulSoup(body_html, "lxml").get_text(" ", strip=True))
        if body_html
        else ""
    )
    if normalized_html:
        return f'      <div class="etr-copy" style="font-size:22px">{_apply_preserved_note_styles(body_html, force_note_style=force_note_style)}</div>'
    return f'      <p><span style="font-size:22px">{escape(body_text)}</span></p>'


def _render_appendix_block(block: dict[str, str]) -> list[str]:
    out = ['  <div class="etr-sec appendix">', '    <div class="etr-text">']
    out.append(
        _render_section_body_html(
            str(block.get("body_html", "")),
            str(block.get("paragraph", "")),
            force_note_style=True,
        )
    )
    image_url = normalize_whitespace(block.get("image_url", ""))
    if image_url:
        out.append(
            f'      <img alt="" src="{escape(image_url, quote=True)}" '
            'style="display:inline-block; vertical-align:middle; width:min(60px, 14vw); max-width:60px; height:auto; margin-left:12px;" />'
        )
    out.append("    </div>")
    out.append("  </div>")
    out.append("")
    return out


def _apply_preserved_note_styles(
    body_html: str, *, force_note_style: bool = False
) -> str:
    fragment = BeautifulSoup(body_html, "lxml")
    body = fragment.body or fragment
    for tag in body.find_all(["p", "li"]):
        text = normalize_whitespace(tag.get_text(" ", strip=True))
        if not text:
            continue
        if force_note_style or _looks_like_preserved_note(text):
            tag["style"] = _merge_inline_styles(
                tag.get("style", ""), "font-size:12px; font-style:italic;"
            )
    return "".join(str(child) for child in body.contents).strip()


def _looks_like_preserved_note(text: str) -> bool:
    return text.startswith("*")


def _filter_supported_inline_style(raw_style: str) -> str:
    allowed_properties = {"font-size"}
    cleaned_parts: list[str] = []
    for part in str(raw_style or "").split(";"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        normalized_key = normalize_whitespace(key).lower()
        normalized_value = normalize_whitespace(value)
        if normalized_key in allowed_properties and normalized_value:
            cleaned_parts.append(f"{normalized_key}:{normalized_value}")
    return "; ".join(cleaned_parts)


def _merge_inline_styles(existing: str, addition: str) -> str:
    merged: dict[str, str] = {}
    for style in [existing, addition]:
        for part in str(style or "").split(";"):
            if ":" not in part:
                continue
            key, value = part.split(":", 1)
            normalized_key = normalize_whitespace(key).lower()
            normalized_value = normalize_whitespace(value)
            if normalized_key and normalized_value:
                merged[normalized_key] = normalized_value
    return "; ".join(f"{key}:{value}" for key, value in merged.items()) + (
        ";" if merged else ""
    )


def _blocks_from_text(source_text: str) -> list[dict[str, str]]:
    lines = split_visible_lines(source_text)
    if not lines:
        return []
    blocks: list[dict[str, str]] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if line.isupper() or (
            len(line) < 90 and idx + 1 < len(lines) and len(lines[idx + 1]) > 20
        ):
            title = line
            idx += 1
            paragraphs: list[str] = []
            while (
                idx < len(lines) and not lines[idx].isupper() and len(lines[idx]) > 10
            ):
                paragraphs.append(lines[idx])
                idx += 1
            paragraph = normalize_whitespace(" ".join(paragraphs))
            if title and paragraph:
                blocks.append(
                    {
                        "title": title.title() if title.isupper() else title,
                        "paragraph": paragraph,
                        "image_url": "",
                    }
                )
            continue
        idx += 1
    return blocks
