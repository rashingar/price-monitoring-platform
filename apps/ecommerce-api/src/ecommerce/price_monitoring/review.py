"""Price Monitoring review row loading and manual price action handling."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from ecommerce.catalog.source_catalog import is_atomic_model
from ecommerce.ignore.product_ignore import IgnoredProductInput, upsert_ignored_product

INPUT_COLUMNS = ("model", "mpn", "name", "price")
REVIEW_COLUMNS = [
    "model",
    "mpn",
    "name",
    "source",
    "current_price",
    "competitor_price",
    "competitor_store",
    "competitor_url",
    "price_delta",
    "price_delta_percent",
    "recommended_action",
    "selected_action",
    "undercut_amount",
    "target_price",
    "status",
    "warnings",
]
COMMON_ENRICHED_FILENAMES = (
    "enriched.csv",
    "fetched.csv",
    "results.csv",
    "bestprice_enriched.csv",
    "skroutz_enriched.csv",
)
SUPPORTED_ACTIONS = {"match_price", "undercut", "ignore"}
SUPPORTED_SOURCES = {"skroutz", "bestprice"}
TWO_PLACES = Decimal("0.01")


class PriceReviewError(ValueError):
    """Raised for malformed review input or invalid manual actions."""


@dataclass(frozen=True)
class PriceActionInput:
    model: str
    selected_action: str
    undercut_amount: Decimal | None = None
    reason: str = ""


@dataclass
class PriceReviewRow:
    model: str
    mpn: str
    name: str
    current_price: Decimal | None
    source: str
    competitor_price: Decimal | None
    competitor_store: str
    competitor_url: str
    price_delta: Decimal | None
    price_delta_percent: Decimal | None
    recommended_action: str
    selected_action: str
    undercut_amount: Decimal | None
    target_price: Decimal | None
    status: str
    warnings: list[str]

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "mpn": self.mpn,
            "name": self.name,
            "current_price": _decimal_to_float(self.current_price),
            "source": self.source,
            "competitor_price": _decimal_to_float(self.competitor_price),
            "competitor_store": self.competitor_store,
            "competitor_url": self.competitor_url,
            "price_delta": _decimal_to_float(self.price_delta),
            "price_delta_percent": _decimal_to_float(self.price_delta_percent),
            "recommended_action": self.recommended_action,
            "selected_action": self.selected_action,
            "undercut_amount": _decimal_to_float(self.undercut_amount),
            "target_price": _decimal_to_float(self.target_price),
            "status": self.status,
            "warnings": self.warnings,
        }

    def to_csv_dict(self) -> dict[str, str]:
        return {
            "model": self.model,
            "mpn": self.mpn,
            "name": self.name,
            "source": self.source,
            "current_price": _money_text(self.current_price),
            "competitor_price": _money_text(self.competitor_price),
            "competitor_store": self.competitor_store,
            "competitor_url": self.competitor_url,
            "price_delta": _money_text(self.price_delta),
            "price_delta_percent": _decimal_text(self.price_delta_percent),
            "recommended_action": self.recommended_action,
            "selected_action": self.selected_action,
            "undercut_amount": _money_text(self.undercut_amount),
            "target_price": _money_text(self.target_price),
            "status": self.status,
            "warnings": "; ".join(self.warnings),
        }


@dataclass(frozen=True)
class PriceReviewResult:
    run_id: str
    source: str
    rows: list[PriceReviewRow]
    review_csv_path: Path
    review_actions_path: Path
    summary: dict[str, int]
    warnings: list[str]


def load_price_review_rows(run_dir: Path, enriched_csv_path: Path | None = None) -> list[PriceReviewRow]:
    """Load input and enriched CSV data from a Price Monitoring run folder."""

    run_dir = Path(run_dir)
    if not run_dir.exists():
        raise FileNotFoundError(f"Price monitoring run folder not found: {run_dir}")

    input_csv_path = run_dir / "input.csv"
    input_rows = _read_required_csv(input_csv_path, INPUT_COLUMNS, "input.csv")
    enriched_path = discover_enriched_csv(run_dir, enriched_csv_path)
    enriched_rows = _read_csv(enriched_path, "enriched CSV")

    run_source = _load_run_source(run_dir)
    source = _resolve_source(run_source, enriched_path, enriched_rows)
    enriched_by_model = _rows_by_model(enriched_rows)
    rows: list[PriceReviewRow] = []

    for index, input_row in enumerate(input_rows):
        model = _text(input_row.get("model"))
        enriched_row = enriched_by_model.get(model)
        if enriched_row is None and index < len(enriched_rows):
            enriched_row = enriched_rows[index]
        enriched_row = enriched_row or {}
        rows.append(_build_review_row(input_row, enriched_row, source))
    return rows


def load_price_review_rows_from_observations(
    run_dir: Path,
    observations: list[dict[str, Any]],
) -> list[PriceReviewRow]:
    """Load review rows from DB-backed Vendor Sources price observations."""

    run_dir = Path(run_dir)
    if not run_dir.exists():
        raise FileNotFoundError(f"Price monitoring run folder not found: {run_dir}")
    if not observations:
        raise FileNotFoundError(f"No persisted price observations found for run: {run_dir.name}")

    input_csv_path = run_dir / "input.csv"
    input_rows = _read_required_csv(input_csv_path, INPUT_COLUMNS, "input.csv")
    run_source = _load_run_source(run_dir)
    source = _source_from_observations(observations) or run_source
    observations_by_model = _observations_by_key(observations, "model")
    observations_by_mpn = _observations_by_key(observations, "mpn")
    rows: list[PriceReviewRow] = []

    for index, input_row in enumerate(input_rows):
        model = _text(input_row.get("model"))
        mpn = _text(input_row.get("mpn"))
        observation = observations_by_model.get(model) or observations_by_mpn.get(mpn)
        if observation is None and index < len(observations):
            observation = observations[index]
        enriched_row = _observation_to_enriched_row(observation or {}, source=source)
        input_with_observed_price = dict(input_row)
        if not _text(input_with_observed_price.get("price")):
            input_with_observed_price["price"] = _text(enriched_row.get("current_price"))
        rows.append(_build_review_row(input_with_observed_price, enriched_row, _text(enriched_row.get("source")) or source))
    return rows


def apply_price_actions(
    run_dir: Path,
    actions: list[PriceActionInput],
    enriched_csv_path: Path | None = None,
) -> PriceReviewResult:
    """Apply user-selected manual pricing actions and write review artifacts."""

    run_dir = Path(run_dir)
    rows = load_price_review_rows(run_dir, enriched_csv_path)
    return apply_price_actions_to_rows(run_dir, rows, actions)


def apply_price_actions_to_rows(
    run_dir: Path,
    rows: list[PriceReviewRow],
    actions: list[PriceActionInput],
) -> PriceReviewResult:
    """Apply manual pricing actions to already-loaded review rows."""

    run_dir = Path(run_dir)
    action_by_model = _validate_action_list(actions)
    rows_by_model = {row.model: row for row in rows}
    warnings: list[str] = []

    for model, action in action_by_model.items():
        row = rows_by_model.get(model)
        if row is None:
            raise PriceReviewError(f"Action references unknown model: {model}")
        _apply_action_to_row(row, action)
        if action.selected_action == "ignore":
            _upsert_ignore_from_row(row, action)

    review_csv_path = run_dir / "review.csv"
    review_actions_path = run_dir / "review_actions.json"
    _write_review_csv(review_csv_path, rows)
    summary = _review_summary(rows, actions_count=len(actions))
    payload = {
        "run_id": run_dir.name,
        "created_at": _now_iso(),
        "source": _source_from_rows(rows),
        "actions_count": len(actions),
        "exportable_count": summary["exportable_count"],
        "ignored_count": summary["ignored_count"],
        "not_exportable_count": summary["not_exportable_count"],
        "actions": [_action_to_json(action) for action in actions],
        "warnings": warnings,
    }
    _write_json(review_actions_path, payload)

    return PriceReviewResult(
        run_id=run_dir.name,
        source=payload["source"],
        rows=rows,
        review_csv_path=review_csv_path,
        review_actions_path=review_actions_path,
        summary=summary,
        warnings=warnings,
    )


def discover_enriched_csv(run_dir: Path, enriched_csv_path: Path | None = None) -> Path:
    if enriched_csv_path is not None:
        path = Path(enriched_csv_path)
        if not path.exists():
            raise FileNotFoundError(f"Enriched CSV not found: {path}")
        return path

    for filename in COMMON_ENRICHED_FILENAMES:
        candidate = run_dir / filename
        if candidate.exists():
            return candidate

    candidates = sorted(
        path
        for path in run_dir.glob("*.csv")
        if "enriched" in path.name.lower()
        and path.name.lower() not in {"review.csv", "opencart_price_update.csv", "input.csv"}
    )
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"Enriched CSV not found in run folder: {run_dir}")


def load_review_csv(path: Path) -> list[PriceReviewRow]:
    rows = _read_required_csv(Path(path), tuple(REVIEW_COLUMNS), "review.csv")
    result: list[PriceReviewRow] = []
    for row in rows:
        warnings = [part.strip() for part in _text(row.get("warnings")).split(";") if part.strip()]
        result.append(
            PriceReviewRow(
                model=_text(row.get("model")),
                mpn=_text(row.get("mpn")),
                name=_text(row.get("name")),
                current_price=_parse_decimal(row.get("current_price")),
                source=_text(row.get("source")),
                competitor_price=_parse_decimal(row.get("competitor_price")),
                competitor_store=_text(row.get("competitor_store")),
                competitor_url=_text(row.get("competitor_url")),
                price_delta=_parse_decimal(row.get("price_delta")),
                price_delta_percent=_parse_decimal(row.get("price_delta_percent")),
                recommended_action=_text(row.get("recommended_action")),
                selected_action=_text(row.get("selected_action")),
                undercut_amount=_parse_decimal(row.get("undercut_amount")),
                target_price=_parse_decimal(row.get("target_price")),
                status=_text(row.get("status")),
                warnings=warnings,
            )
        )
    return result


def summarize_review_rows(rows: list[PriceReviewRow]) -> dict[str, int]:
    return {
        "total": len(rows),
        "review_required": sum(1 for row in rows if row.status == "review_required"),
        "not_exportable": sum(1 for row in rows if row.status == "not_exportable"),
    }


def _build_review_row(input_row: dict[str, str], enriched_row: dict[str, str], source: str) -> PriceReviewRow:
    model = _text(input_row.get("model"))
    mpn = _text(input_row.get("mpn"))
    name = _text(input_row.get("name"))
    current_price = _parse_decimal(_first_present(input_row, ("current_price", "price")))
    competitor_price = _competitor_price(enriched_row, source)
    competitor_store = _competitor_store(enriched_row, source)
    competitor_url = _competitor_url(enriched_row, source)
    warnings: list[str] = []

    if not is_atomic_model(model):
        warnings.append("composite_or_invalid_model")
    if current_price is None or current_price <= 0:
        warnings.append("missing_or_invalid_current_price")
    if competitor_price is None or competitor_price <= 0:
        warnings.append("missing_or_invalid_competitor_price")

    price_delta: Decimal | None = None
    price_delta_percent: Decimal | None = None
    if current_price is not None and current_price > 0 and competitor_price is not None and competitor_price > 0:
        price_delta = current_price - competitor_price
        price_delta_percent = (price_delta / current_price) * Decimal("100")

    recommended_action = _recommended_action(current_price, competitor_price)
    status = "review_required" if competitor_price is not None and competitor_price > 0 else "not_exportable"

    return PriceReviewRow(
        model=model,
        mpn=mpn,
        name=name,
        current_price=current_price,
        source=source,
        competitor_price=competitor_price if competitor_price is not None and competitor_price > 0 else None,
        competitor_store=competitor_store,
        competitor_url=competitor_url,
        price_delta=price_delta,
        price_delta_percent=price_delta_percent,
        recommended_action=recommended_action,
        selected_action="",
        undercut_amount=None,
        target_price=None,
        status=status,
        warnings=warnings,
    )


def _apply_action_to_row(row: PriceReviewRow, action: PriceActionInput) -> None:
    if not is_atomic_model(row.model):
        raise PriceReviewError(f"Action rejected for non-atomic model: {row.model}")
    if action.selected_action != "ignore" and (row.competitor_price is None or row.competitor_price <= 0):
        raise PriceReviewError(f"Action rejected for row without valid competitor price: {row.model}")

    row.selected_action = action.selected_action
    row.undercut_amount = action.undercut_amount

    if action.selected_action == "ignore":
        row.target_price = None
        row.status = "ignored"
        return

    if action.selected_action == "match_price":
        target_price = row.competitor_price
    else:
        if action.undercut_amount is None:
            raise PriceReviewError(f"undercut_amount is required for undercut action: {row.model}")
        target_price = row.competitor_price - action.undercut_amount

    if target_price is None or target_price <= 0:
        raise PriceReviewError(f"Computed target_price must be greater than 0 for model: {row.model}")

    row.target_price = _round_money(target_price)
    row.status = "exportable"


def _validate_action_list(actions: list[PriceActionInput]) -> dict[str, PriceActionInput]:
    action_by_model: dict[str, PriceActionInput] = {}
    for action in actions:
        model = _text(action.model)
        selected_action = _text(action.selected_action)
        if not model:
            raise PriceReviewError("model is required")
        if not selected_action:
            raise PriceReviewError(f"selected_action is required for model: {model}")
        if selected_action not in SUPPORTED_ACTIONS:
            raise PriceReviewError("selected_action must be one of: match_price, undercut, ignore")
        if selected_action == "undercut":
            if action.undercut_amount is None:
                raise PriceReviewError(f"undercut_amount is required for undercut action: {model}")
            if action.undercut_amount <= 0:
                raise PriceReviewError(f"undercut_amount must be greater than 0 for model: {model}")
        if model in action_by_model:
            raise PriceReviewError(f"Duplicate action for model: {model}")
        action_by_model[model] = PriceActionInput(
            model=model,
            selected_action=selected_action,
            undercut_amount=action.undercut_amount,
            reason=_text(action.reason),
        )
    return action_by_model


def _upsert_ignore_from_row(row: PriceReviewRow, action: PriceActionInput) -> None:
    upsert_ignored_product(
        IgnoredProductInput(
            model=row.model,
            name=row.name,
            mpn=row.mpn,
            reason=action.reason or "manual ignore from price review",
        )
    )


def _write_review_csv(path: Path, rows: list[PriceReviewRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_dict())


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _read_required_csv(path: Path, required_columns: tuple[str, ...], label: str) -> list[dict[str, str]]:
    rows = _read_csv(path, label)
    fieldnames = _fieldnames(path, label)
    normalized = {name.strip().casefold(): name for name in fieldnames if name is not None}
    missing = [column for column in required_columns if column.casefold() not in normalized]
    if missing:
        raise PriceReviewError(f"{label} missing required columns: {', '.join(missing)}")
    return [{column: _value_by_case(row, column) for column in required_columns} | row for row in rows]


def _read_csv(path: Path, label: str) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            reader = csv.DictReader(f, delimiter=_detect_delimiter(sample))
            if reader.fieldnames is None:
                raise PriceReviewError(f"{label} is missing a header row")
            return [{key: value if value is not None else "" for key, value in row.items()} for row in reader]
    except UnicodeDecodeError as exc:
        raise PriceReviewError(f"{label} must be valid UTF-8 CSV") from exc
    except csv.Error as exc:
        raise PriceReviewError(f"{label} is malformed CSV") from exc


def _fieldnames(path: Path, label: str) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        reader = csv.DictReader(f, delimiter=_detect_delimiter(sample))
        if reader.fieldnames is None:
            raise PriceReviewError(f"{label} is missing a header row")
        return list(reader.fieldnames)


def _detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        if dialect.delimiter in {",", ";", "\t"}:
            return dialect.delimiter
    except csv.Error:
        pass
    return ","


def _load_run_source(run_dir: Path) -> str:
    summary_path = run_dir / "selection_summary.json"
    if not summary_path.exists():
        return ""
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return ""
    source = _text(payload.get("source")).lower()
    return source if source in SUPPORTED_SOURCES else ""


def _resolve_source(run_source: str, enriched_path: Path, enriched_rows: list[dict[str, str]]) -> str:
    headers = {header.casefold() for row in enriched_rows for header in row.keys()}
    name = enriched_path.name.casefold()
    if any(header.startswith("bestprice_") for header in headers) or "bestprice" in name:
        return "bestprice"
    if any(header.startswith("skroutz_") for header in headers) or "skroutz" in name:
        return "skroutz"
    if run_source in SUPPORTED_SOURCES:
        return run_source
    raise PriceReviewError("Unable to determine enriched CSV source.")


def _rows_by_model(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        model = _text(_value_by_case(row, "model"))
        if model and model not in result:
            result[model] = row
    return result


def _observations_by_key(observations: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for observation in sorted(observations, key=_observation_priority_key):
        value = _text(observation.get(key))
        if value and value not in result:
            result[value] = observation
    return result


def _observation_priority_key(observation: dict[str, Any]) -> tuple[int, Decimal]:
    price = _parse_decimal(observation.get("competitor_price"))
    if price is None or price <= 0:
        return (1, Decimal("0"))
    return (0, price)


def _source_from_observations(observations: list[dict[str, Any]]) -> str:
    for observation in observations:
        source = _text(observation.get("source")).lower()
        if source:
            return source
    return ""


def _observation_to_enriched_row(observation: dict[str, Any], *, source: str) -> dict[str, str]:
    raw = observation.get("raw_observation")
    row = {str(key): _text(value) for key, value in raw.items()} if isinstance(raw, dict) else {}
    resolved_source = _text(observation.get("source")).lower() or source
    competitor_price = _text(observation.get("competitor_price"))
    product_url = _text(observation.get("product_url"))
    competitor_name = _text(observation.get("competitor_name")) or _text(observation.get("seller_name"))
    row.update(
        {
            "model": _text(observation.get("model")) or row.get("model", ""),
            "mpn": _text(observation.get("mpn")) or row.get("mpn", ""),
            "name": _text(observation.get("product_name")) or row.get("name", ""),
            "source": resolved_source,
            "current_price": _text(observation.get("own_price")) or row.get("current_price", ""),
            "competitor_price": competitor_price or row.get("competitor_price", ""),
            "price_found": competitor_price or row.get("price_found", ""),
            "competitor_store": competitor_name or row.get("competitor_store", ""),
            "store": competitor_name or row.get("store", ""),
            "competitor_url": product_url or row.get("competitor_url", ""),
            "url": product_url or row.get("url", ""),
            "price_delta": _text(observation.get("price_delta")) or row.get("price_delta", ""),
            "price_delta_percent": _text(observation.get("price_delta_percent")) or row.get("price_delta_percent", ""),
        }
    )
    if resolved_source:
        row[f"{resolved_source}_price"] = competitor_price or row.get(f"{resolved_source}_price", "")
        row[f"{resolved_source}_url"] = product_url or row.get(f"{resolved_source}_url", "")
    if resolved_source == "bestprice":
        row["bestprice_best_store"] = competitor_name or row.get("bestprice_best_store", "")
        row["bestprice_best_store_price"] = competitor_price or row.get("bestprice_best_store_price", "")
    return row


def _competitor_price(row: dict[str, str], source: str) -> Decimal | None:
    if source == "bestprice":
        return _first_decimal(
            row,
            (
                "bestprice_price",
                "bestprice_best_store_price",
                "competitor_price",
                "price_found",
                "target_price",
                "bestprice_next_store_price",
            ),
        )
    return _first_decimal(row, ("skroutz_price", "competitor_price", "price_found", "target_price"))


def _competitor_store(row: dict[str, str], source: str) -> str:
    if source == "bestprice":
        return _first_present(row, ("bestprice_best_store", "competitor_store", "bestprice_next_store"))
    return _first_present(row, ("competitor_store", "store"))


def _competitor_url(row: dict[str, str], source: str) -> str:
    if source == "bestprice":
        return _first_present(row, ("bestprice_url", "competitor_url", "url"))
    return _first_present(row, ("skroutz_url", "competitor_url", "url"))


def _recommended_action(current_price: Decimal | None, competitor_price: Decimal | None) -> str:
    if competitor_price is None or competitor_price <= 0:
        return "ignore"
    if current_price is None or current_price <= competitor_price:
        return "ignore"
    return "match_price"


def _review_summary(rows: list[PriceReviewRow], *, actions_count: int) -> dict[str, int]:
    return {
        "actions_count": actions_count,
        "exportable_count": sum(1 for row in rows if row.status == "exportable"),
        "ignored_count": sum(1 for row in rows if row.status == "ignored"),
        "not_exportable_count": sum(1 for row in rows if row.status == "not_exportable"),
    }


def _source_from_rows(rows: list[PriceReviewRow]) -> str:
    return rows[0].source if rows else ""


def _action_to_json(action: PriceActionInput) -> dict[str, Any]:
    return {
        "model": action.model,
        "selected_action": action.selected_action,
        "undercut_amount": _decimal_to_float(action.undercut_amount),
        "reason": action.reason,
    }


def _first_decimal(row: dict[str, str], columns: tuple[str, ...]) -> Decimal | None:
    return _parse_decimal(_first_present(row, columns))


def _first_present(row: dict[str, str], columns: tuple[str, ...]) -> str:
    for column in columns:
        value = _text(_value_by_case(row, column))
        if value:
            return value
    return ""


def _value_by_case(row: dict[str, str], column: str) -> str:
    for key, value in row.items():
        if key is not None and key.strip().casefold() == column.casefold():
            return value
    return ""


def _parse_decimal(value: object) -> Decimal | None:
    text = _text(value)
    if not text:
        return None
    cleaned = text.replace("€", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _money_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{_round_money(value):.2f}"


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{_round_money(value):.2f}"


def _decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(_round_money(value))


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
