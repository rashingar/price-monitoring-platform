import csv
import json
from pathlib import Path

import pytest

from product_factory.mapping import build_row
from product_factory.models import (
    CLIInput,
    ParsedProduct,
    SchemaMatchResult,
    TaxonomyResolution,
)
from product_factory.parser_product_skroutz import SkroutzProductParser
from product_factory.repo_paths import PRODUCT_TEMPLATE_PATH
from product_factory.skroutz_sections import extract_skroutz_section_window
from product_factory.taxonomy import TaxonomyResolver
from product_factory.utils import load_template_headers
from product_factory.validator import validate_candidate_csv

SAMPLES = {
    "143481": {
        "url": "https://www.skroutz.gr/s/61800471/tcl-q65h-soundbar-5-1-bluetooth-hdmi-kai-wi-fi-me-asyrmato-subwoofer-mayro.html",
        "photos": 8,
        "sections": 9,
        "skroutz_status": 1,
        "boxnow": 0,
        "price": "269",
    },
    "344317": {
        "url": "https://www.skroutz.cy/s/65282590/tefal-subito-kafetiera-filtrou-1000w.html",
        "photos": 2,
        "sections": 0,
        "skroutz_status": 0,
        "boxnow": 0,
        "price": "39",
    },
    "341490": {
        "url": "https://www.skroutz.gr/s/51055155/Estia-Intense-Vrastiras-1-7lt-2200W-Luminus-Mat.html",
        "photos": 7,
        "sections": 0,
        "skroutz_status": 0,
        "boxnow": 1,
        "price": "19",
    },
}


@pytest.fixture(autouse=True)
def disable_eprel_energy_label_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "product_factory.parser_product_skroutz.resolve_eprel_energy_label_asset_url",
        lambda **_kwargs: "",
    )


def _snapshot(root: Path, *parts: str) -> dict:
    return json.loads(
        (root / "golden_snapshots" / "skroutz" / Path(*parts)).read_text(
            encoding="utf-8"
        )
    )


def _cli(model: str) -> CLIInput:
    sample = SAMPLES[model]
    return CLIInput(
        model=model,
        url=sample["url"],
        photos=sample["photos"],
        sections=sample["sections"],
        skroutz_status=sample["skroutz_status"],
        boxnow=sample["boxnow"],
        price=sample["price"],
        out="unused",
    )


def _parsed_and_taxonomy(
    skroutz_fixtures_root: Path, model: str
) -> tuple[ParsedProduct, TaxonomyResolution]:
    sample = SAMPLES[model]
    html = (skroutz_fixtures_root / "html" / f"{model}.html").read_text(
        encoding="utf-8"
    )
    parsed = SkroutzProductParser().parse(html, sample["url"])
    taxonomy, _ = TaxonomyResolver().resolve(
        parsed.source.breadcrumbs,
        parsed.source.canonical_url or sample["url"],
        parsed.source.name,
        parsed.source.key_specs,
        parsed.source.spec_sections,
    )
    return parsed, taxonomy


@pytest.mark.parametrize("model", ["143481", "344317", "341490"])
def test_skroutz_parser_snapshot_covers_stable_fixture_fields(
    fixtures_root: Path, skroutz_fixtures_root: Path, model: str
) -> None:
    parsed, _taxonomy = _parsed_and_taxonomy(skroutz_fixtures_root, model)
    source = parsed.source

    actual = {
        "source_name": source.source_name,
        "page_type": source.page_type,
        "product_code": source.product_code,
        "brand": source.brand,
        "mpn": source.mpn,
        "name": source.name,
        "canonical_url": source.canonical_url,
        "category_tag_text": source.category_tag_text,
        "category_tag_href": source.category_tag_href,
        "category_tag_slug": source.category_tag_slug,
        "skroutz_family": source.skroutz_family,
        "gallery_image_count": len(source.gallery_images),
        "spec_section_count": len(source.spec_sections),
        "key_specs": [item.to_dict() for item in source.key_specs[:5]],
    }

    assert actual == _snapshot(fixtures_root, "parser", f"{model}.expected.json")


@pytest.mark.parametrize("model", ["143481", "344317", "341490"])
def test_skroutz_taxonomy_snapshot_covers_resolved_category_contract(
    fixtures_root: Path,
    skroutz_fixtures_root: Path,
    model: str,
) -> None:
    parsed, taxonomy = _parsed_and_taxonomy(skroutz_fixtures_root, model)

    actual = {
        "parent_category": taxonomy.parent_category,
        "leaf_category": taxonomy.leaf_category,
        "sub_category": taxonomy.sub_category or "",
        "taxonomy_source_category": parsed.source.taxonomy_source_category,
        "taxonomy_match_type": parsed.source.taxonomy_match_type,
        "taxonomy_rule_id": parsed.source.taxonomy_rule_id,
        "taxonomy_ambiguity": parsed.source.taxonomy_ambiguity,
        "taxonomy_escalation_reason": parsed.source.taxonomy_escalation_reason,
    }

    assert actual == _snapshot(fixtures_root, "taxonomy", f"{model}.expected.json")


