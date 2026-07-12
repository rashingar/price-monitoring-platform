import argparse
import json
from pathlib import Path

import pytest
from PIL import Image

from product_factory.models import (
    CLIInput,
    GalleryImage,
    ParsedProduct,
    SchemaMatchResult,
    SourceProductData,
    SpecItem,
    SpecSection,
    TaxonomyResolution,
)
from product_factory.services.execution_models import (
    PrepareExecutionResult,
    RenderExecutionResult,
    RenderExecutionValidationReport,
)
from product_factory.services import (
    PrepareRequest,
    PublishRequest,
    RenderRequest,
    RunArtifacts,
    RunMetadata,
    RunStatus,
    RunType,
    ServiceError,
    ServiceErrorCode,
    ServiceResult,
)
from product_factory.workflow import (
    build_cli_input_from_args,
    build_parser,
    prepare_workflow,
    render_workflow,
    resolve_model_for_render,
)


def build_intro(words: int = 100) -> str:
    return " ".join(["λέξη"] * words)


def write_split_llm_outputs(
    model_root: Path,
    *,
    intro_text: str,
    meta_description: str,
    meta_keywords: list[str],
) -> None:
    llm_dir = model_root / "llm"
    llm_dir.mkdir(parents=True, exist_ok=True)
    (llm_dir / "intro_text.output.txt").write_text(intro_text, encoding="utf-8")
    (llm_dir / "seo_meta.output.json").write_text(
        json.dumps(
            {
                "product": {
                    "meta_description": meta_description,
                    "meta_keywords": meta_keywords,
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def write_publish_csv_and_jpeg(
    repo_root: Path, model: str, product_file: Path, *, filename: str | None = None
) -> None:
    filename = filename or f"{model}-1.jpg"
    gallery = repo_root / "work" / model / "scrape" / "gallery"
    gallery.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1, 1), "white").save(gallery / filename, format="JPEG")
    product_file.parent.mkdir(parents=True, exist_ok=True)
    product_file.write_text(
        "model,image,additional_image\n"
        f"{model},catalog/01_main/{model}/{filename},\n",
        encoding="utf-8",
    )


def test_build_cli_input_from_template_file(tmp_path: Path, monkeypatch) -> None:
    template = tmp_path / "input.txt"
    template.write_text(
        "model: 233541\nurl: https://www.electronet.gr/oikiakes-syskeyes/example\nphotos: 6\nsections: 5\nskroutz_status: 1\nboxnow: 0\nprice: 2099\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        template_file=str(template),
        stdin=False,
        model=None,
        url=None,
        photos=None,
        sections=None,
        skroutz_status=None,
        boxnow=None,
        price=None,
    )
    cli = build_cli_input_from_args(args)

    assert cli.model == "233541"
    assert cli.photos == 6
    assert cli.sections == 5
    assert str(cli.price) == "2099"


def test_build_parser_pins_supported_workflow_cli_surface() -> None:
    parser = build_parser()
    subparsers_action = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )

    assert parser.prog == "python -m product_factory.workflow"
    assert set(subparsers_action.choices) == {"prepare", "render"}

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["run"])

    assert excinfo.value.code == 2


def test_resolve_model_for_render_accepts_explicit_model_argument() -> None:
    args = argparse.Namespace(model="233541", template_file=None, stdin=False)

    assert resolve_model_for_render(args) == "233541"


def test_resolve_model_for_render_reads_model_from_template_file(
    tmp_path: Path,
) -> None:
    template = tmp_path / "render-input.txt"
    template.write_text("model: 233541\n", encoding="utf-8")
    args = argparse.Namespace(model=None, template_file=str(template), stdin=False)

    assert resolve_model_for_render(args) == "233541"


@pytest.mark.parametrize("model", [None, "", "23354", "233541a", "abc123", "2335417"])
def test_resolve_model_for_render_rejects_missing_or_invalid_model(
    model: str | None,
) -> None:
    from product_factory import workflow

    args = argparse.Namespace(model=model, template_file=None, stdin=False)

    with pytest.raises(ValueError) as excinfo:
        resolve_model_for_render(args)

    assert str(excinfo.value) == workflow.FAIL_MESSAGE


