import json
from pathlib import Path

from pipeline.models import CLIInput, ParsedProduct, SchemaMatchResult, SourceProductData, TaxonomyResolution
from pipeline.services.execution_models import PreparedProductContext, PrepareExecutionResult, RenderExecutionResult
from pipeline.services.models import RunStatus


def test_prepared_product_context_derives_current_artifact_paths(tmp_path: Path) -> None:
    model_root = tmp_path / "work" / "233541"

    context = PreparedProductContext.from_model("233541", model_root=model_root)

    assert context.model_root == model_root
    assert context.scrape_dir == model_root / "scrape"
    assert context.llm_dir == model_root / "llm"
    assert context.source_json_path == model_root / "scrape" / "233541.source.json"
    assert context.scrape_normalized_json_path == model_root / "scrape" / "233541.normalized.json"
    assert context.source_report_json_path == model_root / "scrape" / "233541.report.json"
    assert context.task_manifest_path == model_root / "llm" / "task_manifest.json"
    assert context.intro_text_context_path == model_root / "llm" / "intro_text.context.json"
    assert context.intro_text_prompt_path == model_root / "llm" / "intro_text.prompt.txt"
    assert context.intro_text_output_path == model_root / "llm" / "intro_text.output.txt"
    assert context.seo_meta_context_path == model_root / "llm" / "seo_meta.context.json"
    assert context.seo_meta_prompt_path == model_root / "llm" / "seo_meta.prompt.txt"
    assert context.seo_meta_output_path == model_root / "llm" / "seo_meta.output.json"


def test_prepared_product_context_wraps_prepare_stage_payload(tmp_path: Path) -> None:
    model_root = tmp_path / "work" / "233541"
    scrape_dir = model_root / "scrape"
    llm_dir = model_root / "llm"
    cli = CLIInput(
        model="233541",
        url="https://www.electronet.gr/example",
        photos=6,
        sections=2,
        skroutz_status=1,
        boxnow=0,
        price="2099",
        out=str(scrape_dir),
    )
    parsed = ParsedProduct(
        source=SourceProductData(
            url="https://www.electronet.gr/example",
            canonical_url="https://www.electronet.gr/example",
            product_code="233541",
            brand="LG",
            name="LG Example",
        )
    )
    taxonomy = TaxonomyResolution(
        parent_category="A",
        leaf_category="B",
        sub_category="C",
        taxonomy_path="A > B > C",
    )
    schema_match = SchemaMatchResult(matched_schema_id="schema-1", score=0.9)
    stage_result = {
        "parsed": parsed,
        "taxonomy": taxonomy,
        "schema_match": schema_match,
        "normalized": {"deterministic_product": {"brand": "LG", "mpn": "GSGV80PYLL"}},
        "report": {"warnings": ["prepare warning"]},
        "source_json_path": scrape_dir / "233541.source.json",
        "normalized_json_path": scrape_dir / "233541.normalized.json",
        "report_json_path": scrape_dir / "233541.report.json",
    }

    context = PreparedProductContext.from_prepare_stage_result(
        cli=cli,
        model_root=model_root,
        scrape_dir=scrape_dir,
        llm_dir=llm_dir,
        stage_result=stage_result,
    )

    assert context.source_json_path == scrape_dir / "233541.source.json"
    assert context.scrape_normalized_json_path == scrape_dir / "233541.normalized.json"
    assert context.source_report_json_path == scrape_dir / "233541.report.json"
    assert context.parsed is parsed
    assert context.source_product is parsed.source
    assert context.taxonomy is taxonomy
    assert context.schema_match is schema_match
    assert context.deterministic_product == {"brand": "LG", "mpn": "GSGV80PYLL"}
    assert context.report_payload == {"warnings": ["prepare warning"]}
    assert context.payload == stage_result