@pytest.mark.parametrize("model", ["143481", "344317", "341490"])
def test_skroutz_render_row_snapshot_covers_deterministic_fields(
    fixtures_root: Path,
    skroutz_fixtures_root: Path,
    model: str,
) -> None:
    parsed, taxonomy = _parsed_and_taxonomy(skroutz_fixtures_root, model)
    row, _normalized, _warnings = build_row(
        cli=_cli(model),
        parsed=parsed,
        taxonomy=taxonomy,
        schema_match=SchemaMatchResult(),
        llm_product={
            "meta_description": "Snapshot meta description",
            "meta_keywords": ["Snapshot", parsed.source.brand, parsed.source.mpn],
        },
    )

    actual = {
        key: row[key]
        for key in [
            "model",
            "mpn",
            "name",
            "meta_title",
            "seo_keyword",
            "price",
            "category",
            "image",
            "additional_image",
            "manufacturer",
            "product_url",
            "skroutz_status",
            "boxnow",
        ]
    }

    assert actual == _snapshot(fixtures_root, "render_row", f"{model}.expected.json")


def test_skroutz_143481_section_extraction_snapshot(
    fixtures_root: Path, skroutz_fixtures_root: Path
) -> None:
    html = (skroutz_fixtures_root / "html" / "143481.html").read_text(encoding="utf-8")
    extracted = extract_skroutz_section_window(html, SAMPLES["143481"]["url"])
    rendered = json.loads(
        (
            skroutz_fixtures_root
            / "rendered_sections"
            / "143481.rendered_sections.json"
        ).read_text(encoding="utf-8")
    )

    actual = {
        "section_count": len(extracted["sections"]),
        "window": {
            key: extracted["window"].get(key)
            for key in [
                "start_anchor",
                "stop_anchor",
                "duplicate_signatures_skipped",
                "selected_container_index",
                "candidate_count",
            ]
        },
        "titles": [section["title"] for section in extracted["sections"]],
        "body_signals": [
            extracted["sections"][0]["paragraph"][:80],
            extracted["sections"][3]["paragraph"][:80],
        ],
        "first_image_candidate_suffix": extracted["sections"][0]["image_candidates"][
            0
        ].rsplit("/", 1)[-1],
        "rendered_section_image_url_count": len(
            [
                section
                for section in rendered["sections"]
                if section.get("resolved_image_url")
            ]
        ),
        "local_filenames": [
            f"besco{index}.jpg" for index in range(1, len(rendered["sections"]) + 1)
        ],
    }

    assert actual == _snapshot(fixtures_root, "sections", "143481.expected.json")


def test_skroutz_validation_snapshot_covers_basic_candidate_health(
    tmp_path: Path,
    fixtures_root: Path,
    skroutz_fixtures_root: Path,
) -> None:
    model = "143481"
    parsed, taxonomy = _parsed_and_taxonomy(skroutz_fixtures_root, model)
    row, _normalized, _warnings = build_row(
        cli=_cli(model),
        parsed=parsed,
        taxonomy=taxonomy,
        schema_match=SchemaMatchResult(),
        llm_product={
            "meta_description": "Snapshot meta description",
            "meta_keywords": ["Snapshot", parsed.source.brand, parsed.source.mpn],
        },
    )
    row["characteristics"] = (
        row["characteristics"]
        or "<table><tbody><tr><td>Snapshot</td><td>OK</td></tr></tbody></table>"
    )
    headers = load_template_headers(PRODUCT_TEMPLATE_PATH)
    candidate = tmp_path / "candidate.csv"
    baseline = tmp_path / "baseline.csv"
    for path in [candidate, baseline]:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerow({header: row.get(header, "") for header in headers})

    report = validate_candidate_csv(candidate, baseline_path=baseline)
    actual = {
        "ok": report["ok"],
        "errors": report["errors"],
        "summary": report["summary"],
        "field_health": {
            key: {"status": report["field_health"][key]["status"]}
            for key in [
                "model",
                "mpn",
                "name",
                "description",
                "characteristics",
                "category",
                "price",
                "meta_keyword",
                "meta_title",
                "meta_description",
                "seo_keyword",
                "product_url",
            ]
        },
    }

    assert actual == _snapshot(fixtures_root, "validation", "143481.expected.json")
