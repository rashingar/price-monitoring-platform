"""BridgeCraft bridge execution for simple stock balance CSV files."""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

LOGGER = logging.getLogger("pricefetcher.bridge")

DEFAULT_STOCK_CSV_PATH = Path(r"C:\Exports\CheckWHouseBalance.csv")
ARTIFACT_NAMES = (
    "oc_import.csv",
    "summary.csv",
    "updated.csv",
    "swings.csv",
    "unknown_codes.csv",
    "codes_not_in_entersoft.csv",
)

ENCODINGS: Tuple[str, ...] = (
    "utf-8-sig",
    "utf-8",
    "latin-1",
    "cp1253",
    "iso-8859-7",
    "cp1252",
)

NBSP = "\u00A0"
NNBSP = "\u202F"


@dataclass(frozen=True)
class BridgeArtifact:
    name: str
    path: Path


@dataclass(frozen=True)
class BridgeRunSummary:
    updated_count: int
    unknown_count: int
    codes_not_in_entersoft_count: int
    invalid_or_composite_models_ignored: int


@dataclass(frozen=True)
class BridgeRunResult:
    run_dir: Path
    artifacts: Tuple[BridgeArtifact, ...]
    summary: BridgeRunSummary

    @property
    def oc_import(self) -> Path:
        return self._artifact_path("oc_import.csv")

    @property
    def summary_csv(self) -> Path:
        return self._artifact_path("summary.csv")

    @property
    def updated(self) -> Path:
        return self._artifact_path("updated.csv")

    @property
    def swings(self) -> Path:
        return self._artifact_path("swings.csv")

    @property
    def unknown_codes(self) -> Path:
        return self._artifact_path("unknown_codes.csv")

    @property
    def codes_not_in_entersoft(self) -> Path:
        return self._artifact_path("codes_not_in_entersoft.csv")

    def _artifact_path(self, name: str) -> Path:
        for artifact in self.artifacts:
            if artifact.name == name:
                return artifact.path
        raise KeyError(name)


@dataclass(frozen=True)
class StockCsvReadResult:
    rows_by_model: Dict[str, Dict[str, str]]
    ignored_rows: Tuple[List[str], ...]

    @property
    def ignored_count(self) -> int:
        return len(self.ignored_rows)


def is_atomic_model(model: str) -> bool:
    """Return true only when ``model.strip()`` is exactly six digits."""
    return str(model or "").strip().isdigit() and len(str(model or "").strip()) == 6


def read_model_quantity_export(path: Path) -> Dict[str, Dict[str, str]]:
    """Read a simple stock CSV with ``model,quantity`` headers."""
    return read_balance_stock_csv(path).rows_by_model


def read_balance_stock_csv(path: Path) -> StockCsvReadResult:
    """Read the simplified bridge stock file and collect ignored non-atomic rows."""
    text = _open_text_auto(path)
    rows = _sniff_rows(text)
    if not rows:
        raise ValueError("Stock CSV: missing header row.")

    headers = [h.strip().lower() for h in rows[0]]
    required = ["model", "quantity"]
    missing = [c for c in required if c not in headers]
    if missing:
        raise ValueError(f"Stock CSV missing columns: {missing}. Found: {rows[0]}")

    idx = {name: headers.index(name) for name in required}
    stock_rows: Dict[str, Dict[str, str]] = {}
    ignored_rows: List[List[str]] = []

    for row in rows[1:]:
        if len(row) <= max(idx.values()):
            continue
        model = row[idx["model"]].strip()
        quantity = row[idx["quantity"]]
        if not is_atomic_model(model):
            ignored_rows.append([model, "", quantity, "", "", "invalid_or_composite_model"])
            continue
        qty = _parse_quantity(quantity)
        stock_rows[model] = {"model": model, "quantity": str(qty)}

    return StockCsvReadResult(rows_by_model=stock_rows, ignored_rows=tuple(ignored_rows))


