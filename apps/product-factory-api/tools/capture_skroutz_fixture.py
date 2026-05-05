from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import sys
from pathlib import Path

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

from pipeline.fetcher import ElectronetFetcher
from pipeline.skroutz_sections import extract_skroutz_section_window
from pipeline.skroutz_taxonomy import normalize_category_href_slug


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture and normalize a Skroutz fixture for local regression use.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


def normalize_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for node in soup.select("script, noscript"):
        node.decompose()
    for node in soup.select("[data-reactroot], [data-hypernova-id], [nonce]"):
        for attr in ["data-reactroot", "data-hypernova-id", "nonce"]:
            if node.has_attr(attr):
                del node[attr]
    return soup.prettify()


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fetcher = ElectronetFetcher()
    fetch = fetcher.fetch_playwright(args.url)
    html = normalize_html(fetch.html)
    soup = BeautifulSoup(html, "lxml")

    category_node = soup.select_one("div.sku-title a.category-tag")
    category_tag_text = category_node.get_text(" ", strip=True) if category_node else ""
    category_tag_href = category_node.get("href", "") if category_node else ""
    title_node = soup.select_one("div.sku-title h1.page-title")
    name = title_node.get_text(" ", strip=True) if title_node else ""
    brand_node = soup.select_one("a.brand-page-link img, a.brand-page-link span")
    manufacturer = (brand_node.get("alt", "") if getattr(brand_node, "name", "") == "img" else brand_node.get_text(" ", strip=True)) if brand_node else ""
    section_window = extract_skroutz_section_window(html, base_url=fetch.final_url)

    html_path = output_dir / f"{args.model}.html"
    meta_path = output_dir / f"{args.model}.meta.json"
    html_path.write_text(html, encoding="utf-8")

    metadata = {
        "model": args.model,
        "source_url": args.url,
        "final_url": fetch.final_url,
        "name": name,
        "manufacturer": manufacturer,
        "category_tag_text": category_tag_text,
        "category_tag_href": category_tag_href,
        "normalized_category_slug": normalize_category_href_slug(category_tag_href),
        "has_besco_sections": bool(section_window.get("sections")),
        "detected_besco_section_count": len(section_window.get("sections", [])),
        "taxonomy_hint": "",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "content_hash": hashlib.sha256(html.encode("utf-8")).hexdigest(),
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