def test_prepared_product_context_loads_render_payloads_from_current_artifacts(tmp_path: Path) -> None:
    model_root = tmp_path / "work" / "233541"
    context = PreparedProductContext.from_model("233541", model_root=model_root)
    context.scrape_dir.mkdir(parents=True)
    context.source_json_path.write_text(
        json.dumps(
            {
                "url": "https://www.electronet.gr/example",
                "canonical_url": "https://www.electronet.gr/example",
                "product_code": "233541",
                "brand": "LG",
                "name": "LG Example",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    context.scrape_normalized_json_path.write_text(
        json.dumps(
            {
                "input": {
                    "model": "233541",
                    "url": "https://www.electronet.gr/example",
                    "photos": 6,
                    "sections": 2,
                    "skroutz_status": 1,
                    "boxnow": 0,
                    "price": "2099",
                },
                "taxonomy": {
                    "parent_category": "A",
                    "leaf_category": "B",
                    "sub_category": "C",
                    "taxonomy_path": "A > B > C",
                },
                "schema_match": {
                    "matched_schema_id": "schema-1",
                    "score": 0.9,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def source_loader(path: Path) -> SourceProductData:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return SourceProductData(
            url=payload["url"],
            canonical_url=payload["canonical_url"],
            product_code=payload["product_code"],
            brand=payload["brand"],
            name=payload["name"],
        )

    def json_loader(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    loaded_context = context.load_for_render(
        source_loader=source_loader,
        json_loader=json_loader,
    )
    cli = loaded_context.build_render_cli(candidate_out=model_root / "candidate")

    assert loaded_context.source_product is not None
    assert loaded_context.source_product.product_code == "233541"
    assert loaded_context.require_parsed().source is loaded_context.source_product
    assert loaded_context.require_taxonomy().taxonomy_path == "A > B > C"
    assert loaded_context.require_schema_match().matched_schema_id == "schema-1"
    assert cli.model == "233541"
    assert cli.url == "https://www.electronet.gr/example"
    assert cli.photos == 6
    assert cli.sections == 2
    assert cli.skroutz_status == 1
    assert cli.boxnow == 0
    assert str(cli.price) == "2099"
    assert cli.out == str(model_root / "candidate")


def test_prepare_execution_result_from_mapping_matches_current_prepare_payload(tmp_path: Path) -> None:
    payload = {
        "model_root": tmp_path / "work" / "233541",
        "scrape_dir": tmp_path / "work" / "233541" / "scrape",
        "llm_dir": tmp_path / "work" / "233541" / "llm",
        "task_manifest_path": tmp_path / "work" / "233541" / "llm" / "task_manifest.json",
        "intro_text_context_path": tmp_path / "work" / "233541" / "llm" / "intro_text.context.json",
        "intro_text_prompt_path": tmp_path / "work" / "233541" / "llm" / "intro_text.prompt.txt",
        "intro_text_output_path": tmp_path / "work" / "233541" / "llm" / "intro_text.output.txt",
        "seo_meta_context_path": tmp_path / "work" / "233541" / "llm" / "seo_meta.context.json",
        "seo_meta_prompt_path": tmp_path / "work" / "233541" / "llm" / "seo_meta.prompt.txt",
        "seo_meta_output_path": tmp_path / "work" / "233541" / "llm" / "seo_meta.output.json",
        "run_status": "completed",
        "metadata_path": tmp_path / "work" / "233541" / "prepare.run.json",
        "scrape_result": {
            "source": "electronet",
            "parsed": ParsedProduct(
                source=SourceProductData(
                    url="https://www.electronet.gr/example",
                    canonical_url="https://www.electronet.gr/example",
                    product_code="233541",
                    brand="LG",
                    name="LG Example",
                )
            ),
            "taxonomy": TaxonomyResolution(
                parent_category="A",
                leaf_category="B",
                sub_category="C",
                taxonomy_path="A > B > C",
            ),
            "schema_match": SchemaMatchResult(matched_schema_id="schema-1", score=0.9),
            "report": {"warnings": ["prepare warning"]},
        },
    }

    result = PrepareExecutionResult.from_mapping(payload)

    assert result.model_root == tmp_path / "work" / "233541"
    assert result.scrape_dir == tmp_path / "work" / "233541" / "scrape"
    assert result.llm_dir == tmp_path / "work" / "233541" / "llm"
    assert result.task_manifest_path == tmp_path / "work" / "233541" / "llm" / "task_manifest.json"
    assert result.intro_text_context_path == tmp_path / "work" / "233541" / "llm" / "intro_text.context.json"
    assert result.intro_text_prompt_path == tmp_path / "work" / "233541" / "llm" / "intro_text.prompt.txt"
    assert result.intro_text_output_path == tmp_path / "work" / "233541" / "llm" / "intro_text.output.txt"
    assert result.seo_meta_context_path == tmp_path / "work" / "233541" / "llm" / "seo_meta.context.json"
    assert result.seo_meta_prompt_path == tmp_path / "work" / "233541" / "llm" / "seo_meta.prompt.txt"
    assert result.seo_meta_output_path == tmp_path / "work" / "233541" / "llm" / "seo_meta.output.json"
    assert result.run_status == RunStatus.COMPLETED
    assert result.metadata_path == tmp_path / "work" / "233541" / "prepare.run.json"
    assert result.scrape_result.source == "electronet"
    assert result.scrape_result.parsed is payload["scrape_result"]["parsed"]
    assert result.scrape_result.taxonomy is payload["scrape_result"]["taxonomy"]
    assert result.scrape_result.schema_match is payload["scrape_result"]["schema_match"]
    assert result.scrape_result.report_warnings == ["prepare warning"]
    assert result.payload == payload


def test_render_execution_result_from_mapping_matches_current_render_payload(tmp_path: Path) -> None:
    payload = {
        "candidate_dir": tmp_path / "work" / "233541" / "candidate",
        "candidate_csv_path": tmp_path / "work" / "233541" / "candidate" / "233541.csv",
        "published_csv_path": None,
        "description_path": tmp_path / "work" / "233541" / "candidate" / "description.html",
        "characteristics_path": tmp_path / "work" / "233541" / "candidate" / "characteristics.html",
        "validation_report_path": tmp_path / "work" / "233541" / "candidate" / "233541.validation.json",
        "run_status": "failed",
        "metadata_path": tmp_path / "work" / "233541" / "render.run.json",
        "validation_report": {
            "ok": False,
            "warnings": ["render warning"],
            "errors": ["llm_intro_text_word_count_invalid"],
        },
    }

    result = RenderExecutionResult.from_mapping(payload)

    assert result.candidate_dir == tmp_path / "work" / "233541" / "candidate"
    assert result.candidate_csv_path == tmp_path / "work" / "233541" / "candidate" / "233541.csv"
    assert result.published_csv_path is None
    assert result.description_path == tmp_path / "work" / "233541" / "candidate" / "description.html"
    assert result.characteristics_path == tmp_path / "work" / "233541" / "candidate" / "characteristics.html"
    assert result.validation_report_path == tmp_path / "work" / "233541" / "candidate" / "233541.validation.json"
    assert result.run_status == RunStatus.FAILED
    assert result.metadata_path == tmp_path / "work" / "233541" / "render.run.json"
    assert result.validation_report.ok is False
    assert result.validation_report.warnings == ["render warning"]
    assert result.validation_report.payload == payload["validation_report"]
    assert result.model_root == tmp_path / "work" / "233541"
    assert result.scrape_dir == tmp_path / "work" / "233541" / "scrape"
    assert result.llm_dir == tmp_path / "work" / "233541" / "llm"
    assert result.payload == payload
