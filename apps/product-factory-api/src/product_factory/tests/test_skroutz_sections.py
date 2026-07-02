import json
import sys
import types
from pathlib import Path

import product_factory.prepare_section_assets as section_assets_module
from product_factory.fetcher import ElectronetFetcher
from product_factory.html_builders import extract_presentation_blocks
from product_factory.models import GalleryImage
from product_factory.prepare_section_assets import resolve_skroutz_section_assets
from product_factory.skroutz_sections import (
    build_skroutz_presentation_source_html,
    extract_skroutz_section_window,
    is_placeholder_image_url,
    resolve_skroutz_section_image_url,
)

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


def test_143481_html_fixture_resolves_9_sections_in_stable_order(
    skroutz_fixtures_root: Path,
) -> None:
    html = (skroutz_fixtures_root / "html" / "143481.html").read_text(encoding="utf-8")
    extracted = extract_skroutz_section_window(html, SAMPLE["url"])

    assert extracted["window"]["start_anchor"] == "Περιγραφή"
    assert extracted["window"]["stop_anchor"] == "Κατασκευαστής"
    assert extracted["window"]["duplicate_signatures_skipped"] == 1
    assert [section["title"] for section in extracted["sections"]] == EXPECTED_TITLES
    assert len(extracted["sections"]) == 9
    assert "Χρυσή γωνία 60°" in extracted["sections"][3]["paragraph"]
    assert (
        "Εξαιρετικά υψηλός ρυθμός ανάκλασης υπερήχων"
        in extracted["sections"][3]["paragraph"]
    )
    assert extracted["sections"][0]["image_candidates"][0].endswith("transparent.gif")


def test_placeholder_urls_are_rejected_for_resolved_section_images(
    skroutz_fixtures_root: Path,
) -> None:
    rendered = json.loads(
        (
            skroutz_fixtures_root
            / "rendered_sections"
            / "143481.rendered_sections.json"
        ).read_text(encoding="utf-8")
    )
    lazy_attr = rendered["sections"][0]["image_record"]["lazy_attrs"][
        "data-lazy-media-src-value"
    ]
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
    assert all(
        is_placeholder_image_url(section["resolved_image_url"]) is False
        for section in rendered["sections"]
    )


def test_skroutz_embedded_video_section_is_extracted_as_presentation_block() -> None:
    html = """
    <div class="sku-description">
      <div class="rich-components">
        <section class="two-column">
          <div class="column">
            <h2>Steam cleaning demo</h2>
            <div class="body-text"><p>Watch the cleaner remove dirt from tiles.</p></div>
          </div>
          <div class="column">
            <iframe src="/embedded/demo" title="Demo video" allowfullscreen></iframe>
          </div>
        </section>
      </div>
    </div>
    """

    extracted = extract_skroutz_section_window(html, "https://www.skroutz.gr/p/demo")

    assert len(extracted["sections"]) == 1
    assert extracted["sections"][0]["image_url"] == ""
    assert extracted["sections"][0]["media_html"].startswith("<iframe")
    assert (
        'src="https://www.skroutz.gr/embedded/demo"'
        in extracted["sections"][0]["media_html"]
    )

    rebuilt = build_skroutz_presentation_source_html(extracted["sections"])
    blocks = extract_presentation_blocks(
        rebuilt, "", base_url="https://www.skroutz.gr/p/demo"
    )

    assert blocks == [
        {
            "title": "Steam cleaning demo",
            "paragraph": "Watch the cleaner remove dirt from tiles.",
            "image_url": "",
            "media_html": '<iframe allowfullscreen="" src="https://www.skroutz.gr/embedded/demo" title="Demo video"></iframe>',
        }
    ]


def test_skroutz_lazy_embedded_video_section_without_body_is_valid() -> None:
    html = """
    <div class="sku-description">
      <div class="rich-components">
        <section class="one-column">
          <h2>Video section</h2>
          <div class="placeholder" data-lazy-media-src-value="//www.youtube.com/embed/example">
            <iframe src="//www.skroutz.gr/assets/transparent.gif" title="Demo video" allowfullscreen></iframe>
          </div>
        </section>
      </div>
    </div>
    """

    extracted = extract_skroutz_section_window(html, "https://www.skroutz.gr/p/demo")

    assert extracted["sections"] == [
        {
            "title": "Video section",
            "paragraph": "",
            "image_url": "",
            "media_html": '<iframe allowfullscreen="" src="https://www.youtube.com/embed/example" title="Demo video"></iframe>',
            "image_candidates": [],
        }
    ]

    rebuilt = build_skroutz_presentation_source_html(extracted["sections"])
    blocks = extract_presentation_blocks(rebuilt, "", base_url="https://www.skroutz.gr/p/demo")

    assert blocks == [
        {
            "title": "Video section",
            "paragraph": "",
            "image_url": "",
            "media_html": '<iframe allowfullscreen="" src="https://www.youtube.com/embed/example" title="Demo video"></iframe>',
        }
    ]


def test_resolve_skroutz_section_assets_skips_text_only_interludes(
    monkeypatch, tmp_path: Path
) -> None:
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
                    "title_signature": [
                        section["title"] for section in rendered_sections
                    ],
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
    assert [section["title"] for section in result.selected_presentation_blocks] == [
        "Section 1",
        "Section 3",
        "Section 4",
    ]
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


def test_rendered_section_extraction_skips_non_presentation_titles_and_tolerates_networkidle_timeout(
    monkeypatch,
) -> None:
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
                "lazy_attrs": {
                    "data-lazy-media-src-value": "https://b.scdn.gr/test-image.png"
                },
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
                    FakeSectionLocator(
                        "Κανονική Ενότητα", "Περιγραφή ενότητας", image_record
                    ),
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

    fake_sync_api = types.SimpleNamespace(
        sync_playwright=lambda: FakePlaywrightContextManager()
    )
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)

    fetcher = ElectronetFetcher()
    monkeypatch.setattr(
        fetcher, "_robots_allowed", lambda url: (True, "robots_unavailable")
    )
    rendered = fetcher.extract_skroutz_section_image_records(SAMPLE["url"])

    assert [section["title"] for section in rendered["sections"]] == [
        "Κανονική Ενότητα"
    ]
    assert (
        rendered["sections"][0]["resolved_image_url"]
        == "https://b.scdn.gr/test-image.png"
    )