def run_bridge_from_balance_csv(
    stock_csv_path: Path,
    opencart_csv_path: Path,
    output_dir: Path,
) -> BridgeRunResult:
    """
    Run the simplified stock balance -> OpenCart bridge.

    ``stock_csv_path`` must use the ``model,quantity`` schema. Entersoft
    ``Προκύπτον`` exports are intentionally not parsed in this branch.
    """
    stock_result = read_balance_stock_csv(stock_csv_path)
    return _run_bridge_inventory(
        inventory_path=stock_csv_path,
        inventory_data=stock_result.rows_by_model,
        ignored_inventory_rows=list(stock_result.ignored_rows),
        opencart_csv=opencart_csv_path,
        output_dir=output_dir,
    )


def read_oc_export(path: Path) -> Tuple[Dict[str, Dict[str, str]], List[List[str]]]:
    """Read an OpenCart export with required model, price, quantity, status columns."""
    text = _open_text_auto(path)
    rows = _sniff_rows(text)
    if not rows:
        raise ValueError("OpenCart export: missing header row.")

    headers = [h.strip().lower() for h in rows[0]]
    required = ["model", "price", "quantity", "status"]
    missing = [c for c in required if c not in headers]
    if missing:
        raise ValueError(f"OpenCart export missing columns: {missing}. Found: {rows[0]}")

    idx = {name: headers.index(name) for name in required}
    name_idx = headers.index("name") if "name" in headers else None
    oc_rows: Dict[str, Dict[str, str]] = {}
    invalid_rows: List[List[str]] = []

    for row in rows[1:]:
        if len(row) <= max(idx.values()):
            continue
        model = row[idx["model"]].strip()
        if not model:
            continue
        name = row[name_idx] if name_idx is not None and name_idx < len(row) else ""
        if not is_atomic_model(model):
            invalid_rows.append(
                [
                    model,
                    _clean_name(name),
                    row[idx["quantity"]],
                    row[idx["price"]],
                    row[idx["status"]],
                    "invalid_or_composite_model",
                ]
            )
            continue

        oc_rows[model] = {
            "model": model,
            "name": _clean_name(name),
            "price": row[idx["price"]],
            "quantity": row[idx["quantity"]],
            "status": row[idx["status"]],
        }

    return oc_rows, invalid_rows


