import csv
import json
import sys
import types
from pathlib import Path

from bs4 import BeautifulSoup

import pipeline.prepare_section_assets as section_assets_module
from pipeline.fetcher import ElectronetFetcher
from pipeline.models import CLIInput, FetchResult, GalleryImage
from pipeline.prepare_section_assets import resolve_skroutz_section_assets
from pipeline.skroutz_sections import extract_skroutz_section_window, is_placeholder_image_url, resolve_skroutz_section_image_url
from pipeline.workflow import prepare_workflow, render_workflow

JPEG_BYTES = b"\xff\xd8\xff\xdb\x00C\x00" + (b"\x08" * 64) + b"\xff\xd9"
SAMPLE = {
    "model": "143481",
    "url": "https://www.skroutz.gr/s/61800471/tcl-q65h-soundbar-5-1-bluetooth-hdmi-kai-wi-fi-me-asyrmato-subwoofer-mayro.html",
    "photos": 8,
    "sections": 9,
    "skroutz_status": 1,
    "boxnow": 0,
    "price": "269",
}
EXPECTED_TITLES = [
    "Καλός ήχος από όλες τις κατευθύνσεις",
    "Ευρύτερο ηχητικό πεδίο, καθαρότερος ήχος",
    "Προσαρμοσμένο τουίτερ:",
    "Ενισχυμένη Κόρνα 60°*:",
    "Ισορροπημένη βελτιστοποίηση, ευρύτερο ηχητικό πεδίο",
    "Τρισδιάστατο πραγματικό surround 360°, βυθιστείτε στο περιεχόμενο",
    "Υψηλή πιστότητα, συγκινητικές καρδιές.",
    "Καθαρά φωνητικά, καθηλωτικοί διάλογοι",
    "Διαφανείς υψηλές συχνότητες, μαγευτική μουσική",
]


def read_csv_row(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.DictReader(handle))


