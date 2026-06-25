from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

from product_factory.characteristics_pipeline import build_characteristics_for_product
from product_factory.estia_batch_import import (
    build_estia_source_url,
    enqueue_estia_xlsx_batch,
    read_estia_xlsx_rows,
)
from product_factory.jobs.models import JobRecord, JobStatus, JobType
from product_factory.jobs.runner import run_full_pipeline_job
from product_factory.jobs.store import JobStore
from product_factory.deterministic_fields import build_deterministic_product_fields
from product_factory.models import SourceProductData, SpecItem, SpecSection, TaxonomyResolution
from product_factory.parser_product_estia import (
    EstiaProductParser,
    normalize_estia_product_name,
)
from product_factory.services.authoring_service import (
    AuthoringStatus,
    IntroTextTaskStatus,
    SeoMetaTaskStatus,
)
from product_factory.services.models import (
    RunArtifacts,
    RunMetadata,
    RunStatus,
    RunType,
    ServiceResult,
)


def test_estia_name_normalization_handles_straw_tumbler_variants() -> None:
    assert normalize_estia_product_name(
        "ΘΕΡΜΟΣ STRAW TUMBLER XL StA 900ml NOIR ECHO ESTIA"
    ) == "Estia Noir Echo - Θερμός Straw Tumbler XL StA 900ml"
    assert normalize_estia_product_name(
        "ΘΕΡΜΟΣ STRAW TUMBLER XL StA 900ml SOFT RIPPLE ESTIA"
    ) == "Estia Soft Ripple - Θερμός Straw Tumbler XL StA 900ml"
    assert normalize_estia_product_name(
        "ΘΕΡΜΟΣ STRAW TUMBLER XL StA 1200ml FOREST SPIRIT ESTIA"
    ) == "Estia Forest Spirit - Θερμός Straw Tumbler XL StA 1200ml"
    assert normalize_estia_product_name(
        "ΘΕΡΜΟΣ STRAW TUMBLER XL StA SAVE THE AEGEAN 900ml NOIR ECHO"
    ) == "Estia Noir Echo - Θερμός Straw Tumbler XL StA 900ml"


