"""CSV parsing for Product Factory batch intake."""

from __future__ import annotations

import csv
import io

from ecommerce.product_factory_batch.models import ParsedBatchCsv, ParsedBatchRow

REQUIRED_COLUMNS = ("model", "brand", "name")


class ProductFactoryBatchCsvError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_product_factory_batch_csv(content: bytes | str) -> ParsedBatchCsv:
    text = _decode_csv(content)
    delimiter = _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise ProductFactoryBatchCsvError("empty_csv", "CSV file is empty.")
    field_map = {
        _normalize_header(field): field
        for field in reader.fieldnames
        if field is not None
    }
    missing = [column for column in REQUIRED_COLUMNS if column not in field_map]
    if missing:
        raise ProductFactoryBatchCsvError(
            "missing_required_columns",
            f"CSV is missing required columns: {', '.join(missing)}.",
        )

    rows: list[ParsedBatchRow] = []
    for row_number, row in enumerate(reader, start=2):
        model = _cell(row, field_map["model"])
        brand = _cell(row, field_map["brand"])
        name = _cell(row, field_map["name"])
        if not model:
            raise ProductFactoryBatchCsvError(
                "empty_model", f"CSV row {row_number} has an empty model."
            )
        if not name:
            raise ProductFactoryBatchCsvError(
                "empty_name", f"CSV row {row_number} has an empty name."
            )
        rows.append(
            ParsedBatchRow(row_number=row_number, model=model, brand=brand, name=name)
        )
    if not rows:
        raise ProductFactoryBatchCsvError("empty_csv", "CSV file has no product rows.")
    return ParsedBatchCsv(delimiter=delimiter, rows=tuple(rows))


def _decode_csv(content: bytes | str) -> str:
    if isinstance(content, str):
        return content
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProductFactoryBatchCsvError(
            "invalid_encoding", "CSV file must be UTF-8 encoded."
        ) from exc


def _detect_delimiter(text: str) -> str:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        if dialect.delimiter in {",", ";"}:
            return dialect.delimiter
    except csv.Error:
        pass
    header = sample.splitlines()[0] if sample.splitlines() else ""
    return ";" if header.count(";") > header.count(",") else ","


def _normalize_header(value: object) -> str:
    return str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")


def _cell(row: dict[str, object], field_name: str) -> str:
    return str(row.get(field_name) or "").strip()