def write_split_llm_outputs_from_baseline(model_root: Path, path: Path) -> None:
    row = read_csv_row(path)
    llm_dir = model_root / "llm"
    llm_dir.mkdir(parents=True, exist_ok=True)
    soup = BeautifulSoup(row["description"], "lxml")
    intro_span = soup.select_one("p span")
    (llm_dir / "intro_text.output.txt").write_text(
        intro_span.get_text(" ", strip=True) if intro_span else "",
        encoding="utf-8",
    )
    (llm_dir / "seo_meta.output.json").write_text(
        json.dumps(
            {
                "product": {
                    "meta_description": row["meta_description"],
                    "meta_keywords": [item.strip() for item in row["meta_keyword"].split(",") if item.strip()],
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def install_143481_fixture_fetcher(monkeypatch, skroutz_fixtures_root: Path) -> None:
    from pipeline import fetcher

    def fake_fetch_httpx(self, url: str):
        raise fetcher.FetchError(f"httpx disabled for test: {url}")

    def fake_fetch_playwright(self, url: str):
        html = (skroutz_fixtures_root / "html" / "143481.html").read_text(encoding="utf-8")
        return FetchResult(url=url, final_url=url, html=html, status_code=200, method="playwright", fallback_used=True, response_headers={})

    def fake_fetch_binary(self, url: str):
        return JPEG_BYTES, "image/jpeg"

    def fake_extract_skroutz_section_image_records(self, url: str):
        return json.loads((skroutz_fixtures_root / "rendered_sections" / "143481.rendered_sections.json").read_text(encoding="utf-8"))

    monkeypatch.setattr(fetcher.ElectronetFetcher, "fetch_httpx", fake_fetch_httpx)
    monkeypatch.setattr(fetcher.ElectronetFetcher, "fetch_playwright", fake_fetch_playwright)
    monkeypatch.setattr(fetcher.ElectronetFetcher, "fetch_binary", fake_fetch_binary)
    monkeypatch.setattr(fetcher.ElectronetFetcher, "extract_skroutz_section_image_records", fake_extract_skroutz_section_image_records)


def test_143481_html_fixture_resolves_9_sections_in_stable_order(skroutz_fixtures_root: Path) -> None:
    html = (skroutz_fixtures_root / "html" / "143481.html").read_text(encoding="utf-8")
    extracted = extract_skroutz_section_window(html, SAMPLE["url"])

    assert extracted["window"]["start_anchor"] == "Περιγραφή"
    assert extracted["window"]["stop_anchor"] == "Κατασκευαστής"
    assert extracted["window"]["duplicate_signatures_skipped"] == 1
    assert [section["title"] for section in extracted["sections"]] == EXPECTED_TITLES
    assert len(extracted["sections"]) == 9
    assert "Χρυσή γωνία 60°" in extracted["sections"][3]["paragraph"]
    assert "Εξαιρετικά υψηλός ρυθμός ανάκλασης υπερήχων" in extracted["sections"][3]["paragraph"]
    assert extracted["sections"][0]["image_candidates"][0].endswith("transparent.gif")


def test_placeholder_urls_are_rejected_for_resolved_section_images(skroutz_fixtures_root: Path) -> None:
    rendered = json.loads((skroutz_fixtures_root / "rendered_sections" / "143481.rendered_sections.json").read_text(encoding="utf-8"))
    lazy_attr = rendered["sections"][0]["image_record"]["lazy_attrs"]["data-lazy-media-src-value"]
    record = {
        "currentSrc": "",
        "img_attrs": {"src": "//www.skroutz.gr/assets/transparent.gif"},
        "lazy_attrs": {"data-lazy-media-src-value": lazy_attr},
        "ancestor_data_attrs": {},
        "source_srcsets": [],
    }

    resolved = resolve_skroutz_section_image_url(record, base_url=SAMPLE["url"])
    assert is_placeholder_image_url(record["img_attrs"]["src"]) is True
    assert is_placeholder_image_url(resolved) is False
    assert resolved.endswith(".png")
    assert all(is_placeholder_image_url(section["resolved_image_url"]) is False for section in rendered["sections"])


def test_resolve_skroutz_section_assets_skips_text_only_interludes(monkeypatch, tmp_path: Path) -> None:
    all_sections = [
        {"title": "Section 1", "paragraph": "Body 1", "image_candidates": []},
        {"title": "Section 2", "paragraph": "Body 2", "image_candidates": []},
        {"title": "Section 3", "paragraph": "Body 3", "image_candidates": []},
        {"title": "Section 4", "paragraph": "Body 4", "image_candidates": []},
    ]
    rendered_sections = [
        {"title": "Section 1", "resolved_image_url": "https://example.com/1.jpg"},
        {"title": "Section 2", "resolved_image_url": ""},
        {"title": "Section 3", "resolved_image_url": "https://example.com/3.jpg"},
        {"title": "Section 4", "resolved_image_url": "https://example.com/4.jpg"},
    ]

    class RecordingFetcher:
        def __init__(self) -> None:
            self.rendered_calls = []
            self.download_calls = []

        def extract_skroutz_section_image_records(self, url: str):
            self.rendered_calls.append(url)
            return {
                "window": {
                    "candidate_count": 4,
                    "duplicate_signatures_skipped": 0,
                    "selected_container_index": 0,
                    "start_anchor": "Description",
                    "stop_anchor": "Manufacturer",
                    "title_signature": [section["title"] for section in rendered_sections],
                },
                "sections": rendered_sections,
            }

        def download_besco_images(self, **kwargs):
            self.download_calls.append(kwargs)
            images = [
                GalleryImage(
                    url=image.url,
                    alt=image.alt,
                    position=image.position,
                    local_filename=f"besco{image.position}.jpg",
                    local_path=str(tmp_path / f"besco{image.position}.jpg"),
                    downloaded=True,
                )
                for image in kwargs["images"]
            ]
            return images, [], [image.local_path for image in images]

    fetcher = RecordingFetcher()

    monkeypatch.setattr(
        section_assets_module,
        "extract_skroutz_section_window",
        lambda *_args, **_kwargs: {
            "warnings": [],
            "window": {
                "candidate_count": 4,
                "duplicate_signatures_skipped": 0,
                "selected_container_index": 0,
                "start_anchor": "Description",
                "stop_anchor": "Manufacturer",
                "title_signature": [section["title"] for section in all_sections],
            },
            "sections": all_sections,
        },
    )

    result = resolve_skroutz_section_assets(
        requested_sections=3,
        fetch_html="<html></html>",
        final_url=SAMPLE["url"],
        canonical_url=SAMPLE["url"],
        url=SAMPLE["url"],
        presentation_source_html="",
        presentation_source_text="",
        manufacturer_enrichment={"presentation_applied": False},
        fetcher=fetcher,
        output_dir=tmp_path,
    )

    assert fetcher.rendered_calls == [SAMPLE["url"]]
    assert [section["title"] for section in result.selected_presentation_blocks] == ["Section 1", "Section 3", "Section 4"]
    assert [image.url for image in result.selected_besco_images] == [
        "https://example.com/1.jpg",
        "https://example.com/3.jpg",
        "https://example.com/4.jpg",
    ]
    assert result.section_image_urls_resolved == [
        {"position": 1, "title": "Section 1", "url": "https://example.com/1.jpg"},
        {"position": 2, "title": "Section 3", "url": "https://example.com/3.jpg"},
        {"position": 3, "title": "Section 4", "url": "https://example.com/4.jpg"},
    ]


def test_rendered_section_extraction_skips_non_presentation_titles_and_tolerates_networkidle_timeout(monkeypatch) -> None:
    class FakeSimpleLocator:
        def __init__(self, count: int = 0, text: str = "", payload: dict | None = None):
            self._count = count
            self._text = text
            self._payload = payload or {}
            self.first = self

        def count(self):
            return self._count

        def inner_text(self, timeout=None):
            return self._text

        def evaluate(self, script):
            return self._payload

    class FakeSectionLocator:
        def __init__(self, title: str, body: str, image_record: dict):
            self._title = title
            self._body = body
            self._image_record = image_record

        def scroll_into_view_if_needed(self, timeout=None):
            return None

        def locator(self, selector: str):
            if selector == "h2, h3, h4":
                return FakeSimpleLocator(count=1, text=self._title)
            if selector == ".body-text":
                return FakeSimpleLocator(count=1, text=self._body)
            if selector == "img":
                return FakeSimpleLocator(count=1, payload=self._image_record)
            raise AssertionError(f"Unexpected section selector: {selector}")

    class FakeSectionsLocator:
        def __init__(self, sections):
            self._sections = sections

        def count(self):
            return len(self._sections)

        def nth(self, index: int):
            return self._sections[index]

    class FakeContainerEntry:
        def __init__(self, meta: dict, sections):
            self._meta = meta
            self._sections = sections

        def evaluate(self, script, index):
            return self._meta

        def locator(self, selector: str):
            if selector == "div.rich-components section":
                return FakeSectionsLocator(self._sections)
            raise AssertionError(f"Unexpected container selector: {selector}")

    class FakeContainerLocator:
        def __init__(self, entry):
            self._entry = entry

        def count(self):
            return 1

        def nth(self, index: int):
            assert index == 0
            return self._entry

    class FakePage:
        def __init__(self):
            image_record = {
                "currentSrc": "",
                "img_attrs": {"src": "//www.skroutz.gr/assets/transparent.gif"},
                "lazy_attrs": {"data-lazy-media-src-value": "https://b.scdn.gr/test-image.png"},
                "ancestor_data_attrs": {},
                "source_srcsets": [],
            }
            self.url = SAMPLE["url"]
            self._container = FakeContainerEntry(
                meta={
                    "dom_index": 0,
                    "title_count": 3,
                    "titles": ["Με μια ματιά", "Κανονική Ενότητα", "Οι χρήστες είπαν:"],
                    "width": 100,
                    "height": 100,
                    "visible_area": 10000,
                },
                sections=[
                    FakeSectionLocator("Με μια ματιά", "skip", image_record),
                    FakeSectionLocator("Κανονική Ενότητα", "Περιγραφή ενότητας", image_record),
                    FakeSectionLocator("Οι χρήστες είπαν:", "skip", image_record),
                ],
            )

        def goto(self, url, wait_until=None, timeout=None):
            return None

        def wait_for_load_state(self, state, timeout=None):
            raise Exception("network still busy")

        def wait_for_timeout(self, timeout):
            return None

        def locator(self, selector: str):
            if selector == "div.sku-description":
                return FakeContainerLocator(self._container)
            raise AssertionError(f"Unexpected page selector: {selector}")

    class FakeContext:
        def new_page(self):
            return FakePage()

    class FakeBrowser:
        def new_context(self, user_agent=None, locale=None):
            return FakeContext()

        def close(self):
            return None

    class FakeChromium:
        def launch(self, headless=True):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightContextManager:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_sync_api = types.SimpleNamespace(sync_playwright=lambda: FakePlaywrightContextManager())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)

    fetcher = ElectronetFetcher()
    monkeypatch.setattr(fetcher, "_robots_allowed", lambda url: (True, "robots_unavailable"))
    rendered = fetcher.extract_skroutz_section_image_records(SAMPLE["url"])

    assert [section["title"] for section in rendered["sections"]] == ["Κανονική Ενότητα"]
    assert rendered["sections"][0]["resolved_image_url"] == "https://b.scdn.gr/test-image.png"


def test_143481_rendered_description_preserves_locked_wrappers(
    tmp_path: Path,
    monkeypatch,
    skroutz_fixtures_root: Path,
    skroutz_golden_outputs_root: Path,
) -> None:
    from pipeline import workflow

    install_143481_fixture_fetcher(monkeypatch, skroutz_fixtures_root)
    monkeypatch.setattr(workflow, "WORK_ROOT", tmp_path / "work")
    monkeypatch.setattr(workflow, "PRODUCTS_ROOT", tmp_path / "products")
    (tmp_path / "products").mkdir(parents=True, exist_ok=True)
    (tmp_path / "products" / "143481.csv").write_text(
        (skroutz_golden_outputs_root / "143481.csv").read_text(encoding="utf-8-sig"),
        encoding="utf-8",
    )

    cli = CLIInput(
        model=SAMPLE["model"],
        url=SAMPLE["url"],
        photos=SAMPLE["photos"],
        sections=SAMPLE["sections"],
        skroutz_status=SAMPLE["skroutz_status"],
        boxnow=SAMPLE["boxnow"],
        price=SAMPLE["price"],
        out="unused",
    )
    prepare_result = prepare_workflow(cli)
    write_split_llm_outputs_from_baseline(prepare_result.model_root, skroutz_golden_outputs_root / "143481.csv")

    render_result = render_workflow("143481")
    description = render_result.description_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(description, "lxml")
    section_nodes = soup.select("div.etr-sec, div.etr-sec.rev")
    besco_dir = prepare_result.scrape_dir / "bescos"
    besco_filenames = [f"besco{index}.jpg" for index in range(1, 10)]

    assert render_result.run_status.value == "completed"
    assert "presentation_sections_weak:2" in render_result.validation_report.warnings
    assert description.count('class="etr-sec"') == 5
    assert description.count('class="etr-sec rev"') == 4
    assert description.count("<!-- SECTION ") == 9
    assert len(section_nodes) == 9
    assert sorted(path.name for path in besco_dir.glob("*.jpg")) == besco_filenames

    for index, section in enumerate(section_nodes, start=1):
        expected_class = ["etr-sec", "rev"] if index % 2 == 0 else ["etr-sec"]
        assert section.get("class") == expected_class
        direct_children = [child for child in section.find_all(recursive=False)]
        assert [child.get("class") for child in direct_children] == [["etr-text"], ["etr-img"]]
        image = section.select_one(".etr-img img")
        assert image is not None
        assert image.get("src", "").rsplit("/", 1)[-1] in besco_filenames
        if index % 2 == 0:
            assert image.get("style") == "display:block; margin-left:auto; margin-right:0;"
        else:
            assert image.get("style") is None

