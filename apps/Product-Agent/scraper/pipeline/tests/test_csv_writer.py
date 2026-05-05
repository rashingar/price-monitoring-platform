from pathlib import Path

from pipeline.csv_writer import write_csv_row
from pipeline.html_builders import (
    build_characteristics_html,
    build_description_html,
    build_description_html_from_intro_and_sections,
    extract_presentation_blocks,
)
from pipeline.models import SpecItem, SpecSection



def test_csv_header_order_preserved_from_template(tmp_path: Path) -> None:
    template = tmp_path / "template.csv"
    template.write_text("b,a,c\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    headers, ordered = write_csv_row({"a": "1", "b": "2", "c": "3"}, out, template)
    assert headers == ["b", "a", "c"]
    assert ordered == {"b": "2", "a": "1", "c": "3"}
    assert out.read_text(encoding="utf-8").splitlines()[0] == "b,a,c"



def test_characteristics_html_and_safe_blank_description() -> None:
    html = build_characteristics_html(
        [
            SpecSection(
                section="Γενικά Χαρακτηριστικά",
                items=[
                    SpecItem("Χρώμα", "Κόκκινο"),
                    SpecItem("Διαστάσεις", "179.00 x 91.30 x 73.50"),
                    SpecItem("Πλάτος Συσκευής σε Εκατοστά", "91,3"),
                    SpecItem("Επιπλέον Χαρακτηριστικά", "χειρολαβή με εσοχή,σύστημα διάγνωσης βλαβών"),
                    SpecItem("Επιπλέον", None),
                ],
            )
        ]
    )
    assert '<table class="table table-bordered">' in html
    assert "<td colspan=\"2\"><strong>Γενικά Χαρακτηριστικά</strong></td>" in html
    assert '<td style="text-align:right;"><strong>Κόκκινο</strong></td>' in html
    assert '<td style="text-align:right;"><strong>179.00 × 91.30 × 73.50</strong></td>' in html
    assert '<td style="text-align:right;"><strong>91.30</strong></td>' in html
    assert html.count('<td style="text-align:right;"><strong>-</strong></td>') >= 2
    description, warnings = build_description_html(
        product_name="Σκούπα",
        hero_summary="",
        presentation_source_html="",
        presentation_source_text="",
        model="343700",
        sections_requested=3,
        cta_url="https://www.etranoulis.gr/example",
        cta_label="Σκούπες Stick",
    )
    assert description == ""
    assert "description_not_built_from_source" in warnings


def test_presentation_blocks_extract_images_and_description_uses_downloaded_bescos() -> None:
    presentation_html = """
    <h3>Section One</h3>
    <p>Paragraph one.</p>
    <img src="/image/catalog/products/343700/section-one.webp" />
    <h3>Section Two</h3>
    <p>Paragraph two.</p>
    """

    blocks = extract_presentation_blocks(
        presentation_source_html=presentation_html,
        presentation_source_text="",
        base_url="https://www.electronet.gr/product/example",
    )

    assert blocks[0]["image_url"] == "https://www.electronet.gr/image/catalog/products/343700/section-one.webp"

    description, warnings = build_description_html(
        product_name="Example Product",
        hero_summary="Intro text",
        presentation_source_html=presentation_html,
        presentation_source_text="",
        model="343700",
        sections_requested=2,
        cta_url="https://www.etranoulis.gr/example",
        cta_label="Category",
        besco_filenames_by_section={1: "besco1.webp"},
    )

    assert warnings == []
    assert "01_bescos/343700/besco1.webp" in description
    assert "01_bescos/343700/besco2.jpg" not in description


def test_description_uses_parent_tv_cta_text() -> None:
    description, warnings = build_description_html(
        product_name="Example TV",
        hero_summary="Intro text",
        presentation_source_html="<h3>Section One</h3><p>Paragraph one.</p>",
        presentation_source_text="",
        model="143051",
        sections_requested=1,
        cta_url="https://www.etranoulis.gr/eikona-hxos/thleoraseis",
        cta_label="Τηλεοράσεις",
    )

    assert warnings == []
    assert 'href="https://www.etranoulis.gr/eikona-hxos/thleoraseis"' in description
    assert "Δείτε περισσότερες Τηλεοράσεις εδώ" in description


def test_presentation_blocks_extract_images_from_left_and_right_banner_layouts() -> None:
    presentation_html = """
    <div class="ck-text inline">
      <div class="middle-align">
        <h2>Brand Tagline</h2>
        <h3>Section One</h3>
        <p>Paragraph one.</p>
      </div>
      <div class="image"><img src="/media/right.jpg" /></div>
    </div>
    <div class="ck-text inline left-banner">
      <div class="image"><img src="/media/left.jpg" /></div>
      <div class="middle-align">
        <h2>Section Two</h2>
        <p>Paragraph two.</p>
      </div>
    </div>
    """

    blocks = extract_presentation_blocks(
        presentation_source_html=presentation_html,
        presentation_source_text="",
        base_url="https://www.electronet.gr/product/example",
    )

    assert len(blocks) == 2
    assert blocks[0]["title"] == "Section One"
    assert blocks[0]["image_url"] == "https://www.electronet.gr/media/right.jpg"
    assert blocks[0]["body_html"] == "<p>Paragraph one.</p>"
    assert blocks[1]["title"] == "Section Two"
    assert blocks[1]["image_url"] == "https://www.electronet.gr/media/left.jpg"
    assert blocks[1]["body_html"] == "<p>Paragraph two.</p>"


def test_presentation_blocks_extract_list_based_electronet_sections() -> None:
    presentation_html = """
    <div class="ck-text whole">
      <iframe src="https://www.youtube.com/embed/example"></iframe>
    </div>
    <div class="ck-text inline">
      <div class="middle-align">
        <h2>Section One</h2>
        <p>Paragraph one.</p>
      </div>
      <div class="image"><img src="/media/one.jpg" /></div>
    </div>
    <div class="ck-text inline left-banner">
      <div class="image"><img src="/media/two.jpg" /></div>
      <div class="middle-align">
        <h2>Section Two</h2>
        <ul>
          <li>Bullet one.</li>
          <li>Bullet two.</li>
        </ul>
      </div>
    </div>
    <div class="ck-text inline">
      <div class="middle-align">
        <h2>Section Three</h2>
        <ul>
          <li>Bullet three.</li>
          <li>Bullet four.</li>
        </ul>
      </div>
      <div class="image"><img src="/media/three.jpg" /></div>
    </div>
    <div class="ck-text inline left-banner">
      <div class="image"><img src="/media/four.jpg" /></div>
      <div class="middle-align">
        <h2>Section Four</h2>
        <ul>
          <li>Bullet five.</li>
          <li>Bullet six.</li>
        </ul>
      </div>
    </div>
    """

    blocks = extract_presentation_blocks(
        presentation_source_html=presentation_html,
        presentation_source_text="",
        base_url="https://www.electronet.gr/product/example",
    )

    assert len(blocks) == 4
    assert blocks[1]["title"] == "Section Two"
    assert blocks[1]["paragraph"] == "Bullet one. Bullet two."
    assert blocks[1]["image_url"] == "https://www.electronet.gr/media/two.jpg"
    assert blocks[1]["body_html"] == "<ul>\n<li>Bullet one.</li>\n<li>Bullet two.</li>\n</ul>"
    assert blocks[3]["title"] == "Section Four"
    assert blocks[3]["paragraph"] == "Bullet five. Bullet six."
    assert blocks[3]["image_url"] == "https://www.electronet.gr/media/four.jpg"
    assert "<ul>" in blocks[3]["body_html"]


def test_description_html_preserves_video_embed_and_list_markup() -> None:
    presentation_html = """
    <div class="ck-text whole">
      <h2>Intro Video</h2>
      <video autoplay="" loop="" muted="" playsinline="" style="width: 70%;">
        <source src="/media/demo.mp4" type="video/mp4" />
      </video>
    </div>
    <div class="ck-text inline">
      <div class="middle-align">
        <h2>Section One</h2>
        <ul>
          <li>Bullet one.</li>
          <li>Bullet two.</li>
        </ul>
      </div>
      <div class="image"><img src="/media/right.jpg" /></div>
    </div>
    """

    description, warnings = build_description_html(
        product_name="Example Product",
        hero_summary="Intro text",
        presentation_source_html=presentation_html,
        presentation_source_text="",
        model="343700",
        sections_requested=1,
        cta_url="https://www.etranoulis.gr/example",
        cta_label="Category",
        besco_filenames_by_section={1: "besco1.gif"},
        base_url="https://www.electronet.gr/product/example",
    )

    assert warnings == []
    assert "<video" in description
    assert "https://www.electronet.gr/media/demo.mp4" in description
    assert 'class="etr-media-block"' in description
    assert "aspect-ratio:750/510" in description
    assert "margin-left:auto; margin-right:auto;" in description
    assert description.index("<video") < description.index("<!-- SECTION 1 -->")
    assert "<ul>" in description
    assert "<li>Bullet one.</li>" in description
    assert "01_bescos/343700/besco1.gif" in description


def test_split_description_renders_inline_embed_as_section_media() -> None:
    presentation_html = """
    <div class="ck-text inline left-banner">
      <div class="image">
        <div class="youtube-embed-wrapper" style="position:relative;overflow:hidden;">
          <iframe src="/embed/demo" width="640" height="360" allowfullscreen=""></iframe>
        </div>
      </div>
      <div class="middle-align">
        <h2>Video Section</h2>
        <p>Paragraph one.</p>
      </div>
    </div>
    """

    blocks = extract_presentation_blocks(
        presentation_source_html=presentation_html,
        presentation_source_text="",
        base_url="https://www.electronet.gr/product/example",
    )
    description, warnings = build_description_html_from_intro_and_sections(
        product_name="Example Product",
        model="343700",
        cta_url="https://www.etranoulis.gr/example",
        cta_text="More",
        intro_text="Intro text",
        sections=[{"title": "Video Section", "body_text": "Paragraph one.", "source_index": 1}],
        besco_filenames_by_section={},
        presentation_source_html=presentation_html,
        presentation_source_text="",
        base_url="https://www.electronet.gr/product/example",
    )

    assert warnings == []
    assert blocks[0]["image_url"] == ""
    assert blocks[0]["media_html"].startswith("<iframe")
    assert 'class="etr-img"' in description
    assert 'class="etr-media"' in description
    assert 'width:750px' in description
    assert 'border-radius:12px' in description
    assert 'width="750"' in description
    assert 'height="510"' in description
    assert 'src="https://www.electronet.gr/embed/demo"' in description
    assert description.index('class="etr-text"') < description.index('class="etr-img"')


def test_standalone_youtube_embed_gets_non_collapsing_media_wrapper() -> None:
    presentation_html = """
    <div class="ck-text whole">
      <h2>Midea Infinity Series</h2>
      <div class="image">
        <div class="youtube-embed-wrapper" style="overflow:hidden;position:relative;">
          <iframe
            allowfullscreen=""
            frameborder="0"
            height="100%"
            scrolling="no"
            src="https://www.youtube.com/embed/ZEr5NLPX-84?rel=0"
            style="height:100%;left:0;position:absolute;top:0;width:100%;"
            width="100%">
          </iframe>
        </div>
      </div>
    </div>
    """

    description, warnings = build_description_html_from_intro_and_sections(
        product_name="Midea Fan",
        model="416096",
        cta_url="https://www.etranoulis.gr/fans",
        cta_text="More",
        intro_text="Intro text",
        sections=[],
        besco_filenames_by_section={},
        presentation_source_html=presentation_html,
        presentation_source_text="",
        base_url="https://www.electronet.gr/product/example",
    )

    assert warnings == []
    assert "youtube-embed-wrapper" not in description
    assert 'class="etr-media-block"' in description
    assert "Midea Infinity Series" in description
    assert "aspect-ratio:750/510" in description
    assert 'height="510"' in description
    assert 'src="https://www.youtube.com/embed/ZEr5NLPX-84?rel=0"' in description


def test_split_description_preserves_safe_intro_strong_markup() -> None:
    description, warnings = build_description_html_from_intro_and_sections(
        product_name="Example Product",
        model="343700",
        cta_url="https://www.etranoulis.gr/example",
        cta_text="More",
        intro_text=(
            "Το <strong>Acme AX100</strong> είναι <strong>γενική συσκευή</strong> με A & B και "
            "ουδέτερη περιγραφή που κρατά τις επιβεβαιωμένες πληροφορίες ευανάγνωστες για τον χρήστη."
        ),
        sections=[{"title": "Section One", "body_text": "Paragraph one.", "source_index": 1}],
        besco_filenames_by_section={},
        presentation_source_html="<h2>Section One</h2><p>Paragraph one.</p>",
        presentation_source_text="",
    )

    assert warnings == []
    assert "<strong>Acme AX100</strong>" in description
    assert "<strong>γενική συσκευή</strong>" in description
    assert "A &amp; B" in description


def test_split_description_sanitizes_unsafe_intro_markup() -> None:
    description, warnings = build_description_html_from_intro_and_sections(
        product_name="Example Product",
        model="343700",
        cta_url="https://www.etranoulis.gr/example",
        cta_text="More",
        intro_text='Το <span onclick="bad()">Acme</span> <script>alert(1)</script> μένει κείμενο.',
        sections=[{"title": "Section One", "body_text": "Paragraph one.", "source_index": 1}],
        besco_filenames_by_section={},
        presentation_source_html="<h2>Section One</h2><p>Paragraph one.</p>",
        presentation_source_text="",
    )

    assert "llm_intro_text_emphasis_invalid" in warnings
    assert "<script" not in description
    assert '<span onclick="bad()"' not in description
    assert "&lt;span" not in description
    assert "&lt;script" not in description


def test_split_description_preserves_small_footnotes_and_regulation_appendix() -> None:
    presentation_html = """
    <div class="ck-text inline">
      <div class="middle-align">
        <h2>Section One</h2>
        <p>Main paragraph.</p>
        <p><em><span style="font-size:12px;">* Exact note text.</span></em></p>
      </div>
      <div class="image"><img src="/media/right.jpg" /></div>
    </div>
    <div class="ck-text inline">
      <div class="middle-align">
        <p>Κανονισμός (ΕΕ) 2023/2854<br />Κανονισμός για τα Δεδομένα</p>
      </div>
      <div class="image"><img src="/media/qr.jpg" /></div>
    </div>
    """

    description, warnings = build_description_html_from_intro_and_sections(
        product_name="Example Product",
        model="343700",
        cta_url="https://www.etranoulis.gr/example",
        cta_text="Δείτε περισσότερα εδώ",
        intro_text="Intro text",
        sections=[{"title": "Section One", "body_text": "Main paragraph. * Exact note text.", "source_index": 1}],
        besco_filenames_by_section={1: "besco1.jpg"},
        presentation_source_html=presentation_html,
        presentation_source_text="",
        base_url="https://www.electronet.gr/product/example",
    )

    assert warnings == []
    assert "font-size:12px" in description
    assert "font-style:italic" in description
    assert "* Exact note text." in description
    assert "Κανονισμός (ΕΕ) 2023/2854" not in description
    assert "Κανονισμός για τα Δεδομένα" not in description
    assert 'src="https://www.electronet.gr/media/qr.jpg"' not in description

