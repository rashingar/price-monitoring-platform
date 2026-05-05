from pathlib import Path

from pipeline.csv_writer import write_csv_row
from pipeline.validator import validate_candidate_csv


def make_mojibake(text: str) -> str:
    return text.encode("utf-8").decode("latin1")


def test_validator_detects_encoding_issue_and_missing_required_fields(tmp_path: Path) -> None:
    template = tmp_path / "template.csv"
    template.write_text(
        "model,mpn,name,description,characteristics,category,image,manufacturer,price,meta_keyword,meta_title,meta_description,seo_keyword,product_url\n",
        encoding="utf-8",
    )
    candidate = tmp_path / "candidate.csv"
    broken_text = make_mojibake("Κακό κείμενο ελέγχου")
    write_csv_row(
        {
            "model": "233541",
            "mpn": "",
            "name": "LG GSGV80PYLL – Ψυγείο",
            "description": broken_text,
            "characteristics": "<table></table>",
            "category": "Ψυγεία",
            "image": "catalog/01_main/233541/233541-1.jpg",
            "manufacturer": "LG",
            "price": "2099",
            "meta_keyword": "LG",
            "meta_title": "LG | eTranoulis",
            "meta_description": broken_text,
            "seo_keyword": "lg-gsgv80pyll",
            "product_url": "https://www.etranoulis.gr/lg-gsgv80pyll",
        },
        candidate,
        template,
    )

    report = validate_candidate_csv(candidate, template_path=template)

    assert report["ok"] is False
    assert "required_field_missing:mpn" in report["errors"]
    assert report["field_health"]["description"]["status"] == "encoding_issue"
    assert "c1_control_character" in report["field_health"]["description"]["encoding_issues"]


def test_validator_compares_against_baseline(tmp_path: Path) -> None:
    template = tmp_path / "template.csv"
    template.write_text("model,mpn,name\n", encoding="utf-8")
    baseline = tmp_path / "baseline.csv"
    candidate = tmp_path / "candidate.csv"
    write_csv_row({"model": "233541", "mpn": "GSGV80PYLL", "name": "LG GSGV80PYLL – Ψυγείο"}, baseline, template)
    write_csv_row({"model": "233541", "mpn": "GSGV80PYLL", "name": "LG GSGV80PYLL – Ψυγείο Ντουλάπα"}, candidate, template)

    report = validate_candidate_csv(candidate, baseline_path=baseline, template_path=template)

    assert report["field_health"]["model"]["status"] == "match"
    assert report["field_health"]["name"]["status"] == "different_but_valid"

