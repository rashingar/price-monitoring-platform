from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .jobs.models import JobStatus, JobType
from .jobs.run_product_factory_job import main as run_job_worker_main
from .jobs.store import DEFAULT_JOBS_DIR, JobStore
from .normalize import normalize_for_match, normalize_whitespace

ESTIA_BASE_URL = "https://estiahomeart.com"
DEFAULT_PHOTOS = 100
DEFAULT_SECTIONS = 0
DEFAULT_GALLERY_MODE = "all"
NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkg_rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
REQUIRED_COLUMNS = {"model", "name", "mpn", "brand"}


@dataclass(slots=True)
class EstiaBatchRow:
    row_number: int
    model: str
    name: str
    mpn: str
    brand: str
    price: str = "0"
    boxnow: int = 0
    source_url: str = ""


@dataclass(slots=True)
class EstiaBatchSummary:
    workbook_path: str
    worksheet_name: str = ""
    total_rows: int = 0
    valid_rows: int = 0
    queued_rows: int = 0
    skipped_rows: int = 0
    warnings: list[str] = field(default_factory=list)
    job_ids: list[str] = field(default_factory=list)
    jobs_succeeded: int = 0
    jobs_failed: int = 0
    generated_outputs: list[dict[str, str]] = field(default_factory=list)
    failed_mpns: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workbook_path": self.workbook_path,
            "worksheet_name": self.worksheet_name,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "queued_rows": self.queued_rows,
            "skipped_rows": self.skipped_rows,
            "warnings": self.warnings,
            "job_ids": self.job_ids,
            "jobs_succeeded": self.jobs_succeeded,
            "jobs_failed": self.jobs_failed,
            "generated_outputs": self.generated_outputs,
            "failed_mpns": self.failed_mpns,
        }


