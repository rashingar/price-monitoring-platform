from __future__ import annotations

import json

from pipeline.prepare_scrape_persistence import (
    PrepareScrapePersistenceInput,
    persist_prepare_scrape_artifacts,
)


def test_persist_prepare_scrape_artifacts_writes_expected_file_set_into_scrape_dir(tmp_path):
    model = "233541"
    scrape_dir = tmp_path / "work" / model / "scrape"
    llm_dir = tmp_path / "work" / model / "llm"
    llm_dir.mkdir(parents=True)
    sentinel = llm_dir / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    result = persist_prepare_scrape_artifacts(
        PrepareScrapePersistenceInput(
            model=model,
            scrape_dir=scrape_dir,
            raw_html="<html><body>δοκιμή</body></html>",
            source_payload={"name": "Προϊόν", "raw_html_path": str(scrape_dir / f"{model}.raw.html")},
            normalized_payload={"product": {"name": "Προϊόν"}},
            report_payload={"warnings": [], "files_written": []},
            bescos_raw_payload={"sections": [{"title": "Intro"}]},
        )
    )

    assert result.raw_html_path.name == f"{model}.raw.html"
    assert result.source_json_path.name == f"{model}.source.json"
    assert result.normalized_json_path.name == f"{model}.normalized.json"
    assert result.report_json_path.name == f"{model}.report.json"
    assert result.bescos_raw_path.name == "bescos_raw.json"
    assert sorted(path.name for path in scrape_dir.iterdir()) == [
        "233541.normalized.json",
        "233541.raw.html",
        "233541.report.json",
        "233541.source.json",
        "bescos_raw.json",
    ]
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert sorted(path.name for path in llm_dir.iterdir()) == ["keep.txt"]


def test_persist_prepare_scrape_artifacts_preserves_text_and_json_content_contract(tmp_path):
    model = "998877"
    scrape_dir = tmp_path / "work" / model / "scrape"
    raw_html = "<html>\n  <body>Κατηγορία & λεπτομέρειες</body>\n</html>"
    source_payload = {"title": "Καφετιέρα", "details": {"color": "Μαύρο"}}
    normalized_payload = {"product": {"meta_keywords": ["Καφετιέρα", "Μαύρο"]}}
    report_payload = {"warnings": ["ok"], "files_written": []}

    result = persist_prepare_scrape_artifacts(
        PrepareScrapePersistenceInput(
            model=model,
            scrape_dir=scrape_dir,
            raw_html=raw_html,
            source_payload=source_payload,
            normalized_payload=normalized_payload,
            report_payload=report_payload,
        )
    )

    assert result.raw_html_path.read_text(encoding="utf-8") == raw_html

    for path, payload in (
        (result.source_json_path, source_payload),
        (result.normalized_json_path, normalized_payload),
        (result.report_json_path, report_payload),
    ):
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert json.loads(text) == payload

    assert "Καφετιέρα" in result.source_json_path.read_text(encoding="utf-8")


def test_persist_prepare_scrape_artifacts_cleans_stale_support_artifacts_without_touching_llm_paths(tmp_path):
    model = "445566"
    scrape_dir = tmp_path / "work" / model / "scrape"
    scrape_dir.mkdir(parents=True)
    stale_sections_path = scrape_dir / "bescos_raw.json"
    stale_sections_path.write_text('{"old": true}\n', encoding="utf-8")

    llm_dir = tmp_path / "work" / model / "llm"
    llm_dir.mkdir(parents=True)
    llm_sentinel = llm_dir / "task_manifest.json"
    llm_sentinel.write_text('{"llm": true}\n', encoding="utf-8")

    result = persist_prepare_scrape_artifacts(
        PrepareScrapePersistenceInput(
            model=model,
            scrape_dir=scrape_dir,
            raw_html="<html></html>",
            source_payload={"name": "Example"},
            normalized_payload={"product": {}},
            report_payload={"warnings": []},
        )
    )

    assert not result.bescos_raw_path.exists()
    assert llm_sentinel.read_text(encoding="utf-8") == '{"llm": true}\n'
    assert sorted(path.name for path in scrape_dir.iterdir()) == [
        "445566.normalized.json",
        "445566.raw.html",
        "445566.report.json",
        "445566.source.json",
    ]