def test_prepare_workflow_delegates_to_service_execution(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory import workflow

    cli = CLIInput(
        model="233541",
        url="https://www.electronet.gr/example",
        photos=6,
        sections=2,
        skroutz_status=1,
        boxnow=0,
        price="2099",
        out=str(tmp_path),
    )
    expected_result = PrepareExecutionResult.from_mapping(
        {
            "model_root": tmp_path / "work" / "233541",
            "scrape_dir": tmp_path / "work" / "233541" / "scrape",
            "llm_dir": tmp_path / "work" / "233541" / "llm",
            "task_manifest_path": tmp_path
            / "work"
            / "233541"
            / "llm"
            / "task_manifest.json",
            "intro_text_context_path": tmp_path
            / "work"
            / "233541"
            / "llm"
            / "intro_text.context.json",
            "intro_text_prompt_path": tmp_path
            / "work"
            / "233541"
            / "llm"
            / "intro_text.prompt.txt",
            "intro_text_output_path": tmp_path
            / "work"
            / "233541"
            / "llm"
            / "intro_text.output.txt",
            "seo_meta_context_path": tmp_path
            / "work"
            / "233541"
            / "llm"
            / "seo_meta.context.json",
            "seo_meta_prompt_path": tmp_path
            / "work"
            / "233541"
            / "llm"
            / "seo_meta.prompt.txt",
            "seo_meta_output_path": tmp_path
            / "work"
            / "233541"
            / "llm"
            / "seo_meta.output.json",
            "run_status": "completed",
            "metadata_path": tmp_path / "work" / "233541" / "prepare.run.json",
            "scrape_result": {"report": {"warnings": []}},
        }
    )

    def fake_execute_prepare_stage(_cli, *, model_dir):
        assert model_dir == tmp_path / "work" / "233541" / "scrape"
        return {"unused": True}

    def fake_execute_prepare_workflow(cli_arg, *, work_root, execute_prepare_stage_fn):
        assert cli_arg is cli
        assert work_root == tmp_path / "work"
        assert execute_prepare_stage_fn is fake_execute_prepare_stage
        return expected_result

    monkeypatch.setattr(workflow, "WORK_ROOT", tmp_path / "work")
    monkeypatch.setattr(workflow, "execute_prepare_stage", fake_execute_prepare_stage)
    monkeypatch.setattr(
        workflow, "execute_prepare_workflow", fake_execute_prepare_workflow
    )

    assert workflow.prepare_workflow(cli) == expected_result


def test_prepare_workflow_writes_prompt_artifacts(tmp_path: Path, monkeypatch) -> None:
    from product_factory import workflow

    monkeypatch.setattr(workflow, "WORK_ROOT", tmp_path / "work")

    source = SourceProductData(
        url="https://www.electronet.gr/example",
        canonical_url="https://www.electronet.gr/example",
        product_code="233541",
        brand="LG",
        name="Ψυγείο Ντουλάπα LG GSGV80PYLL Ασημί E",
        hero_summary="Σύντομη περιγραφή",
        key_specs=[SpecItem(label="Συνολική Καθαρή Χωρητικότητα", value="635")],
    )
    cli = CLIInput(
        model="233541",
        url="https://www.electronet.gr/example",
        photos=6,
        sections=2,
        skroutz_status=1,
        boxnow=0,
        price="2099",
        out=str(tmp_path),
    )

    def fake_execute_prepare_stage(_cli, *, model_dir):
        assert model_dir == tmp_path / "work" / "233541" / "scrape"
        return {
            "normalized": {
                "deterministic_product": {
                    "brand": "LG",
                    "mpn": "GSGV80PYLL",
                    "manufacturer": "LG",
                    "name": "LG GSGV80PYLL – Ψυγείο Ντουλάπα 635Lt",
                    "meta_title": "LG GSGV80PYLL Ψυγείο Ντουλάπα 635Lt | eTranoulis",
                    "seo_keyword": "lg-gsgv80pyll-psygeio-ntoulapa-635lt",
                }
            },
            "parsed": ParsedProduct(source=source),
            "taxonomy": TaxonomyResolution(
                parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
                leaf_category="Ψυγεία & Καταψύκτες",
                sub_category="Ψυγεία Ντουλάπες",
                cta_url="https://www.etranoulis.gr/psygeia-ntoulapes",
            ),
            "schema_match": SchemaMatchResult(matched_schema_id="schema-1", score=0.9),
        }

    monkeypatch.setattr(workflow, "execute_prepare_stage", fake_execute_prepare_stage)

    result = prepare_workflow(cli)

    assert result.llm_dir.exists()
    assert result.task_manifest_path.exists()
    assert result.intro_text_context_path.exists()
    assert result.intro_text_prompt_path.exists()
    assert result.seo_meta_context_path.exists()
    assert result.seo_meta_prompt_path.exists()
    assert result.metadata_path.exists()
    task_manifest = json.loads(result.task_manifest_path.read_text(encoding="utf-8"))
    intro_text_context = json.loads(
        result.intro_text_context_path.read_text(encoding="utf-8")
    )
    seo_meta_context = json.loads(
        result.seo_meta_context_path.read_text(encoding="utf-8")
    )
    intro_text_prompt = result.intro_text_prompt_path.read_text(encoding="utf-8")
    seo_meta_prompt = result.seo_meta_prompt_path.read_text(encoding="utf-8")
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert task_manifest["prepare_mode"] == "split_tasks"
    assert task_manifest["primary_outputs"]["tasks"]["intro_text"][
        "context_path"
    ] == str(result.intro_text_context_path)
    assert task_manifest["primary_outputs"]["tasks"]["seo_meta"]["prompt_path"] == str(
        result.seo_meta_prompt_path
    )
    assert intro_text_context["task"] == "intro_text"
    assert intro_text_context["writer_rules"]["plain_text_only"] is False
    assert intro_text_context["writer_rules"]["allowed_inline_html_tags"] == ["strong"]
    assert intro_text_context["writer_rules"]["llm_owned_fields"] == ["intro_text"]
    assert "presentation_source_sections" not in intro_text_context
    assert "`<strong>` and `</strong>`" in intro_text_prompt
    assert "cta_language" in intro_text_context["writer_rules"]["forbidden_outputs"]
    assert "product.prose_subject" in intro_text_prompt
    assert seo_meta_context["task"] == "seo_meta"
    assert seo_meta_context["writer_rules"]["required_keywords"] == ["LG", "GSGV80PYLL"]
    assert (
        seo_meta_context["product"]["meta_title"]
        == "LG GSGV80PYLL Ψυγείο Ντουλάπα 635Lt | eTranoulis"
    )
    assert (
        "Include verified brand and preferred identifier keywords when available."
        in seo_meta_prompt
    )
    assert result.metadata_path.name == "prepare.run.json"
    assert metadata["run"]["model"] == "233541"
    assert metadata["run"]["run_type"] == "prepare"
    assert metadata["run"]["status"] == "completed"
    assert metadata["artifacts"]["llm_dir"] == str(result.llm_dir)
    assert metadata["artifacts"]["llm_task_manifest_path"] == str(
        result.task_manifest_path
    )
    assert metadata["artifacts"]["intro_text_context_path"] == str(
        result.intro_text_context_path
    )
    assert metadata["artifacts"]["seo_meta_context_path"] == str(
        result.seo_meta_context_path
    )
    assert metadata["artifacts"]["metadata_path"] == str(result.metadata_path)
    assert metadata["details"]["llm_prepare_mode"] == "split_tasks"
    assert metadata["details"]["source"] == ""


def test_render_workflow_delegates_to_service_execution(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory import workflow

    expected_result = RenderExecutionResult(
        candidate_dir=tmp_path / "work" / "233541" / "candidate",
        candidate_csv_path=tmp_path / "work" / "233541" / "candidate" / "233541.csv",
        published_csv_path=tmp_path / "products" / "233541.csv",
        description_path=tmp_path
        / "work"
        / "233541"
        / "candidate"
        / "description.html",
        characteristics_path=tmp_path
        / "work"
        / "233541"
        / "candidate"
        / "characteristics.html",
        validation_report_path=tmp_path
        / "work"
        / "233541"
        / "candidate"
        / "233541.validation.json",
        run_status=RunStatus.COMPLETED,
        metadata_path=tmp_path / "work" / "233541" / "render.run.json",
        validation_report=RenderExecutionValidationReport(ok=True, warnings=[]),
    )

    def fake_execute_render_workflow(model, *, work_root, products_root):
        assert model == "233541"
        assert work_root == tmp_path / "work"
        assert products_root == tmp_path / "products"
        return expected_result

    monkeypatch.setattr(workflow, "WORK_ROOT", tmp_path / "work")
    monkeypatch.setattr(workflow, "PRODUCTS_ROOT", tmp_path / "products")
    monkeypatch.setattr(
        workflow, "execute_render_workflow", fake_execute_render_workflow
    )

    assert workflow.render_workflow("233541") == expected_result


def test_prepare_workflow_keeps_prepare_scrape_only_without_candidate_csv(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory import workflow

    monkeypatch.setattr(workflow, "WORK_ROOT", tmp_path / "work")

    model = "233541"
    scrape_dir = tmp_path / "work" / model / "scrape"
    raw_html_path = scrape_dir / f"{model}.raw.html"
    source_json_path = scrape_dir / f"{model}.source.json"
    normalized_json_path = scrape_dir / f"{model}.normalized.json"
    report_json_path = scrape_dir / f"{model}.report.json"

    normalized_payload = {
        "deterministic_product": {
            "brand": "LG",
            "mpn": "GSGV80PYLL",
            "manufacturer": "LG",
            "name": "LG GSGV80PYLL – Ψυγείο Ντουλάπα",
            "meta_title": "LG GSGV80PYLL Ψυγείο Ντουλάπα | eTranoulis",
            "seo_keyword": "lg-gsgv80pyll-psygeio-ntoulapa",
        },
        "input": {"out": str(tmp_path / "work" / model / "scrape")},
    }
    report_payload = {
        "warnings": [],
        "files_written": [
            str(raw_html_path),
            str(source_json_path),
            str(normalized_json_path),
            str(report_json_path),
        ],
    }

    parsed = ParsedProduct(
        source=SourceProductData(
            url="https://www.electronet.gr/example",
            canonical_url="https://www.electronet.gr/example",
            product_code=model,
            brand="LG",
            name="Ψυγείο Ντουλάπα LG GSGV80PYLL",
            raw_html_path=str(raw_html_path),
            gallery_images=[
                GalleryImage(
                    url="https://example.com/1.jpg",
                    local_path=str(scrape_dir / "gallery" / f"{model}-1.jpg"),
                )
            ],
            besco_images=[
                GalleryImage(
                    url="https://example.com/besco1.jpg",
                    local_path=str(scrape_dir / "bescos" / "besco1.jpg"),
                )
            ],
        )
    )
    cli = CLIInput(
        model=model,
        url="https://www.electronet.gr/example",
        photos=6,
        sections=2,
        skroutz_status=1,
        boxnow=0,
        price="2099",
        out=str(tmp_path),
    )

    def fake_execute_prepare_stage(_cli, *, model_dir):
        assert model_dir == scrape_dir
        model_dir.mkdir(parents=True, exist_ok=True)
        raw_html_path.write_text("<html></html>", encoding="utf-8")
        source_json_path.write_text(
            json.dumps(
                {
                    "url": "https://www.electronet.gr/example",
                    "canonical_url": "https://www.electronet.gr/example",
                    "product_code": model,
                    "brand": "LG",
                    "name": "Ψυγείο Ντουλάπα LG GSGV80PYLL",
                    "raw_html_path": str(raw_html_path),
                    "gallery_images": [
                        {"local_path": str(scrape_dir / "gallery" / f"{model}-1.jpg")}
                    ],
                    "besco_images": [
                        {"local_path": str(scrape_dir / "bescos" / "besco1.jpg")}
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        normalized_json_path.write_text(
            json.dumps(normalized_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report_json_path.write_text(
            json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {
            "normalized": normalized_payload,
            "parsed": parsed,
            "taxonomy": TaxonomyResolution(
                parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
                leaf_category="Ψυγεία & Καταψύκτες",
                sub_category="Ψυγεία Ντουλάπες",
                cta_url="https://www.etranoulis.gr/psygeia-ntoulapes",
            ),
            "schema_match": SchemaMatchResult(matched_schema_id="schema-1", score=0.9),
            "report": report_payload,
            "model_dir": scrape_dir,
            "raw_html_path": raw_html_path,
            "source_json_path": source_json_path,
            "normalized_json_path": normalized_json_path,
            "report_json_path": report_json_path,
        }

    monkeypatch.setattr(workflow, "execute_prepare_stage", fake_execute_prepare_stage)

    result = prepare_workflow(cli)
    assert result.scrape_result.payload["model_dir"] == scrape_dir
    assert (scrape_dir / f"{model}.source.json").exists()
    assert (scrape_dir / f"{model}.normalized.json").exists()
    assert (scrape_dir / f"{model}.report.json").exists()
    assert not (scrape_dir / f"{model}.csv").exists()
    assert not (tmp_path / "work" / model / "candidate" / f"{model}.csv").exists()


def test_prepare_workflow_writes_failed_metadata_on_error(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory import workflow

    monkeypatch.setattr(workflow, "WORK_ROOT", tmp_path / "work")
    cli = CLIInput(
        model="233541",
        url="https://www.electronet.gr/example",
        photos=1,
        sections=0,
        skroutz_status=0,
        boxnow=0,
        price="0",
        out=str(tmp_path),
    )

    def fake_execute_prepare_stage(_cli, *, model_dir):
        assert model_dir == tmp_path / "work" / "233541" / "scrape"
        raise RuntimeError("prepare exploded")

    monkeypatch.setattr(workflow, "execute_prepare_stage", fake_execute_prepare_stage)

    try:
        prepare_workflow(cli)
    except RuntimeError as exc:
        assert str(exc) == "prepare exploded"
    else:
        raise AssertionError("Expected RuntimeError")

    metadata_path = tmp_path / "work" / "233541" / "prepare.run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["run"]["status"] == "failed"
    assert metadata["run"]["error_code"] == ServiceErrorCode.UNEXPECTED_FAILURE.value
    assert metadata["run"]["error_detail"] == "prepare exploded"


def test_execute_render_workflow_retries_short_intro_before_candidate_build(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory.services import render_execution
    from product_factory.services.settings_service import get_intro_text_policy

    model = "233541"
    scrape_dir = tmp_path / "work" / model / "scrape"
    llm_dir = tmp_path / "work" / model / "llm"
    products_dir = tmp_path / "products"
    scrape_dir.mkdir(parents=True)
    llm_dir.mkdir(parents=True)
    products_dir.mkdir(parents=True)

    source = SourceProductData(
        url="https://www.electronet.gr/example",
        canonical_url="https://www.electronet.gr/example",
        product_code=model,
        brand="LG",
        name="Ψυγείο Ντουλάπα LG GSGV80PYLL Ασημί E",
        hero_summary="Το LG GSGV80PYLL προσφέρει μεγάλη χωρητικότητα.",
        price_text="2.099,00 €",
        price_value=2099.0,
        gallery_images=[
            GalleryImage(
                url="https://example.com/233541-1.jpg",
                position=1,
                local_filename="233541-1.jpg",
                downloaded=True,
            )
        ],
        besco_images=[
            GalleryImage(
                url="https://example.com/besco1.jpg",
                position=1,
                local_filename="besco1.jpg",
                downloaded=True,
            )
        ],
        key_specs=[
            SpecItem(label="Συνολική Καθαρή Χωρητικότητα", value="635"),
            SpecItem(label="Τεχνολογία Ψύξης", value="Total No Frost"),
            SpecItem(label="Συνδεσιμότητα", value="WiFi"),
            SpecItem(label="Ενεργειακή Κλάση", value="(E)"),
            SpecItem(label="Πλάτος cm", value="91cm"),
            SpecItem(label="Ύψος cm", value="179 cm"),
            SpecItem(label="Χρώμα", value="Inox"),
            SpecItem(label="Ψύξη", value="Total No Frost"),
        ],
        presentation_source_html="""
        <section>
          <h3>NatureFRESH για καθημερινή φρεσκάδα</h3>
          <p>Το NatureFRESH βοηθά στη σωστή συντήρηση και υποστηρίζει σταθερή ψύξη σε όλη τη διάρκεια της ημέρας
          με καθαρή οργάνωση, πρακτική χρήση και άνετη πρόσβαση στα τρόφιμα για όλη την οικογένεια.</p>
        </section>
        """,
        spec_sections=[
            SpecSection(
                section="Επισκόπηση Προϊόντος",
                items=[SpecItem(label="Τύπος Ψυγείου", value="Ντουλάπα")],
            ),
        ],
    )
    source_json = scrape_dir / f"{model}.source.json"
    source_json.write_text(
        __import__("json").dumps(source.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    normalized_payload = {
        "input": {
            "model": model,
            "url": "https://www.electronet.gr/example",
            "photos": 1,
            "sections": 1,
            "skroutz_status": 1,
            "boxnow": 0,
            "price": "2099",
            "out": str(scrape_dir),
        },
        "taxonomy": TaxonomyResolution(
            parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            leaf_category="Ψυγεία & Καταψύκτες",
            sub_category="Ψυγεία Ντουλάπες",
            cta_url="https://www.etranoulis.gr/oikiakes-syskeues/psygeia-katapsyktes/psygeia-ntoulapes",
        ).to_dict(),
        "schema_match": SchemaMatchResult(
            matched_schema_id="schema-1", score=0.9
        ).to_dict(),
    }
    (scrape_dir / f"{model}.normalized.json").write_text(
        __import__("json").dumps(normalized_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    intro_policy = get_intro_text_policy(source=source.source_name)
    too_short_words = intro_policy.min_words - 1
    valid_words = intro_policy.min_words

    events: list[str] = []
    original_build_row = render_execution.build_row

    def tracking_build_row(*args, **kwargs):
        events.append("build_row")
        return original_build_row(*args, **kwargs)

    def resolve_seo_meta(**_kwargs):
        events.append("seo_meta")
        return {
            "product": {
                "meta_description": "Το LG GSGV80PYLL είναι ψυγείο ντουλάπα 635 λίτρων με Total No Frost και WiFi για άνεση κάθε μέρα.",
                "meta_keywords": [
                    "LG",
                    "GSGV80PYLL",
                    "Ψυγείο Ντουλάπα",
                    "Total No Frost",
                ],
            }
        }

    def resolve_intro_text(**kwargs):
        events.append(f"intro:{kwargs['attempt']}")
        return build_intro(too_short_words if kwargs["attempt"] == 1 else valid_words)

    monkeypatch.setattr(render_execution, "build_row", tracking_build_row)

    result = render_execution.execute_render_workflow(
        model,
        work_root=tmp_path / "work",
        products_root=products_dir,
        resolve_intro_text_fn=resolve_intro_text,
        resolve_seo_meta_fn=resolve_seo_meta,
    )

    assert events == ["seo_meta", "intro:1", "intro:2", "build_row"]
    assert result.run_status == RunStatus.COMPLETED
    assert result.published_csv_path == products_dir / f"{model}.csv"
    assert result.validation_report.ok is True
    assert (llm_dir / "seo_meta.output.json").exists()
    assert (llm_dir / "intro_text.output.txt").read_text(
        encoding="utf-8"
    ) == build_intro(valid_words)


def test_render_rehydrates_characteristics_source_from_prepare_normalized() -> None:
    from product_factory.services.render_execution import (
        _load_characteristics_source_from_normalized,
    )

    main_source = SourceProductData(
        source_name="electronet",
        name="A/C Inventor Neo Plus NPVI-24WFI/NPVO24 24000Btu",
        spec_sections=[],
    )
    characteristics_source = SourceProductData(
        source_name="bestprice",
        name="Inventor Neo Plus",
        spec_sections=[
            SpecSection(
                section="Χαρακτηριστικά",
                items=[SpecItem(label="Ονομαστική Απόδοση", value="24000 BTU")],
            )
        ],
    )

    loaded = _load_characteristics_source_from_normalized(
        {"characteristics_source": characteristics_source.to_dict()},
        fallback=main_source,
    )

    assert loaded.source_name == "bestprice"
    assert loaded.spec_sections[0].items[0].value == "24000 BTU"


def test_execute_render_workflow_stops_before_candidate_build_when_intro_retries_exhaust(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory.services import render_execution
    from product_factory.services.settings_service import get_intro_text_policy

    model = "233541"
    scrape_dir = tmp_path / "work" / model / "scrape"
    llm_dir = tmp_path / "work" / model / "llm"
    scrape_dir.mkdir(parents=True)
    llm_dir.mkdir(parents=True)

    source = SourceProductData(
        url="https://www.electronet.gr/example",
        canonical_url="https://www.electronet.gr/example",
        product_code=model,
        brand="LG",
        name="LG Example",
        gallery_images=[
            GalleryImage(
                url="https://example.com/233541-1.jpg",
                position=1,
                local_filename="233541-1.jpg",
                downloaded=True,
            )
        ],
        spec_sections=[
            SpecSection(
                section="Επισκόπηση Προϊόντος",
                items=[SpecItem(label="Τύπος Ψυγείου", value="Ντουλάπα")],
            )
        ],
        presentation_source_html="""
        <section>
          <h3>NatureFRESH</h3>
          <p>Κείμενο αρκετά μεγάλο ώστε η ενότητα να παραμένει χρήσιμη στη deterministic απόδοση περιγραφής προϊόντος.</p>
        </section>
        """,
    )
    (scrape_dir / f"{model}.source.json").write_text(
        json.dumps(source.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (scrape_dir / f"{model}.normalized.json").write_text(
        json.dumps(
            {
                "input": {
                    "model": model,
                    "url": source.url,
                    "photos": 1,
                    "sections": 1,
                    "skroutz_status": 1,
                    "boxnow": 0,
                    "price": "2099",
                },
                "taxonomy": TaxonomyResolution(
                    cta_url="https://example.com", leaf_category="Ψυγεία & Καταψύκτες"
                ).to_dict(),
                "schema_match": SchemaMatchResult(
                    matched_schema_id="schema-1", score=0.9
                ).to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    intro_policy = get_intro_text_policy(source=source.source_name)
    too_short_words = intro_policy.min_words - 1

    events: list[str] = []

    def fail_if_build_row_called(*_args, **_kwargs):
        events.append("build_row")
        raise AssertionError(
            "build_row should not run before intro validation succeeds"
        )

    def resolve_seo_meta(**_kwargs):
        events.append("seo_meta")
        return {
            "product": {
                "meta_description": "Έγκυρη περιγραφή.",
                "meta_keywords": ["LG", "Example"],
            }
        }

    def resolve_intro_text(**kwargs):
        events.append(f"intro:{kwargs['attempt']}")
        return build_intro(too_short_words)

    monkeypatch.setattr(render_execution, "build_row", fail_if_build_row_called)

    with pytest.raises(ServiceError) as excinfo:
        render_execution.execute_render_workflow(
            model,
            work_root=tmp_path / "work",
            products_root=tmp_path / "products",
            resolve_intro_text_fn=resolve_intro_text,
            resolve_seo_meta_fn=resolve_seo_meta,
        )

    assert events == ["seo_meta", "intro:1", "intro:2", "intro:3"]
    assert excinfo.value.code == ServiceErrorCode.VALIDATION_FAILURE.value
    assert excinfo.value.details["stage"] == "intro_text"
    assert excinfo.value.details["error_code"] == "llm_intro_text_word_count_invalid"
    assert excinfo.value.details["attempt_count"] == 3
    assert excinfo.value.details["trace_path"] == str(
        llm_dir / "intro_text.retry_trace.json"
    )
    assert (llm_dir / "seo_meta.output.json").exists()
    assert (llm_dir / "intro_text.output.txt").exists()
    trace = json.loads(
        (llm_dir / "intro_text.retry_trace.json").read_text(encoding="utf-8")
    )
    assert [item["status"] for item in trace] == ["retry", "retry", "failed"]
    assert not (tmp_path / "work" / model / "candidate" / f"{model}.csv").exists()
    assert not (tmp_path / "products" / f"{model}.csv").exists()
    metadata = json.loads(
        (tmp_path / "work" / model / "render.run.json").read_text(encoding="utf-8")
    )
    assert metadata["run"]["status"] == "failed"
    assert metadata["run"]["error_code"] == ServiceErrorCode.VALIDATION_FAILURE.value
    assert "stage=intro_text" in metadata["run"]["error_detail"]
    assert (
        "error_code=llm_intro_text_word_count_invalid"
        in metadata["run"]["error_detail"]
    )
    assert metadata["details"]["stage"] == "intro_text"
    assert metadata["details"]["error_code"] == "llm_intro_text_word_count_invalid"
    assert metadata["details"]["attempt_count"] == 3
    assert metadata["details"]["trace_path"] == str(
        llm_dir / "intro_text.retry_trace.json"
    )


def test_render_workflow_writes_failed_metadata_when_llm_output_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory import workflow
    import product_factory.services.llm_stage_execution as llm_stage_execution

    monkeypatch.setattr(workflow, "WORK_ROOT", tmp_path / "work")

    def fail_missing_openai_key():
        raise ServiceError(
            ServiceErrorCode.UNEXPECTED_FAILURE.value,
            "Missing OPENAI_API_KEY. Set it in the environment or repo-root .env.",
        )

    monkeypatch.setattr(
        llm_stage_execution, "load_openai_llm_config", fail_missing_openai_key
    )

    model = "233541"
    scrape_dir = tmp_path / "work" / model / "scrape"
    llm_dir = tmp_path / "work" / model / "llm"
    scrape_dir.mkdir(parents=True)
    llm_dir.mkdir(parents=True)
    (llm_dir / "seo_meta.prompt.txt").write_text("seo prompt", encoding="utf-8")
    source = SourceProductData(
        url="https://www.electronet.gr/example",
        canonical_url="https://www.electronet.gr/example",
        product_code=model,
        brand="LG",
        name="LG Example",
    )
    (scrape_dir / f"{model}.source.json").write_text(
        json.dumps(source.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (scrape_dir / f"{model}.normalized.json").write_text(
        json.dumps(
            {
                "input": {
                    "model": model,
                    "url": "https://www.electronet.gr/example",
                    "photos": 1,
                    "sections": 0,
                    "skroutz_status": 0,
                    "boxnow": 0,
                    "price": "0",
                },
                "taxonomy": {},
                "schema_match": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    try:
        render_workflow(model)
    except ServiceError as exc:
        assert exc.code == ServiceErrorCode.UNEXPECTED_FAILURE.value
        assert "Missing OPENAI_API_KEY" in exc.message
    else:
        raise AssertionError("Expected ServiceError")

    metadata_path = tmp_path / "work" / model / "render.run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["run"]["status"] == "failed"
    assert metadata["run"]["error_code"] == ServiceErrorCode.UNEXPECTED_FAILURE.value
    assert "Missing OPENAI_API_KEY" in metadata["run"]["error_detail"]


def test_render_workflow_builds_description_from_split_outputs_and_deterministic_sections(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory import workflow

    monkeypatch.setattr(workflow, "WORK_ROOT", tmp_path / "work")
    monkeypatch.setattr(workflow, "PRODUCTS_ROOT", tmp_path / "products")

    model = "233541"
    scrape_dir = tmp_path / "work" / model / "scrape"
    scrape_dir.mkdir(parents=True)

    source = SourceProductData(
        url="https://www.electronet.gr/example",
        canonical_url="https://www.electronet.gr/example",
        product_code=model,
        brand="LG",
        mpn="GSGV80PYLL",
        name="Ψυγείο Ντουλάπα LG GSGV80PYLL Ασημί E",
        hero_summary="Το LG GSGV80PYLL προσφέρει μεγάλη χωρητικότητα.",
        price_text="2.099,00 €",
        price_value=2099.0,
        gallery_images=[
            GalleryImage(
                url="https://example.com/233541-1.jpg",
                position=1,
                local_filename="233541-1.jpg",
                downloaded=True,
            )
        ],
        besco_images=[
            GalleryImage(
                url="https://example.com/besco1.jpg",
                position=1,
                local_filename="besco1.jpg",
                downloaded=True,
            ),
            GalleryImage(
                url="https://example.com/besco2.jpg",
                position=2,
                local_filename="besco2.jpg",
                downloaded=True,
            ),
        ],
        key_specs=[
            SpecItem(label="Συνολική Καθαρή Χωρητικότητα", value="635"),
            SpecItem(label="Τεχνολογία Ψύξης", value="Total No Frost"),
            SpecItem(label="Συνδεσιμότητα", value="WiFi"),
            SpecItem(label="Ενεργειακή Κλάση", value="(E)"),
            SpecItem(label="Πλάτος cm", value="91cm"),
            SpecItem(label="Ύψος cm", value="179 cm"),
            SpecItem(label="Χρώμα", value="Inox"),
            SpecItem(label="Ψύξη", value="Total No Frost"),
        ],
        spec_sections=[
            SpecSection(
                section="Βασικά Χαρακτηριστικά",
                items=[SpecItem(label="Τύπος Ψυγείου", value="Ντουλάπα")],
            )
        ],
        presentation_source_html="""
        <section>
          <h3>NatureFRESH για καθημερινή φρεσκάδα</h3>
          <p>Το NatureFRESH βοηθά στη σωστή συντήρηση και διατηρεί σταθερή ψύξη σε όλο τον θάλαμο,
          προσφέροντας πρακτική οργάνωση και εύκολη καθημερινή πρόσβαση στα τρόφιμα με σταθερή απόδοση και άνεση.</p>
        </section>
        <section>
          <h3>DoorCooling+ για ομοιόμορφη ψύξη</h3>
          <p>Η λειτουργία DoorCooling+ ενισχύει την ομοιόμορφη κατανομή του αέρα και υποστηρίζει σταθερή ψύξη,
          ώστε τα τρόφιμα να παραμένουν οργανωμένα και προσβάσιμα με καθαρή και πρακτική καθημερινή χρήση.</p>
        </section>
        """,
    )
    (scrape_dir / f"{model}.source.json").write_text(
        json.dumps(source.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (scrape_dir / f"{model}.normalized.json").write_text(
        json.dumps(
            {
                "input": {
                    "model": model,
                    "url": "https://www.electronet.gr/example",
                    "photos": 1,
                    "sections": 2,
                    "skroutz_status": 1,
                    "boxnow": 0,
                    "price": "2099",
                },
                "taxonomy": TaxonomyResolution(
                    parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
                    leaf_category="Ψυγεία & Καταψύκτες",
                    sub_category="Ψυγεία Ντουλάπες",
                    cta_url="https://www.etranoulis.gr/oikiakes-syskeues/psygeia-katapsyktes/psygeia-ntoulapes",
                ).to_dict(),
                "schema_match": SchemaMatchResult(
                    matched_schema_id="schema-1", score=0.9
                ).to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_split_llm_outputs(
        tmp_path / "work" / model,
        intro_text=build_intro(),
        meta_description="Το LG GSGV80PYLL είναι ψυγείο ντουλάπα 635 λίτρων με Total No Frost και WiFi για άνεση κάθε μέρα.",
        meta_keywords=["Ψυγεία Ντουλάπες", "Ψυγείο Ντουλάπα", "Total No Frost"],
    )

    result = render_workflow(model)
    description = result.description_path.read_text(encoding="utf-8")
    candidate_row = next(
        __import__("csv").DictReader(
            result.candidate_csv_path.open("r", encoding="utf-8-sig", newline="")
        )
    )

    assert result.run_status == RunStatus.COMPLETED
    assert result.published_csv_path == tmp_path / "products" / f"{model}.csv"
    assert "NatureFRESH για καθημερινή φρεσκάδα" in description
    assert "DoorCooling+ για ομοιόμορφη ψύξη" in description
    assert "λέξη λέξη λέξη" in description
    assert candidate_row["meta_keyword"].startswith("LG, GSGV80PYLL")
    assert candidate_row["meta_keyword"].count("Ψυγ") == 1

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["details"]["validation_ok"] is True
    assert metadata["details"]["published"] is True
    assert metadata["details"]["intro_text_trace_path"] == str(
        tmp_path / "work" / model / "llm" / "intro_text.retry_trace.json"
    )
    assert "upload_attempted" not in metadata["details"]


def test_execute_render_workflow_rerun_with_existing_valid_seo_keeps_downstream_work_single_per_run(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory.services import render_execution

    model = "233541"
    scrape_dir = tmp_path / "work" / model / "scrape"
    llm_dir = tmp_path / "work" / model / "llm"
    products_dir = tmp_path / "products"
    scrape_dir.mkdir(parents=True)
    llm_dir.mkdir(parents=True)
    products_dir.mkdir(parents=True)

    source = SourceProductData(
        url="https://www.electronet.gr/example",
        canonical_url="https://www.electronet.gr/example",
        product_code=model,
        brand="LG",
        mpn="GSGV80PYLL",
        name="Ψυγείο Ντουλάπα LG GSGV80PYLL Ασημί E",
        hero_summary="Το LG GSGV80PYLL προσφέρει μεγάλη χωρητικότητα.",
        price_text="2.099,00 €",
        price_value=2099.0,
        gallery_images=[
            GalleryImage(
                url="https://example.com/233541-1.jpg",
                position=1,
                local_filename="233541-1.jpg",
                downloaded=True,
            )
        ],
        besco_images=[
            GalleryImage(
                url="https://example.com/besco1.jpg",
                position=1,
                local_filename="besco1.jpg",
                downloaded=True,
            )
        ],
        key_specs=[
            SpecItem(label="Συνολική Καθαρή Χωρητικότητα", value="635"),
            SpecItem(label="Τεχνολογία Ψύξης", value="Total No Frost"),
            SpecItem(label="Συνδεσιμότητα", value="WiFi"),
            SpecItem(label="Ενεργειακή Κλάση", value="(E)"),
            SpecItem(label="Πλάτος cm", value="91cm"),
            SpecItem(label="Ύψος cm", value="179 cm"),
            SpecItem(label="Χρώμα", value="Inox"),
            SpecItem(label="Ψύξη", value="Total No Frost"),
        ],
        spec_sections=[
            SpecSection(
                section="Βασικά Χαρακτηριστικά",
                items=[SpecItem(label="Τύπος Ψυγείου", value="Ντουλάπα")],
            )
        ],
        presentation_source_html="""
        <section>
          <h3>NatureFRESH για καθημερινή φρεσκάδα</h3>
          <p>Το NatureFRESH βοηθά στη σωστή συντήρηση και διατηρεί σταθερή ψύξη σε όλο τον θάλαμο, προσφέροντας πρακτική οργάνωση, καθαρή πρόσβαση στα τρόφιμα και σταθερή καθημερινή χρήση με ευκολία για όλη την οικογένεια.</p>
        </section>
        """,
    )
    (scrape_dir / f"{model}.source.json").write_text(
        json.dumps(source.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (scrape_dir / f"{model}.normalized.json").write_text(
        json.dumps(
            {
                "input": {
                    "model": model,
                    "url": source.url,
                    "photos": 1,
                    "sections": 1,
                    "skroutz_status": 1,
                    "boxnow": 0,
                    "price": "2099",
                },
                "taxonomy": TaxonomyResolution(
                    parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
                    leaf_category="Ψυγεία & Καταψύκτες",
                    sub_category="Ψυγεία Ντουλάπες",
                    cta_url="https://www.etranoulis.gr/oikiakes-syskeues/psygeia-katapsyktes/psygeia-ntoulapes",
                ).to_dict(),
                "schema_match": SchemaMatchResult(
                    matched_schema_id="schema-1", score=0.9
                ).to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    seo_text = json.dumps(
        {
            "product": {
                "meta_description": "Υπάρχουσα έγκυρη περιγραφή.",
                "meta_keywords": ["LG", "GSGV80PYLL", "Ψυγείο Ντουλάπα"],
            }
        },
        ensure_ascii=False,
        indent=2,
    )
    (llm_dir / "seo_meta.output.json").write_text(seo_text, encoding="utf-8")

    build_calls: list[str] = []
    intro_calls: list[int] = []
    original_build_row = render_execution.build_row

    def tracking_build_row(*args, **kwargs):
        build_calls.append("build_row")
        return original_build_row(*args, **kwargs)

    def resolve_intro_text(**kwargs):
        intro_calls.append(kwargs["attempt"])
        return build_intro(100)

    monkeypatch.setattr(render_execution, "build_row", tracking_build_row)

    first_result = render_execution.execute_render_workflow(
        model,
        work_root=tmp_path / "work",
        products_root=products_dir,
        resolve_intro_text_fn=resolve_intro_text,
    )
    second_result = render_execution.execute_render_workflow(
        model,
        work_root=tmp_path / "work",
        products_root=products_dir,
        resolve_intro_text_fn=resolve_intro_text,
    )

    assert first_result.run_status == RunStatus.COMPLETED
    assert second_result.run_status == RunStatus.COMPLETED
    assert intro_calls == [1, 1]
    assert build_calls == ["build_row", "build_row"]
    assert (llm_dir / "seo_meta.output.json").read_text(encoding="utf-8") == seo_text


def test_workflow_main_render_returns_publish_failure_exit_code(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    from product_factory import workflow

    def fake_resolve_model_for_render(_args) -> str:
        return "233541"

    def fake_render_product(request: RenderRequest) -> ServiceResult:
        assert request.model == "233541"
        return ServiceResult(
            run=RunMetadata(
                model="233541", run_type=RunType.RENDER, status=RunStatus.COMPLETED
            ),
            artifacts=RunArtifacts(
                candidate_csv_path=tmp_path
                / "work"
                / "233541"
                / "candidate"
                / "233541.csv",
                published_csv_path=tmp_path / "products" / "233541.csv",
                validation_report_path=tmp_path
                / "work"
                / "233541"
                / "candidate"
                / "233541.validation.json",
                metadata_path=tmp_path / "work" / "233541" / "render.run.json",
            ),
            details={"validation_ok": True, "published": True},
        )

    def fake_publish_product(request: PublishRequest) -> ServiceResult:
        assert request.model == "233541"
        assert request.current_job_product_file == tmp_path / "products" / "233541.csv"
        return ServiceResult(
            run=RunMetadata(
                model="233541",
                run_type=RunType.PUBLISH,
                status=RunStatus.FAILED,
                warnings=["OpenCart publish failed during image_upload: exit=12"],
                error_code=ServiceErrorCode.PUBLISH_FAILURE.value,
            ),
            artifacts=RunArtifacts(
                metadata_path=tmp_path / "work" / "233541" / "publish.run.json"
            ),
            details={
                "publish_attempted": True,
                "publish_status": "failed",
                "publish_stage": "image_upload",
                "publish_message": "OpenCart publish failed during image_upload: exit=12",
                "upload_report_path": str(
                    tmp_path / "work" / "233541" / "upload.opencart.json"
                ),
                "import_report_path": str(
                    tmp_path / "work" / "233541" / "import.opencart.json"
                ),
            },
        )

    monkeypatch.setattr(
        workflow, "resolve_model_for_render", fake_resolve_model_for_render
    )
    monkeypatch.setattr(workflow, "render_product", fake_render_product)
    monkeypatch.setattr(workflow, "publish_product", fake_publish_product)

    exit_code = workflow.main(["render"])
    captured = capsys.readouterr()

    assert exit_code == 7
    assert "Render status: success" in captured.out
    assert "Publish status: failed" in captured.out
    assert "Publish stage: image_upload" in captured.out
    assert (
        "Publish message: OpenCart publish failed during image_upload: exit=12"
        in captured.out
    )
    assert (
        f"OpenCart upload report: {tmp_path / 'work' / '233541' / 'upload.opencart.json'}"
        in captured.out
    )
    assert (
        f"OpenCart import report: {tmp_path / 'work' / '233541' / 'import.opencart.json'}"
        in captured.out
    )
    assert (
        f"Publish metadata path: {tmp_path / 'work' / '233541' / 'publish.run.json'}"
        in captured.out
    )
    return

    monkeypatch.setattr(workflow, "WORK_ROOT", tmp_path / "work")
    monkeypatch.setattr(workflow, "PRODUCTS_ROOT", tmp_path / "products")

    model = "233541"
    scrape_dir = tmp_path / "work" / model / "scrape"
    scrape_dir.mkdir(parents=True)

    source = SourceProductData(
        url="https://www.electronet.gr/example",
        canonical_url="https://www.electronet.gr/example",
        product_code=model,
        brand="LG",
        mpn="GSGV80PYLL",
        name="LG Example Product",
        hero_summary="Example summary for validation coverage.",
        price_text="999,00 €",
        price_value=999.0,
        gallery_images=[
            GalleryImage(
                url="https://example.com/233541-1.jpg",
                position=1,
                local_filename="233541-1.jpg",
                downloaded=True,
            )
        ],
        key_specs=[SpecItem(label="Power", value="2200 W")],
        spec_sections=[
            SpecSection(
                section="Specs", items=[SpecItem(label="Type", value="Example")]
            )
        ],
        presentation_source_html="""
        <section>
          <h3>Example section</h3>
          <p>This section provides a clearly written product explanation with enough descriptive text about performance, daily use, practical convenience, and overall behavior to remain usable during deterministic rendering for the final product description output.</p>
        </section>
        """,
    )
    (scrape_dir / f"{model}.source.json").write_text(
        json.dumps(source.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (scrape_dir / f"{model}.normalized.json").write_text(
        json.dumps(
            {
                "input": {
                    "model": model,
                    "url": source.url,
                    "photos": 1,
                    "sections": 1,
                    "skroutz_status": 0,
                    "boxnow": 0,
                    "price": "0",
                },
                "taxonomy": TaxonomyResolution(
                    parent_category="Home",
                    leaf_category="Example",
                    sub_category="Examples",
                    cta_url="https://example.com",
                ).to_dict(),
                "schema_match": SchemaMatchResult(
                    matched_schema_id="schema-1", score=0.9
                ).to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_split_llm_outputs(
        tmp_path / "work" / model,
        intro_text=build_intro(),
        meta_description="Valid meta description for upload warning coverage.",
        meta_keywords=["LG", "GSGV80PYLL", "Example"],
    )
    monkeypatch.setattr(
        render_execution,
        "_run_opencart_image_upload",
        lambda **_kwargs: {
            "upload_attempted": True,
            "upload_ok": False,
            "upload_report_path": render_execution.REPO_ROOT
            / "work"
            / model
            / "upload.opencart.json",
            "upload_warning": "opencart_image_upload_failed: exit=1: upload failed",
        },
    )

    result = render_workflow(model)

    assert result.run_status == RunStatus.COMPLETED
    assert result.published_csv_path == tmp_path / "products" / f"{model}.csv"
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["run"]["status"] == "completed"
    assert (
        "opencart_image_upload_failed: exit=1: upload failed"
        in metadata["run"]["warnings"]
    )
    assert metadata["details"]["upload_attempted"] is True
    assert metadata["details"]["upload_ok"] is False
    assert (
        metadata["details"]["upload_warning"]
        == "opencart_image_upload_failed: exit=1: upload failed"
    )


def test_execute_publish_workflow_passes_model_and_current_job_product_file(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory.services import publish_execution

    repo_root = tmp_path
    model = "233541"
    script_path = repo_root / "tools" / "run_opencart_pipeline.sh"
    current_job_product_file = repo_root / "products" / "233541.csv"
    main_image_path = (
        repo_root / "work" / model / "scrape" / "gallery" / f"{model}-1.jpg"
    )
    (repo_root / "work" / model).mkdir(parents=True)
    script_path.parent.mkdir(parents=True)
    current_job_product_file.parent.mkdir(parents=True)
    main_image_path.parent.mkdir(parents=True)
    script_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    write_publish_csv_and_jpeg(repo_root, model, current_job_product_file)
    captured: dict[str, object] = {}
    calls: list[list[str]] = []

    class DummyCompleted:
        def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(cmd, *, cwd, capture_output, text, check, env=None):
        calls.append(cmd)
        captured["cwd"] = cwd
        captured["env"] = env
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["check"] = check
        if cmd[-1] == "--version":
            return DummyCompleted(0, "GNU bash, version 5.2.0\n", "")
        captured["cmd"] = cmd
        return DummyCompleted(0, "[opencart-publish] ok\n", "")

    monkeypatch.setattr(
        publish_execution.shutil,
        "which",
        lambda name: "/usr/bin/bash" if name == "bash" else None,
    )
    monkeypatch.setattr(publish_execution.subprocess, "run", fake_run)

    result = publish_execution.execute_publish_workflow(
        repo_root=repo_root,
        work_root=repo_root / "work",
        products_root=repo_root / "products",
        model=model,
        current_job_product_file=current_job_product_file,
    )

    assert calls == [
        ["/usr/bin/bash", "--version"],
        ["/usr/bin/bash", "tools/run_opencart_pipeline.sh", model],
    ]
    assert captured["cmd"] == ["/usr/bin/bash", "tools/run_opencart_pipeline.sh", model]
    assert captured["cwd"] == repo_root
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["check"] is False
    assert captured["env"]["CURRENT_JOB_PRODUCT_FILE"] == "products/233541.csv"
    assert "REPO_ROOT" not in captured["env"]
    assert result["publish_attempted"] is True
    assert result["publish_status"] == "warning"
    assert result["publish_stage"] == "csv_import"
    assert (
        result["upload_report_path"]
        == repo_root / "work" / model / "upload.opencart.json"
    )
    assert (
        result["import_report_path"]
        == repo_root / "work" / model / "import.opencart.json"
    )
    return

    repo_root = tmp_path
    script_path = repo_root / "tools" / "run_opencart_image_upload.sh"
    current_job_product_file = repo_root / "products" / "233541.csv"
    script_path.parent.mkdir(parents=True)
    current_job_product_file.parent.mkdir(parents=True)
    script_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    current_job_product_file.write_text("header\nvalue\n", encoding="utf-8")
    captured: dict[str, object] = {}

    class DummyCompleted:
        returncode = 0
        stdout = "[opencart-upload] ok\n"
        stderr = ""

    def fake_run(cmd, *, cwd, env, capture_output, text, check):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["env"] = env
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["check"] = check
        return DummyCompleted()

    monkeypatch.setattr(render_execution.subprocess, "run", fake_run)

    result = render_execution._run_opencart_image_upload(
        repo_root=repo_root,
        model="233541",
        current_job_product_file=current_job_product_file,
    )

    assert captured["cmd"] == ["bash", str(script_path)]
    assert captured["cwd"] == repo_root
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["check"] is False
    assert captured["env"]["CURRENT_JOB_PRODUCT_FILE"] == str(current_job_product_file)
    assert captured["env"]["REPO_ROOT"] == str(repo_root)
    assert result["upload_attempted"] is True
    assert result["upload_ok"] is True
    assert (
        result["upload_report_path"]
        == repo_root / "work" / "233541" / "upload.opencart.json"
    )
    assert result["upload_warning"] is None


def test_execute_publish_workflow_fails_preflight_when_bash_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory.services import publish_execution

    repo_root = tmp_path
    model = "233541"
    script_path = repo_root / "tools" / "run_opencart_pipeline.sh"
    current_job_product_file = repo_root / "products" / "233541.csv"
    main_image_path = (
        repo_root / "work" / model / "scrape" / "gallery" / f"{model}-1.jpg"
    )
    script_path.parent.mkdir(parents=True)
    current_job_product_file.parent.mkdir(parents=True)
    main_image_path.parent.mkdir(parents=True)
    script_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    write_publish_csv_and_jpeg(repo_root, model, current_job_product_file)

    monkeypatch.setattr(publish_execution.shutil, "which", lambda _name: None)

    result = publish_execution.execute_publish_workflow(
        repo_root=repo_root,
        work_root=repo_root / "work",
        products_root=repo_root / "products",
        model=model,
        current_job_product_file=current_job_product_file,
    )

    assert result["publish_status"] == "failed"
    assert result["publish_stage"] == "preflight"
    assert (
        result["publish_message"]
        == "OpenCart publish failed during preflight: bash executable not found on PATH"
    )


def test_execute_publish_workflow_classifies_wsl_launcher_probe_failures(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory.services import publish_execution

    repo_root = tmp_path
    model = "233541"
    script_path = repo_root / "tools" / "run_opencart_pipeline.sh"
    current_job_product_file = repo_root / "products" / "233541.csv"
    main_image_path = (
        repo_root / "work" / model / "scrape" / "gallery" / f"{model}-1.jpg"
    )
    script_path.parent.mkdir(parents=True)
    current_job_product_file.parent.mkdir(parents=True)
    main_image_path.parent.mkdir(parents=True)
    script_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    write_publish_csv_and_jpeg(repo_root, model, current_job_product_file)

    class DummyCompleted:
        returncode = 1
        stdout = "Error code: Wsl/Service/CreateInstance/0xd0000022\n"
        stderr = ""

    monkeypatch.setattr(
        publish_execution.shutil,
        "which",
        lambda name: "/usr/bin/bash" if name == "bash" else None,
    )
    monkeypatch.setattr(
        publish_execution.subprocess, "run", lambda *args, **kwargs: DummyCompleted()
    )

    result = publish_execution.execute_publish_workflow(
        repo_root=repo_root,
        work_root=repo_root / "work",
        products_root=repo_root / "products",
        model=model,
        current_job_product_file=current_job_product_file,
    )

    assert result["publish_status"] == "failed"
    assert result["publish_stage"] == "preflight"
    assert "bash_or_wsl_startup_failure" in str(result["publish_message"])
    assert "CreateInstance/0xd0000022" in str(result["publish_message"])


def test_execute_publish_workflow_fails_preflight_when_main_image_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory.services import publish_execution

    repo_root = tmp_path
    model = "233541"
    script_path = repo_root / "tools" / "run_opencart_pipeline.sh"
    current_job_product_file = repo_root / "products" / "233541.csv"
    script_path.parent.mkdir(parents=True)
    current_job_product_file.parent.mkdir(parents=True)
    (repo_root / "work" / model / "scrape").mkdir(parents=True)
    script_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    current_job_product_file.write_text(
        "model,image,additional_image\n"
        f"{model},catalog/01_main/{model}/{model}-1.jpg,\n",
        encoding="utf-8",
    )

    # The CSV-referenced image is missing and must be reported before shell invocation.
    monkeypatch.setattr(
        publish_execution.shutil,
        "which",
        lambda name: "/usr/bin/bash" if name == "bash" else None,
    )

    result = publish_execution.execute_publish_workflow(
        repo_root=repo_root,
        work_root=repo_root / "work",
        products_root=repo_root / "products",
        model=model,
        current_job_product_file=current_job_product_file,
    )

    assert result["publish_status"] == "failed"
    assert result["publish_stage"] == "preflight"
    assert "missing main gallery image" in str(result["publish_message"])


def test_render_workflow_warns_and_continues_when_source_sections_are_missing_entirely(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory import workflow

    monkeypatch.setattr(workflow, "WORK_ROOT", tmp_path / "work")
    monkeypatch.setattr(workflow, "PRODUCTS_ROOT", tmp_path / "products")
    model = "233541"
    scrape_dir = tmp_path / "work" / model / "scrape"
    scrape_dir.mkdir(parents=True)
    source = SourceProductData(
        url="https://www.electronet.gr/example",
        canonical_url="https://www.electronet.gr/example",
        product_code=model,
        brand="LG",
        mpn="GSGV80PYLL",
        name="LG Example",
        spec_sections=[
            SpecSection(
                section="Ξ’Ξ±ΟƒΞΉΞΊΞ¬ Ξ§Ξ±ΟΞ±ΞΊΟ„Ξ·ΟΞΉΟƒΟ„ΞΉΞΊΞ¬",
                items=[SpecItem(label="Ξ¤ΟΟ€ΞΏΟ‚ Ξ¨Ο…Ξ³ΞµΞ―ΞΏΟ…", value="ΞΟ„ΞΏΟ…Ξ»Ξ¬Ο€Ξ±")],
            )
        ],
    )
    (scrape_dir / f"{model}.source.json").write_text(
        json.dumps(source.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (scrape_dir / f"{model}.normalized.json").write_text(
        json.dumps(
            {
                "input": {
                    "model": model,
                    "url": source.url,
                    "photos": 1,
                    "sections": 1,
                    "skroutz_status": 0,
                    "boxnow": 0,
                    "price": "0",
                },
                "taxonomy": TaxonomyResolution(
                    cta_url="https://example.com", leaf_category="Ψυγεία & Καταψύκτες"
                ).to_dict(),
                "schema_match": SchemaMatchResult().to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_split_llm_outputs(
        tmp_path / "work" / model,
        intro_text=build_intro(),
        meta_description="Το LG GSGV80PYLL είναι ψυγείο ντουλάπα με άνετη καθημερινή χρήση.",
        meta_keywords=["LG", "GSGV80PYLL"],
    )

    result = render_workflow(model)

    assert "presentation_sections_missing:1" in result.validation_report.warnings
    assert "requested_sections_reduced:0" in result.validation_report.warnings
    assert result.metadata_path.exists()


def test_render_workflow_warns_and_continues_when_one_requested_section_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory import workflow

    monkeypatch.setattr(workflow, "WORK_ROOT", tmp_path / "work")
    monkeypatch.setattr(workflow, "PRODUCTS_ROOT", tmp_path / "products")
    model = "233541"
    scrape_dir = tmp_path / "work" / model / "scrape"
    scrape_dir.mkdir(parents=True)
    source = SourceProductData(
        url="https://www.electronet.gr/example",
        canonical_url="https://www.electronet.gr/example",
        product_code=model,
        brand="LG",
        mpn="GSGV80PYLL",
        name="LG Example",
        spec_sections=[
            SpecSection(
                section="Βασικά Χαρακτηριστικά",
                items=[SpecItem(label="Τύπος Ψυγείου", value="Ντουλάπα")],
            )
        ],
        presentation_source_html="""
        <section>
          <h3>Κανονική ενότητα</h3>
          <p>Η συγκεκριμένη ενότητα περιγράφει καθαρά τη λειτουργία της συσκευής με αρκετές λέξεις και
          σταθερό περιεχόμενο ώστε να θεωρείται χρήσιμη για τελική προβολή στη σελίδα προϊόντος.</p>
        </section>
        <section>
          <h3>Εικόνα μόνο</h3>
          <img src="https://example.com/image.jpg" />
        </section>
        """,
        besco_images=[
            GalleryImage(
                url="https://example.com/besco1.jpg",
                position=1,
                local_filename="besco1.jpg",
                downloaded=True,
            )
        ],
    )
    (scrape_dir / f"{model}.source.json").write_text(
        json.dumps(source.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (scrape_dir / f"{model}.normalized.json").write_text(
        json.dumps(
            {
                "input": {
                    "model": model,
                    "url": source.url,
                    "photos": 1,
                    "sections": 2,
                    "skroutz_status": 0,
                    "boxnow": 0,
                    "price": "0",
                },
                "taxonomy": TaxonomyResolution(
                    parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
                    cta_url="https://example.com",
                    leaf_category="Ψυγεία & Καταψύκτες",
                ).to_dict(),
                "schema_match": SchemaMatchResult().to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_split_llm_outputs(
        tmp_path / "work" / model,
        intro_text=build_intro(),
        meta_description="Το LG GSGV80PYLL είναι ψυγείο ντουλάπα με άνετη καθημερινή χρήση.",
        meta_keywords=["Ψυγείο Ντουλάπες", "Ψυγείο Ντουλάπα"],
    )

    result = render_workflow(model)
    description = result.description_path.read_text(encoding="utf-8")

    assert result.run_status == RunStatus.COMPLETED
    assert "Κανονική ενότητα" in description
    assert result.validation_report.ok is True
    assert "presentation_sections_missing:1" in result.validation_report.warnings
    assert "requested_sections_reduced:1" in result.validation_report.warnings


def test_render_workflow_warns_and_continues_when_multiple_requested_sections_are_missing(
    tmp_path: Path, monkeypatch
) -> None:
    from product_factory import workflow

    monkeypatch.setattr(workflow, "WORK_ROOT", tmp_path / "work")
    monkeypatch.setattr(workflow, "PRODUCTS_ROOT", tmp_path / "products")
    model = "331566"
    scrape_dir = tmp_path / "work" / model / "scrape"
    scrape_dir.mkdir(parents=True)
    source = SourceProductData(
        url="https://www.electronet.gr/example",
        canonical_url="https://www.electronet.gr/example",
        product_code=model,
        brand="Black&Decker",
        mpn="PV1820L-QW",
        name="Black&Decker Example",
        spec_sections=[
            SpecSection(
                section="Βασικά Χαρακτηριστικά",
                items=[SpecItem(label="Τάση Volt", value="18")],
            )
        ],
        presentation_source_html="""
        <section>
          <h3>Περιστρεφόμενο ρύγχος</h3>
          <p>Η ενότητα αυτή περιγράφει με σαφή, καθαρό και επαρκή τρόπο τη λειτουργία του σκουπακίου, την ευκολία πρόσβασης σε δύσκολα σημεία, την πρακτική καθημερινή χρήση και τη συνολικά αξιόπιστη εμπειρία που χρειάζεται η τελική προβολή στη σελίδα προϊόντος.</p>
        </section>
        """,
        besco_images=[
            GalleryImage(
                url="https://example.com/besco1.jpg",
                position=1,
                local_filename="besco1.jpg",
                downloaded=True,
            )
        ],
    )
    (scrape_dir / f"{model}.source.json").write_text(
        json.dumps(source.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (scrape_dir / f"{model}.normalized.json").write_text(
        json.dumps(
            {
                "input": {
                    "model": model,
                    "url": source.url,
                    "photos": 1,
                    "sections": 4,
                    "skroutz_status": 0,
                    "boxnow": 1,
                    "price": "99",
                },
                "taxonomy": TaxonomyResolution(
                    parent_category="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
                    leaf_category="Σκούπισμα",
                    sub_category="Σκουπάκια",
                    taxonomy_path="ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ > Σκούπισμα > Σκουπάκια",
                    cta_url="https://example.com/skoupakia",
                ).to_dict(),
                "schema_match": SchemaMatchResult().to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_split_llm_outputs(
        tmp_path / "work" / model,
        intro_text=build_intro(),
        meta_description="Το Black&Decker PV1820L-QW είναι σκουπάκι χειρός με επαναφορτιζόμενη λειτουργία.",
        meta_keywords=["Black&Decker", "PV1820L-QW"],
    )

    result = render_workflow(model)
    description = result.description_path.read_text(encoding="utf-8")

    assert result.run_status == RunStatus.COMPLETED
    assert "Περιστρεφόμενο ρύγχος" in description
    assert result.validation_report.ok is True
    assert "presentation_sections_missing:3" in result.validation_report.warnings
    assert "requested_sections_reduced:1" in result.validation_report.warnings


def test_workflow_main_prepare_routes_through_prepare_service(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    from product_factory import workflow

    cli = CLIInput(
        model="233541",
        url="https://www.electronet.gr/example",
        photos=2,
        sections=1,
        skroutz_status=1,
        boxnow=0,
        price="2099",
        out=str(tmp_path),
    )

    def fake_build_cli_input_from_args(_args):
        return cli

    def fake_prepare_product(request: PrepareRequest) -> ServiceResult:
        assert request.model == cli.model
        assert request.url == cli.url
        assert request.photos == cli.photos
        assert request.sections == cli.sections
        assert request.skroutz_status == cli.skroutz_status
        assert request.boxnow == cli.boxnow
        assert request.price == cli.price
        return ServiceResult(
            run=RunMetadata(
                model=cli.model, run_type=RunType.PREPARE, status=RunStatus.COMPLETED
            ),
            artifacts=RunArtifacts(
                scrape_dir=tmp_path / "work" / cli.model / "scrape",
                llm_task_manifest_path=tmp_path
                / "work"
                / cli.model
                / "llm"
                / "task_manifest.json",
                intro_text_context_path=tmp_path
                / "work"
                / cli.model
                / "llm"
                / "intro_text.context.json",
                intro_text_prompt_path=tmp_path
                / "work"
                / cli.model
                / "llm"
                / "intro_text.prompt.txt",
                seo_meta_context_path=tmp_path
                / "work"
                / cli.model
                / "llm"
                / "seo_meta.context.json",
                seo_meta_prompt_path=tmp_path
                / "work"
                / cli.model
                / "llm"
                / "seo_meta.prompt.txt",
                metadata_path=tmp_path / "work" / cli.model / "prepare.run.json",
            ),
        )

    monkeypatch.setattr(
        workflow, "build_cli_input_from_args", fake_build_cli_input_from_args
    )
    monkeypatch.setattr(workflow, "prepare_product", fake_prepare_product)

    exit_code = workflow.main(["prepare"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert (
        f"Scrape artifacts: {tmp_path / 'work' / cli.model / 'scrape'}" in captured.out
    )
    assert (
        f"LLM task manifest: {tmp_path / 'work' / cli.model / 'llm' / 'task_manifest.json'}"
        in captured.out
    )
    assert (
        f"Intro task context: {tmp_path / 'work' / cli.model / 'llm' / 'intro_text.context.json'}"
        in captured.out
    )
    assert (
        f"Intro task prompt: {tmp_path / 'work' / cli.model / 'llm' / 'intro_text.prompt.txt'}"
        in captured.out
    )
    assert (
        f"SEO task context: {tmp_path / 'work' / cli.model / 'llm' / 'seo_meta.context.json'}"
        in captured.out
    )
    assert (
        f"SEO task prompt: {tmp_path / 'work' / cli.model / 'llm' / 'seo_meta.prompt.txt'}"
        in captured.out
    )
    assert "Run status: completed" in captured.out
    assert (
        f"Metadata path: {tmp_path / 'work' / cli.model / 'prepare.run.json'}"
        in captured.out
    )


def test_workflow_main_render_routes_through_render_service(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    from product_factory import workflow

    def fake_resolve_model_for_render(_args) -> str:
        return "233541"

    def fake_render_product(request: RenderRequest) -> ServiceResult:
        assert request.model == "233541"
        return ServiceResult(
            run=RunMetadata(
                model="233541", run_type=RunType.RENDER, status=RunStatus.COMPLETED
            ),
            artifacts=RunArtifacts(
                candidate_csv_path=tmp_path
                / "work"
                / "233541"
                / "candidate"
                / "233541.csv",
                published_csv_path=tmp_path / "products" / "233541.csv",
                validation_report_path=tmp_path
                / "work"
                / "233541"
                / "candidate"
                / "233541.validation.json",
                metadata_path=tmp_path / "work" / "233541" / "render.run.json",
            ),
            details={"validation_ok": True, "published": True},
        )

    def fake_publish_product(request: PublishRequest) -> ServiceResult:
        assert request.model == "233541"
        assert request.current_job_product_file == tmp_path / "products" / "233541.csv"
        return ServiceResult(
            run=RunMetadata(
                model="233541", run_type=RunType.PUBLISH, status=RunStatus.COMPLETED
            ),
            artifacts=RunArtifacts(
                metadata_path=tmp_path / "work" / "233541" / "publish.run.json"
            ),
            details={
                "publish_attempted": True,
                "publish_status": "success",
                "publish_stage": "csv_import",
                "publish_message": "OpenCart publish completed successfully.",
                "upload_report_path": str(
                    tmp_path / "work" / "233541" / "upload.opencart.json"
                ),
                "import_report_path": str(
                    tmp_path / "work" / "233541" / "import.opencart.json"
                ),
            },
        )

    monkeypatch.setattr(
        workflow, "resolve_model_for_render", fake_resolve_model_for_render
    )
    monkeypatch.setattr(workflow, "render_product", fake_render_product)
    monkeypatch.setattr(workflow, "publish_product", fake_publish_product)

    exit_code = workflow.main(["render"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert (
        f"Candidate CSV: {tmp_path / 'work' / '233541' / 'candidate' / '233541.csv'}"
        in captured.out
    )
    assert f"Published CSV: {tmp_path / 'products' / '233541.csv'}" in captured.out
    assert (
        f"Validation report: {tmp_path / 'work' / '233541' / 'candidate' / '233541.validation.json'}"
        in captured.out
    )
    assert "Validation ok: True" in captured.out
    assert "Render status: success" in captured.out
    assert "Publish status: success" in captured.out
    assert "Publish stage: csv_import" in captured.out
    assert "Publish message: OpenCart publish completed successfully." in captured.out
    assert (
        f"OpenCart upload report: {tmp_path / 'work' / '233541' / 'upload.opencart.json'}"
        in captured.out
    )
    assert (
        f"OpenCart import report: {tmp_path / 'work' / '233541' / 'import.opencart.json'}"
        in captured.out
    )
    assert "Run status: completed" in captured.out
    assert (
        f"Metadata path: {tmp_path / 'work' / '233541' / 'render.run.json'}"
        in captured.out
    )
    assert (
        f"Publish metadata path: {tmp_path / 'work' / '233541' / 'publish.run.json'}"
        in captured.out
    )


@pytest.mark.parametrize(
    ("service_code", "expected_exit"),
    [
        (ServiceErrorCode.MISSING_ARTIFACT.value, 3),
        (ServiceErrorCode.PROVIDER_FAILURE.value, 4),
        (ServiceErrorCode.PARSE_FAILURE.value, 6),
        (ServiceErrorCode.PUBLISH_FAILURE.value, 7),
        (ServiceErrorCode.UNEXPECTED_FAILURE.value, 8),
    ],
)
def test_workflow_main_maps_service_error_codes_to_explicit_exit_codes(
    monkeypatch, capsys, service_code: str, expected_exit: int
) -> None:
    from product_factory import workflow

    def fake_build_cli_input_from_args(_args):
        return CLIInput(
            model="233541",
            url="https://www.electronet.gr/example",
            photos=2,
            sections=1,
            skroutz_status=1,
            boxnow=0,
            price="2099",
            out="out",
        )

    def fake_prepare_product(_request: PrepareRequest) -> ServiceResult:
        raise ServiceError(service_code, f"{service_code} message")

    monkeypatch.setattr(
        workflow, "build_cli_input_from_args", fake_build_cli_input_from_args
    )
    monkeypatch.setattr(workflow, "prepare_product", fake_prepare_product)

    exit_code = workflow.main(["prepare"])
    captured = capsys.readouterr()

    assert exit_code == expected_exit
    assert f"{service_code} message" in captured.err


def test_workflow_main_prepare_keeps_cli_shape_for_degraded_metadata_result(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    from product_factory import workflow

    def fake_build_cli_input_from_args(_args):
        return CLIInput(
            model="233541",
            url="https://www.electronet.gr/example",
            photos=2,
            sections=1,
            skroutz_status=1,
            boxnow=0,
            price="2099",
            out="out",
        )

    def fake_prepare_product(_request: PrepareRequest) -> ServiceResult:
        return ServiceResult(
            run=RunMetadata(
                model="233541",
                run_type=RunType.PREPARE,
                status=RunStatus.COMPLETED,
                warnings=[
                    f"Failed to write prepare run metadata at {tmp_path / 'work' / '233541' / 'prepare.run.json'}: disk full"
                ],
                error_code=ServiceErrorCode.UNEXPECTED_FAILURE.value,
                error_detail=f"Failed to write prepare run metadata at {tmp_path / 'work' / '233541' / 'prepare.run.json'}: disk full",
            ),
            artifacts=RunArtifacts(
                scrape_dir=tmp_path / "work" / "233541" / "scrape",
                llm_task_manifest_path=tmp_path
                / "work"
                / "233541"
                / "llm"
                / "task_manifest.json",
                intro_text_context_path=tmp_path
                / "work"
                / "233541"
                / "llm"
                / "intro_text.context.json",
                intro_text_prompt_path=tmp_path
                / "work"
                / "233541"
                / "llm"
                / "intro_text.prompt.txt",
                seo_meta_context_path=tmp_path
                / "work"
                / "233541"
                / "llm"
                / "seo_meta.context.json",
                seo_meta_prompt_path=tmp_path
                / "work"
                / "233541"
                / "llm"
                / "seo_meta.prompt.txt",
                metadata_path=None,
            ),
        )

    monkeypatch.setattr(
        workflow, "build_cli_input_from_args", fake_build_cli_input_from_args
    )
    monkeypatch.setattr(workflow, "prepare_product", fake_prepare_product)

    exit_code = workflow.main(["prepare"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert (
        f"Scrape artifacts: {tmp_path / 'work' / '233541' / 'scrape'}" in captured.out
    )
    assert "Run status: completed" in captured.out
    assert "Metadata path: None" in captured.out


def test_workflow_main_prepare_hard_failure_prints_service_error_only(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    from product_factory import workflow

    def fake_build_cli_input_from_args(_args):
        return CLIInput(
            model="233541",
            url="https://www.electronet.gr/example",
            photos=2,
            sections=1,
            skroutz_status=1,
            boxnow=0,
            price="2099",
            out="out",
        )

    def fake_prepare_product(_request: PrepareRequest) -> ServiceResult:
        raise ServiceError(
            ServiceErrorCode.MISSING_ARTIFACT.value,
            f"Prepare completed but required artifacts are missing: llm_task_manifest_path={tmp_path / 'work' / '233541' / 'llm' / 'task_manifest.json'}",
        )

    monkeypatch.setattr(
        workflow, "build_cli_input_from_args", fake_build_cli_input_from_args
    )
    monkeypatch.setattr(workflow, "prepare_product", fake_prepare_product)

    exit_code = workflow.main(["prepare"])
    captured = capsys.readouterr()

    assert exit_code == 3
    assert captured.out == ""
    assert (
        "Prepare completed but required artifacts are missing: llm_task_manifest_path="
        in captured.err
    )


def test_workflow_main_render_uses_validation_failure_exit_code(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    from product_factory import workflow

    def fake_resolve_model_for_render(_args) -> str:
        return "233541"

    def fake_render_product(request: RenderRequest) -> ServiceResult:
        assert request.model == "233541"
        return ServiceResult(
            run=RunMetadata(
                model="233541",
                run_type=RunType.RENDER,
                status=RunStatus.FAILED,
                error_code=ServiceErrorCode.VALIDATION_FAILURE.value,
                error_detail="Candidate validation failed",
            ),
            artifacts=RunArtifacts(
                candidate_csv_path=tmp_path
                / "work"
                / "233541"
                / "candidate"
                / "233541.csv",
                validation_report_path=tmp_path
                / "work"
                / "233541"
                / "candidate"
                / "233541.validation.json",
                metadata_path=tmp_path / "work" / "233541" / "render.run.json",
            ),
            details={"validation_ok": False},
        )

    monkeypatch.setattr(
        workflow, "resolve_model_for_render", fake_resolve_model_for_render
    )
    monkeypatch.setattr(workflow, "render_product", fake_render_product)

    exit_code = workflow.main(["render"])
    captured = capsys.readouterr()

    assert exit_code == 5
    assert "Validation ok: False" in captured.out


def test_workflow_main_render_keeps_cli_shape_for_degraded_metadata_result(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    from product_factory import workflow

    def fake_resolve_model_for_render(_args) -> str:
        return "233541"

    def fake_render_product(request: RenderRequest) -> ServiceResult:
        assert request.model == "233541"
        return ServiceResult(
            run=RunMetadata(
                model="233541",
                run_type=RunType.RENDER,
                status=RunStatus.COMPLETED,
                warnings=[
                    f"Render metadata artifact is missing: {tmp_path / 'work' / '233541' / 'render.run.json'}"
                ],
                error_code=ServiceErrorCode.MISSING_ARTIFACT.value,
                error_detail=f"Render metadata artifact is missing: {tmp_path / 'work' / '233541' / 'render.run.json'}",
            ),
            artifacts=RunArtifacts(
                candidate_csv_path=tmp_path
                / "work"
                / "233541"
                / "candidate"
                / "233541.csv",
                validation_report_path=tmp_path
                / "work"
                / "233541"
                / "candidate"
                / "233541.validation.json",
                metadata_path=None,
            ),
            details={"validation_ok": True, "published": False},
        )

    monkeypatch.setattr(
        workflow, "resolve_model_for_render", fake_resolve_model_for_render
    )
    monkeypatch.setattr(workflow, "render_product", fake_render_product)

    exit_code = workflow.main(["render"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert (
        f"Candidate CSV: {tmp_path / 'work' / '233541' / 'candidate' / '233541.csv'}"
        in captured.out
    )
    assert (
        f"Validation report: {tmp_path / 'work' / '233541' / 'candidate' / '233541.validation.json'}"
        in captured.out
    )
    assert "Validation ok: True" in captured.out
    assert "Render status: success" in captured.out
    assert "Publish status: not_attempted" in captured.out
    assert "Run status: completed" in captured.out
    assert "Metadata path: None" in captured.out


def test_workflow_main_render_validation_failure_still_prints_operator_paths(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    from product_factory import workflow

    def fake_resolve_model_for_render(_args) -> str:
        return "233541"

    def fake_render_product(request: RenderRequest) -> ServiceResult:
        assert request.model == "233541"
        return ServiceResult(
            run=RunMetadata(
                model="233541",
                run_type=RunType.RENDER,
                status=RunStatus.FAILED,
                warnings=[
                    "Candidate failed validation; skipping publish to products/."
                ],
                error_code=ServiceErrorCode.VALIDATION_FAILURE.value,
                error_detail="Candidate validation failed",
            ),
            artifacts=RunArtifacts(
                candidate_csv_path=tmp_path
                / "work"
                / "233541"
                / "candidate"
                / "233541.csv",
                validation_report_path=tmp_path
                / "work"
                / "233541"
                / "candidate"
                / "233541.validation.json",
                metadata_path=tmp_path / "work" / "233541" / "render.run.json",
            ),
            details={"validation_ok": False, "published": False},
        )

    monkeypatch.setattr(
        workflow, "resolve_model_for_render", fake_resolve_model_for_render
    )
    monkeypatch.setattr(workflow, "render_product", fake_render_product)

    exit_code = workflow.main(["render"])
    captured = capsys.readouterr()

    assert exit_code == 5
    assert (
        f"Candidate CSV: {tmp_path / 'work' / '233541' / 'candidate' / '233541.csv'}"
        in captured.out
    )
    assert (
        f"Validation report: {tmp_path / 'work' / '233541' / 'candidate' / '233541.validation.json'}"
        in captured.out
    )
    assert "Validation ok: False" in captured.out
    assert "Render status: failure" in captured.out
    assert "Publish status: not_attempted" in captured.out
    assert "Publish stage: -" in captured.out
    assert (
        "Publish message: Publish skipped because render did not publish products/233541.csv."
        in captured.out
    )
    assert "Run status: failed" in captured.out
    assert (
        f"Metadata path: {tmp_path / 'work' / '233541' / 'render.run.json'}"
        in captured.out
    )


def test_workflow_main_render_hard_failure_prints_service_error_only(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    from product_factory import workflow

    def fake_resolve_model_for_render(_args) -> str:
        return "233541"

    def fake_render_product(_request: RenderRequest) -> ServiceResult:
        raise ServiceError(
            ServiceErrorCode.MISSING_ARTIFACT.value,
            f"Render completed but required artifacts are missing: validation_report_path={tmp_path / 'work' / '233541' / 'candidate' / '233541.validation.json'}",
        )

    monkeypatch.setattr(
        workflow, "resolve_model_for_render", fake_resolve_model_for_render
    )
    monkeypatch.setattr(workflow, "render_product", fake_render_product)

    exit_code = workflow.main(["render"])
    captured = capsys.readouterr()

    assert exit_code == 3
    assert captured.out == ""
    assert (
        "Render completed but required artifacts are missing: validation_report_path="
        in captured.err
    )


def test_resolve_render_sections_backfills_with_weak_sections_before_reducing() -> None:
    from product_factory.services import render_execution

    sections, warnings = render_execution._resolve_render_sections(
        extracted_sections=[
            {
                "title": "Usable",
                "body_text": " ".join(f"λέξη{i}" for i in range(30)),
                "image_url": "https://example.com/1.jpg",
            },
            {
                "title": "Weak",
                "body_text": " ".join(f"όρος{i}" for i in range(12)),
                "image_url": "https://example.com/2.jpg",
            },
        ],
        sections_requested=2,
    )

    assert [section["title"] for section in sections] == ["Usable", "Weak"]
    assert "presentation_sections_weak:1" in warnings
    assert not any(
        warning.startswith("requested_sections_reduced:") for warning in warnings
    )


def test_resolve_render_sections_preserves_source_order_when_backfilling_weak_sections() -> (
    None
):
    from product_factory.services import render_execution

    sections, warnings = render_execution._resolve_render_sections(
        extracted_sections=[
            {
                "title": "Usable One",
                "body_text": " ".join(f"λέξη{i}" for i in range(30)),
                "image_url": "https://example.com/1.jpg",
            },
            {
                "title": "Weak Two",
                "body_text": " ".join(f"όρος{i}" for i in range(12)),
                "image_url": "https://example.com/2.jpg",
            },
            {
                "title": "Usable Three",
                "body_text": " ".join(f"κείμενο{i}" for i in range(30)),
                "image_url": "",
            },
        ],
        sections_requested=3,
    )

    assert [section["title"] for section in sections] == [
        "Usable One",
        "Weak Two",
        "Usable Three",
    ]
    assert [section["source_index"] for section in sections] == [1, 2, 3]
    assert "presentation_sections_weak:1" in warnings