def read_estia_xlsx_rows(path: Path | str) -> tuple[str, list[dict[str, str]]]:
    workbook_path = Path(path)
    with ZipFile(workbook_path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_name, sheet_path = _select_sheet(archive)
        rows = _read_sheet_rows(archive, sheet_path, shared_strings)
    if not rows:
        return sheet_name, []
    header = [_normalize_header(value) for value in rows[0]]
    data_rows: list[dict[str, str]] = []
    for offset, values in enumerate(rows[1:], start=2):
        if not any(normalize_whitespace(value) for value in values):
            continue
        row: dict[str, str] = {"_row_number": str(offset)}
        for index, key in enumerate(header):
            if not key:
                continue
            row[key] = normalize_whitespace(values[index] if index < len(values) else "")
        data_rows.append(row)
    return sheet_name, data_rows


def validate_estia_batch_rows(
    rows: list[dict[str, str]], *, workbook_path: Path | str, worksheet_name: str
) -> tuple[list[EstiaBatchRow], EstiaBatchSummary]:
    summary = EstiaBatchSummary(
        workbook_path=str(workbook_path),
        worksheet_name=worksheet_name,
        total_rows=len(rows),
    )
    if rows:
        missing_columns = sorted(REQUIRED_COLUMNS - set(rows[0]))
        if missing_columns:
            summary.warnings.append(
                f"missing_required_columns:{','.join(missing_columns)}"
            )
            summary.skipped_rows = len(rows)
            return [], summary

    valid: list[EstiaBatchRow] = []
    for row in rows:
        row_number = int(row.get("_row_number") or 0)
        model = _normalize_model(row.get("model", ""))
        name = normalize_whitespace(row.get("name", ""))
        mpn = normalize_whitespace(row.get("mpn", ""))
        brand = normalize_whitespace(row.get("brand", ""))
        price = normalize_whitespace(row.get("price", "")) or "0"
        boxnow = _parse_bool_int(row.get("boxnow", "0"))
        row_warnings = []
        if not model or not model.isdigit() or len(model) != 6:
            row_warnings.append("invalid_model")
        if not name:
            row_warnings.append("missing_name")
        if not mpn:
            row_warnings.append("missing_mpn")
        if not brand:
            row_warnings.append("missing_brand")
        if row_warnings:
            summary.warnings.append(
                f"row {row_number}: skipped:{','.join(row_warnings)}"
            )
            continue
        valid.append(
            EstiaBatchRow(
                row_number=row_number,
                model=model,
                name=name,
                mpn=mpn,
                brand=brand,
                price=price,
                boxnow=boxnow,
                source_url=build_estia_source_url(mpn),
            )
        )
    summary.valid_rows = len(valid)
    summary.skipped_rows = summary.total_rows - summary.valid_rows
    return valid, summary


def build_estia_source_url(mpn: str) -> str:
    return f"{ESTIA_BASE_URL}/{normalize_whitespace(mpn).strip('/')}"


def enqueue_estia_xlsx_batch(
    path: Path | str,
    *,
    job_store: JobStore | None = None,
    photos: int = DEFAULT_PHOTOS,
    sections: int = DEFAULT_SECTIONS,
    skip_publish: bool = True,
    run: bool = False,
) -> EstiaBatchSummary:
    workbook_path = Path(path)
    sheet_name, raw_rows = read_estia_xlsx_rows(workbook_path)
    rows, summary = validate_estia_batch_rows(
        raw_rows, workbook_path=workbook_path, worksheet_name=sheet_name
    )
    store = job_store or JobStore()
    for row in rows:
        payload = build_full_pipeline_payload(
            row,
            photos=photos,
            sections=sections,
            skip_publish=skip_publish,
        )
        record = store.enqueue(JobType.FULL_PIPELINE, payload)
        summary.job_ids.append(record.job_id)
        summary.queued_rows += 1
        if run:
            exit_code = run_job_worker_main(
                ["--job-id", record.job_id, "--job-root", str(store.jobs_dir)]
            )
            updated = store.get_job(record.job_id)
            if updated and updated.status == JobStatus.SUCCEEDED and exit_code == 0:
                summary.jobs_succeeded += 1
                output = updated.artifacts.get("render.published_csv_path") or updated.artifacts.get(
                    "published_csv_path", ""
                )
                if output:
                    summary.generated_outputs.append(
                        {"model": row.model, "mpn": row.mpn, "path": output}
                    )
            else:
                summary.jobs_failed += 1
                summary.failed_mpns.append(
                    {
                        "model": row.model,
                        "mpn": row.mpn,
                        "error": (updated.error if updated else None) or "job_failed",
                    }
                )
    return summary


def build_full_pipeline_payload(
    row: EstiaBatchRow,
    *,
    photos: int = DEFAULT_PHOTOS,
    sections: int = DEFAULT_SECTIONS,
    skip_publish: bool = True,
) -> dict[str, Any]:
    return {
        "model": row.model,
        "product_name": row.name,
        "source_url": row.source_url,
        "bestprice_enabled": False,
        "skroutz_enabled": False,
        "boxnow_enabled": bool(row.boxnow),
        "price": row.price,
        "photos": max(int(photos), 1),
        "sections": max(int(sections), 0),
        "gallery_mode": DEFAULT_GALLERY_MODE,
        "skip_publish": bool(skip_publish),
        "trigger_source": "estia_xlsx_batch",
        "source_resolution": {
            "provider": "estia",
            "row_number": row.row_number,
            "mpn": row.mpn,
            "brand": row.brand,
            "original_name": row.name,
        },
    }


def _read_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("main:si", NS):
        strings.append("".join(node.text or "" for node in item.findall(".//main:t", NS)))
    return strings


def _select_sheet(archive: ZipFile) -> tuple[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("pkg_rel:Relationship", NS)
    }
    sheets = []
    for sheet in workbook.findall("main:sheets/main:sheet", NS):
        name = str(sheet.attrib.get("name") or "")
        rel_id = str(sheet.attrib.get(f"{{{NS['rel']}}}id") or "")
        target = rel_targets.get(rel_id, "")
        if not target:
            continue
        normalized_target = target.lstrip("/")
        sheet_path = (
            normalized_target
            if normalized_target.startswith("xl/")
            else f"xl/{normalized_target}"
        )
        sheets.append((name, sheet_path))
    preferred = next(
        (
            (name, path)
            for name, path in sheets
            if normalize_for_match(name) in {normalize_for_match("Φύλλο1"), "sheet1"}
            and _sheet_has_rows(archive, path)
        ),
        None,
    )
    if preferred:
        return preferred
    for name, path in sheets:
        if _sheet_has_rows(archive, path):
            return name, path
    raise ValueError("Workbook has no non-empty worksheets")


def _sheet_has_rows(archive: ZipFile, sheet_path: str) -> bool:
    root = ET.fromstring(archive.read(sheet_path))
    return bool(root.findall("main:sheetData/main:row", NS))


def _read_sheet_rows(
    archive: ZipFile, sheet_path: str, shared_strings: list[str]
) -> list[list[str]]:
    root = ET.fromstring(archive.read(sheet_path))
    rows: list[list[str]] = []
    for row in root.findall("main:sheetData/main:row", NS):
        values_by_index: dict[int, str] = {}
        for cell in row.findall("main:c", NS):
            cell_ref = str(cell.attrib.get("r") or "")
            index = _column_index(cell_ref)
            if index < 0:
                continue
            values_by_index[index] = _cell_value(cell, shared_strings)
        if values_by_index:
            max_index = max(values_by_index)
            rows.append([values_by_index.get(index, "") for index in range(max_index + 1)])
    return rows


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return normalize_whitespace(
            "".join(node.text or "" for node in cell.findall(".//main:t", NS))
        )
    value_node = cell.find("main:v", NS)
    value = value_node.text if value_node is not None else ""
    if cell_type == "s" and value:
        try:
            return shared_strings[int(value)]
        except (IndexError, ValueError):
            return ""
    return normalize_whitespace(value)


def _column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Za-z]+)", cell_ref)
    if not match:
        return -1
    index = 0
    for char in match.group(1).upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _normalize_header(value: str) -> str:
    return normalize_whitespace(value).lower().replace(" ", "_")


def _normalize_model(value: str) -> str:
    model = normalize_whitespace(value)
    if re.fullmatch(r"\d+\.0+", model):
        model = model.split(".", 1)[0]
    return model


def _parse_bool_int(value: str) -> int:
    normalized = normalize_whitespace(value).lower()
    if normalized in {"true", "yes", "y", "ναι"}:
        return 1
    try:
        return 1 if int(float(normalized or "0")) else 0
    except ValueError:
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m product_factory.estia_batch_import"
    )
    parser.add_argument("xlsx_path")
    parser.add_argument("--job-root", default=str(DEFAULT_JOBS_DIR))
    parser.add_argument("--photos", type=int, default=DEFAULT_PHOTOS)
    parser.add_argument("--sections", type=int, default=DEFAULT_SECTIONS)
    parser.add_argument("--run", action="store_true")
    publish_group = parser.add_mutually_exclusive_group()
    publish_group.add_argument(
        "--skip-publish", action="store_true", default=True
    )
    publish_group.add_argument(
        "--publish", action="store_false", dest="skip_publish"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = enqueue_estia_xlsx_batch(
        args.xlsx_path,
        job_store=JobStore(Path(args.job_root)),
        photos=args.photos,
        sections=args.sections,
        skip_publish=bool(args.skip_publish),
        run=bool(args.run),
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 1 if summary.jobs_failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