def _run_bridge_inventory(
    inventory_path: Path,
    inventory_data: Dict[str, Dict[str, str]],
    ignored_inventory_rows: List[List[str]],
    opencart_csv: Path,
    output_dir: Path,
) -> BridgeRunResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "bridge.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    LOGGER.addHandler(file_handler)

    try:
        LOGGER.info("Starting bridge run")
        LOGGER.info("Stock CSV: %s", inventory_path)
        LOGGER.info("OpenCart: %s", opencart_csv)

        oc_data, oc_invalid_rows = read_oc_export(opencart_csv)
        exception_models = _read_exceptions(output_dir)

        rows_import: List[List[str]] = []
        rows_summary: List[List[str]] = []
        rows_updated: List[List[str]] = []
        swings: List[List[str]] = []
        codes_not_in_entersoft: List[List[str]] = []
        unknown_codes: List[List[str]] = [*ignored_inventory_rows, *oc_invalid_rows]
        swing_threshold = 25

        for model in sorted(oc_data):
            stock = inventory_data.get(model)
            oc = oc_data[model]
            if stock is None:
                if model not in exception_models:
                    codes_not_in_entersoft.append([model, oc.get("name", "")])
                continue

            old_qty = _parse_int(oc.get("quantity", "0"))
            new_qty = _parse_int(stock.get("quantity", "0"))
            old_price = _parse_float(oc.get("price", "0"))
            new_price = old_price
            old_status = _parse_int(oc.get("status", "0"))
            new_status = old_status

            if new_qty <= 0:
                new_status = 0
            elif new_price == 0:
                new_status = 0
            elif old_status == 0 and new_qty > 0 and new_price > 0:
                new_status = 1
            elif old_price == 0 and new_price > 0 and new_qty > 0:
                new_status = 1

            if old_qty < 0 and new_qty <= 0:
                continue

            delta_qty = new_qty - old_qty
            delta_status = new_status - old_status
            if delta_qty == 0 and delta_status == 0:
                continue

            name = oc.get("name", "")
            rows_import.append([model, str(new_qty), f"{new_price:.2f}", str(new_status)])
            rows_summary.append(
                [
                    model,
                    name,
                    old_qty,
                    new_qty,
                    old_price,
                    new_price,
                    old_status,
                    new_status,
                    "unchanged",
                ]
            )
            rows_updated.append([model, name, new_qty, f"{new_price:.2f}", new_status])

            if abs(delta_qty) >= swing_threshold:
                swings.append([model, name, old_qty, new_qty, delta_qty])

        paths = {
            "oc_import.csv": output_dir / "oc_import.csv",
            "summary.csv": output_dir / "summary.csv",
            "updated.csv": output_dir / "updated.csv",
            "swings.csv": output_dir / "swings.csv",
            "unknown_codes.csv": output_dir / "unknown_codes.csv",
            "codes_not_in_entersoft.csv": output_dir / "codes_not_in_entersoft.csv",
        }

        _write_csv(paths["oc_import.csv"], ["model", "quantity", "price", "status"], rows_import)
        _write_csv(
            paths["summary.csv"],
            [
                "model",
                "name",
                "old_qty",
                "new_qty",
                "old_price",
                "new_price",
                "old_status",
                "new_status",
                "price_change",
            ],
            rows_summary,
        )
        _write_csv(paths["updated.csv"], ["model", "name", "quantity", "price", "status"], rows_updated)
        _write_csv(paths["swings.csv"], ["model", "name", "old_qty", "new_qty", "delta_qty"], swings)
        _write_csv(paths["unknown_codes.csv"], ["model", "name", "quantity", "price", "status", "reason"], unknown_codes)
        _write_csv(paths["codes_not_in_entersoft.csv"], ["model", "name"], codes_not_in_entersoft)

        LOGGER.info("Bridge run complete. Output dir: %s", output_dir)
        artifacts = tuple(BridgeArtifact(name=name, path=paths[name]) for name in ARTIFACT_NAMES)
        return BridgeRunResult(
            run_dir=output_dir,
            artifacts=artifacts,
            summary=BridgeRunSummary(
                updated_count=len(rows_updated),
                unknown_count=len(unknown_codes),
                codes_not_in_entersoft_count=len(codes_not_in_entersoft),
                invalid_or_composite_models_ignored=len(ignored_inventory_rows) + len(oc_invalid_rows),
            ),
        )
    finally:
        LOGGER.removeHandler(file_handler)
        file_handler.close()


def _open_text_auto(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("pricefetcher.bridge", b"", 0, 1, f"Cannot decode {path}")


def _sniff_rows(text: str) -> List[List[str]]:
    lines = text.splitlines()
    sample = "\n".join(lines[:5]) if lines else ""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t"])
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ","
    return list(csv.reader(io.StringIO(text), dialect=dialect))


def _read_exceptions(out_dir: Path) -> set[str]:
    path = out_dir / "Exceptions.csv"
    if not path.exists():
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["model", "name"])
        return set()
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return {str(row.get("model", "")).strip() for row in reader if row.get("model")}
    except Exception:
        return set()


def _write_csv(path: Path, headers: List[str], rows: List[List]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def _clean_name(value: str) -> str:
    s = "" if value is None else str(value)
    return s.rstrip('"').strip()


def _parse_quantity(value: object) -> int:
    if value is None:
        return 0
    s = str(value).strip().replace(NBSP, " ").replace(NNBSP, " ")
    s = re.sub(r"\s+", " ", s)
    negative = False
    if s.endswith("-"):
        negative, s = True, s[:-1].strip()
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()
    s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    s = s.replace(" ", "")
    try:
        number = float(s)
    except ValueError:
        return 0
    if negative:
        number = -number
    return max(0, int(round(number)))


def _parse_float(value: object) -> float:
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return 0.0


def _parse_int(value: object) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except ValueError:
        return 0