def test_estia_parser_extracts_main_product_area_only() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://estiahomeart.com/01-32098">
      </head>
      <body>
        <div class="product-essential">
          <div class="gallery">
            <a class="picture-link" data-full-image-url="/images/thumbs/main-full.jpeg" href="/images/thumbs/main-thumb_625.jpeg">
              <img class="cloudzoom" src="/images/thumbs/main-thumb_625.jpeg" alt="main">
            </a>
          </div>
          <div class="overview">
            <div class="product-name"><h1>ΘΕΡΜΟΣ STRAW TUMBLER XL StA 900ml NOIR ECHO ESTIA</h1></div>
            <div class="manufacturers">Brand: <a>Estia</a></div>
            <div class="sku">Κωδικός προϊόντος: 01-32098</div>
          </div>
        </div>
        <div class="productTabs">
          <div id="quickTab-description">
            <div class="full-description"><p>Τα StrawTumbler XL είναι ιδανικά για καθημερινή χρήση.</p></div>
          </div>
          <div id="quickTab-specifications">
            <div class="product-specs-box">
              <table>
                <tr><td class="spec-name">Brand</td><td class="spec-value">Estia</td></tr>
                <tr><td class="spec-name">Χρώμα</td><td class="spec-value">Noir Echo</td></tr>
              </table>
            </div>
          </div>
          <div id="quickTab-elem">
            <div class="product-specs-box">
              <table>
                <tr><td class="spec-name">Μήκος τεμαχίου (cm)</td><td>14,5</td></tr>
                <tr><td class="spec-name">Capacity τεμαχίου (lt)</td><td>0,9</td></tr>
              </table>
            </div>
          </div>
        </div>
        <div class="related-products-grid product-grid">
          <img class="picture-img" src="/images/thumbs/related_440.jpeg" alt="related">
        </div>
        <footer><img src="/images/thumbs/logo.png" alt="logo"></footer>
      </body>
    </html>
    """

    parsed = EstiaProductParser().parse(html, "https://estiahomeart.com/01-32098")

    assert parsed.source.source_name == "estia"
    assert parsed.source.product_code == "01-32098"
    assert parsed.source.mpn == "01-32098"
    assert (
        parsed.source.name
        == "Estia Noir Echo - Θερμός Straw Tumbler XL StA 900ml"
    )
    assert parsed.source.breadcrumbs == [
        "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        "Καφές-Ροφήματα-Χυμοί",
        "Αξεσουάρ-Αναλώσιμα-Θερμός",
    ]
    assert [image.url for image in parsed.source.gallery_images] == [
        "https://estiahomeart.com/images/thumbs/main-full.jpeg"
    ]
    assert parsed.source.spec_sections[0].section == "Χαρακτηριστικά"
    assert parsed.source.spec_sections[1].section == "Ογκομετρικά Στοιχεία"
    assert {
        item.label: item.value for item in parsed.source.spec_sections[0].items
    }["Χρώμα"] == "Noir Echo"
    assert {
        item.label: item.value for item in parsed.source.spec_sections[1].items
    }["Capacity τεμαχίου (lt)"] == "0,9"
    assert parsed.source.presentation_source_html == ""
    assert parsed.field_diagnostics["presentation_blocks"].selected_strategy == (
        "not_applicable:estia_no_presentation_sections"
    )
    assert not any("related" in image.url for image in parsed.source.gallery_images)
    assert parsed.critical_missing == []


def test_estia_characteristics_render_raw_source_spec_sections() -> None:
    source = SourceProductData(
        source_name="estia",
        brand="Estia",
        mpn="01-32098",
        name="Estia Noir Echo - Θερμός Straw Tumbler XL StA 900ml",
        spec_sections=[
            SpecSection(
                "Χαρακτηριστικά",
                [
                    SpecItem("Χρώμα", "Noir Echo"),
                    SpecItem("Υλικό", "Ανοξείδωτο ατσάλι 18/8"),
                ],
            ),
            SpecSection(
                "Ογκομετρικά Στοιχεία",
                [SpecItem("Capacity τεμαχίου (lt)", "0,9")],
            ),
        ],
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Καφές-Ροφήματα-Χυμοί",
        sub_category="Αξεσουάρ-Αναλώσιμα-Θερμός",
    )

    html, diagnostics, warnings = build_characteristics_for_product(source, taxonomy)

    assert diagnostics["mode"] == "raw_spec_sections"
    assert warnings == []
    assert "Χαρακτηριστικά" in html
    assert "Ογκομετρικά Στοιχεία" in html
    assert "Capacity τεμαχίου (lt)" in html
    assert "Με βαλβίδα ασφαλείας" not in html


def test_estia_deterministic_fields_preserve_normalized_source_name() -> None:
    source = SourceProductData(
        source_name="estia",
        brand="Estia",
        mpn="01-32098",
        product_code="01-32098",
        name="Estia Noir Echo - Θερμός Straw Tumbler XL StA 900ml",
    )
    taxonomy = TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        leaf_category="Καφές-Ροφήματα-Χυμοί",
        sub_category="Αξεσουάρ-Αναλώσιμα-Θερμός",
    )

    fields = build_deterministic_product_fields(
        source, taxonomy, "343089", lambda name, model: f"slug-{model}"
    )

    assert fields["name"] == "Estia Noir Echo - Θερμός Straw Tumbler XL StA 900ml"
    assert fields["mpn"] == "01-32098"
    assert fields["meta_title"] == (
        "Estia Noir Echo - Θερμός Straw Tumbler XL StA 900ml | eTranoulis"
    )
    assert fields["seo_keyword"] == "slug-343089"


def test_estia_xlsx_import_enqueues_full_pipeline_jobs(tmp_path: Path) -> None:
    workbook = tmp_path / "thermos-estia.xlsx"
    _write_xlsx(
        workbook,
        [
            ["model", "name", "mpn", "brand", "price", "Boxnow"],
            [
                "343089",
                "ΘΕΡΜΟΣ STRAW TUMBLER XL StA 900ml NOIR ECHO ESTIA",
                "01-32098",
                "Estia",
                "16.60",
                "1",
            ],
            ["343090", "Missing mpn", "", "Estia", "15.00", "0"],
        ],
    )
    store = JobStore(tmp_path / "jobs")

    sheet_name, rows = read_estia_xlsx_rows(workbook)
    summary = enqueue_estia_xlsx_batch(workbook, job_store=store)
    jobs = store.list_jobs()

    assert sheet_name == "Φύλλο1"
    assert rows[0]["model"] == "343089"
    assert build_estia_source_url("01-32098") == "https://estiahomeart.com/01-32098"
    assert summary.total_rows == 2
    assert summary.valid_rows == 1
    assert summary.skipped_rows == 1
    assert summary.queued_rows == 1
    assert "row 3: skipped:missing_mpn" in summary.warnings
    assert len(jobs) == 1
    assert jobs[0].job_type == JobType.FULL_PIPELINE
    assert jobs[0].payload["source_url"] == "https://estiahomeart.com/01-32098"
    assert jobs[0].payload["product_name"] == (
        "ΘΕΡΜΟΣ STRAW TUMBLER XL StA 900ml NOIR ECHO ESTIA"
    )
    assert jobs[0].payload["price"] == "16.60"
    assert jobs[0].payload["bestprice_status"] == 1
    assert jobs[0].payload["skroutz_status"] == 0
    assert jobs[0].payload["boxnow"] == 1
    assert jobs[0].payload["sections"] == 0
    assert jobs[0].payload["skip_publish"] is True
    assert jobs[0].payload["source_resolution"]["mpn"] == "01-32098"


def test_full_pipeline_skip_publish_preserves_price_and_stops_after_render(
    tmp_path: Path,
) -> None:
    calls: list[object] = []
    model = "343089"
    product_file = tmp_path / "products" / f"{model}.csv"
    record = JobRecord(
        job_id="job-1",
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.RUNNING,
        model=model,
        payload={
            "model": model,
            "source_url": "https://estiahomeart.com/01-32098",
            "bestprice_status": 1,
            "skroutz_status": 0,
            "boxnow": 1,
            "price": "16.60",
            "gallery_mode": "all",
            "skip_publish": True,
        },
    )

    def prepare_fn(request):
        calls.append(request)
        scrape_dir = tmp_path / "work" / model / "scrape"
        llm_dir = tmp_path / "work" / model / "llm"
        scrape_dir.mkdir(parents=True, exist_ok=True)
        llm_dir.mkdir(parents=True, exist_ok=True)
        for path in [
            scrape_dir / f"{model}.source.json",
            scrape_dir / f"{model}.normalized.json",
            scrape_dir / f"{model}.report.json",
            llm_dir / "task_manifest.json",
            llm_dir / "intro_text.context.json",
            llm_dir / "seo_meta.context.json",
        ]:
            path.write_text("{}\n", encoding="utf-8")
        (llm_dir / "intro_text.prompt.txt").write_text("intro\n", encoding="utf-8")
        (llm_dir / "seo_meta.prompt.txt").write_text("seo\n", encoding="utf-8")
        return _service_result(
            request.model,
            RunType.PREPARE,
            artifacts=RunArtifacts(
                scrape_dir=scrape_dir,
                llm_dir=llm_dir,
                source_json_path=scrape_dir / f"{model}.source.json",
                scrape_normalized_json_path=scrape_dir / f"{model}.normalized.json",
                source_report_json_path=scrape_dir / f"{model}.report.json",
                llm_task_manifest_path=llm_dir / "task_manifest.json",
                intro_text_context_path=llm_dir / "intro_text.context.json",
                intro_text_prompt_path=llm_dir / "intro_text.prompt.txt",
                seo_meta_context_path=llm_dir / "seo_meta.context.json",
                seo_meta_prompt_path=llm_dir / "seo_meta.prompt.txt",
            ),
        )

    result = run_full_pipeline_job(
        record,
        lambda _line: None,
        prepare_product_fn=prepare_fn,
        run_intro_text_authoring_fn=lambda *_args, **_kwargs: _authoring_status(tmp_path, model),
        run_seo_meta_authoring_fn=lambda *_args, **_kwargs: _authoring_status(tmp_path, model),
        render_product_fn=lambda request: (
            calls.append(request)
            or _service_result(
                request.model,
                RunType.RENDER,
                artifacts=RunArtifacts(published_csv_path=product_file),
            )
        ),
        publish_product_fn=lambda request: calls.append(request),
    )

    assert result.status == JobStatus.SUCCEEDED
    assert result.message == "Full pipeline job succeeded without publish."
    assert len(calls) == 2
    assert calls[0].price == "16.60"
    assert calls[0].boxnow == 1
    assert calls[0].url == "https://estiahomeart.com/01-32098"
    assert result.artifacts["published_csv_path"] == str(product_file)


def _service_result(
    model: str,
    run_type: RunType,
    *,
    status: RunStatus = RunStatus.COMPLETED,
    artifacts: RunArtifacts | None = None,
) -> ServiceResult:
    return ServiceResult(
        run=RunMetadata(model=model, run_type=run_type, status=status),
        artifacts=artifacts or RunArtifacts(),
    )


def _authoring_status(root: Path, model: str) -> AuthoringStatus:
    llm_dir = root / "work" / model / "llm"
    return AuthoringStatus(
        model=model,
        llm_dir=str(llm_dir),
        intro_text=IntroTextTaskStatus(
            status="valid",
            output_path=str(llm_dir / "intro_text.output.txt"),
            trace_path=None,
            word_count=90,
            min_words=60,
            max_words=180,
            max_attempts=3,
        ),
        seo_meta=SeoMetaTaskStatus(
            status="valid",
            output_path=str(llm_dir / "seo_meta.output.json"),
        ),
        ready_for_render=True,
    )


def _write_xlsx(path: Path, rows: list[list[str]]) -> None:
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row):
            ref = f"{chr(ord('A') + col_index)}{row_index}"
            cells.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Φύλλο1" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
