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
PRICE_EQUALITY_TOLERANCE = Decimal("0.05")

GENERIC_LISTING_COLLECTION_KEYS = {
    "offers",
    "shops",
    "stores",
    "listings",
    "product_cards",
    "results",
    "items",
    "cards",
}
STORE_ALIASES = ("store", "shop", "shop_name", "seller", "seller_name", "merchant", "name")
PRICE_ALIASES = ("price", "final_price", "sale_price", "competitor_price", "price_found", "best_store_price")
URL_ALIASES = ("url", "product_url", "shop_url", "seller_url", "store_url", "href")


class PriceReviewError(ValueError):
    """Raised for malformed review input or invalid manual actions."""


@dataclass(frozen=True)
class TopListing:
    rank: int
    store: str
    price: Decimal
    url: str
    source: str
    raw_source: str = ""
    evidence_source: str = ""

    def to_api_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "rank": self.rank,
            "store": self.store,
            "price": _decimal_to_float(self.price),
            "url": self.url,
            "source": self.source,
        }
        if self.raw_source:
            payload["raw_source"] = self.raw_source
        if self.evidence_source:
            payload["evidence_source"] = self.evidence_source
        return payload


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
    competitor_rank: int | None = None
    next_competitor_price: Decimal | None = None
    next_competitor_store: str = ""
    next_competitor_url: str = ""
    next_store_delta: Decimal | None = None
    next_store_delta_percent: Decimal | None = None
    top_listings: list[TopListing] | None = None
    delta_basis: str | None = None

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
            "competitor_rank": self.competitor_rank,
            "next_competitor_price": _decimal_to_float(self.next_competitor_price),
            "next_competitor_store": self.next_competitor_store,
            "next_competitor_url": self.next_competitor_url,
            "next_store_delta": _decimal_to_float(self.next_store_delta),
            "next_store_delta_percent": _decimal_to_float(self.next_store_delta_percent),
            "top_listings": [listing.to_api_dict() for listing in self.top_listings or []],
            "delta_basis": self.delta_basis,
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
    observations_grouped_by_model = _observations_grouped_by_key(observations, "model")
    observations_grouped_by_mpn = _observations_grouped_by_key(observations, "mpn")
    rows: list[PriceReviewRow] = []

    for index, input_row in enumerate(input_rows):
        model = _text(input_row.get("model"))
        mpn = _text(input_row.get("mpn"))
        product_observations = observations_grouped_by_model.get(model) or observations_grouped_by_mpn.get(mpn) or []
        top_listings = _top_listings_from_observations(product_observations, fallback_source=source)
        observation = observations_by_model.get(model) or observations_by_mpn.get(mpn)
        enriched_observation = _observation_from_listing(observation or {}, top_listings[0]) if top_listings else observation
        enriched_row = _observation_to_enriched_row(enriched_observation or {}, source=source)
        input_with_observed_price = dict(input_row)
        if not _text(input_with_observed_price.get("price")):
            input_with_observed_price["price"] = _text(enriched_row.get("current_price"))
        rows.append(
            _build_review_row(
                input_with_observed_price,
                enriched_row,
                _text(enriched_row.get("source")) or source,
                top_listings=top_listings,
            )
        )
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


def _build_review_row(
    input_row: dict[str, str],
    enriched_row: dict[str, str],
    source: str,
    *,
    top_listings: list[TopListing] | None = None,
) -> PriceReviewRow:
    model = _text(input_row.get("model"))
    mpn = _text(input_row.get("mpn"))
    name = _text(input_row.get("name"))
    current_price = _parse_decimal(_first_present(input_row, ("current_price", "price")))
    listings = list(top_listings or [])
    best_listing = listings[0] if listings else None
    next_listing = listings[1] if len(listings) > 1 else None
    competitor_price = best_listing.price if best_listing else _competitor_price(enriched_row, source)
    competitor_store = best_listing.store if best_listing else _competitor_store(enriched_row, source)
    competitor_url = best_listing.url if best_listing else _competitor_url(enriched_row, source)
    warnings: list[str] = []

    if not is_atomic_model(model):
        warnings.append("composite_or_invalid_model")
    if current_price is None or current_price <= 0:
        warnings.append("missing_or_invalid_current_price")
    if competitor_price is None or competitor_price <= 0:
        warnings.append("missing_or_invalid_competitor_price")

    price_delta: Decimal | None = None
    price_delta_percent: Decimal | None = None
    delta_basis: str | None = None
    next_store_delta: Decimal | None = None
    next_store_delta_percent: Decimal | None = None
    if current_price is not None and current_price > 0 and competitor_price is not None and competitor_price > 0:
        delta_competitor_price = competitor_price
        delta_basis = "best_competitor"
        if best_listing is not None and next_listing is not None and prices_nearly_equal(current_price, best_listing.price):
            delta_competitor_price = next_listing.price
            delta_basis = "next_store"
        price_delta = current_price - delta_competitor_price
        price_delta_percent = (price_delta / current_price) * Decimal("100")
        if delta_basis == "next_store":
            next_store_delta = price_delta
            next_store_delta_percent = price_delta_percent

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
        competitor_rank=best_listing.rank if best_listing else None,
        next_competitor_price=next_listing.price if next_listing else None,
        next_competitor_store=next_listing.store if next_listing else "",
        next_competitor_url=next_listing.url if next_listing else "",
        next_store_delta=next_store_delta,
        next_store_delta_percent=next_store_delta_percent,
        top_listings=listings,
        delta_basis=delta_basis,
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


def _observations_grouped_by_key(observations: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for observation in sorted(observations, key=_observation_priority_key):
        value = _text(observation.get(key))
        if value:
            result.setdefault(value, []).append(observation)
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
    competitor_url = _text(row.get("bestprice_best_store_url")) if resolved_source == "bestprice" else ""
    competitor_url = competitor_url or product_url
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
            "competitor_url": competitor_url or row.get("competitor_url", ""),
            "url": competitor_url or row.get("url", ""),
            "price_delta": _text(observation.get("price_delta")) or row.get("price_delta", ""),
            "price_delta_percent": _text(observation.get("price_delta_percent")) or row.get("price_delta_percent", ""),
        }
    )
    if resolved_source:
        row[f"{resolved_source}_price"] = competitor_price or row.get(f"{resolved_source}_price", "")
        row[f"{resolved_source}_url"] = competitor_url or row.get(f"{resolved_source}_url", "")
    if resolved_source == "bestprice":
        row["bestprice_best_store"] = competitor_name or row.get("bestprice_best_store", "")
        row["bestprice_best_store_price"] = competitor_price or row.get("bestprice_best_store_price", "")
    return row


def _observation_from_listing(observation: dict[str, Any], listing: TopListing) -> dict[str, Any]:
    enriched = dict(observation)
    enriched["competitor_name"] = listing.store
    enriched["seller_name"] = listing.store
    enriched["competitor_price"] = _money_text(listing.price)
    enriched["product_url"] = listing.url or _text(observation.get("product_url"))
    enriched["source"] = listing.source or _text(observation.get("source"))
    return enriched


def _top_listings_from_observations(observations: list[dict[str, Any]], *, fallback_source: str) -> list[TopListing]:
    candidates: list[TopListing] = []
    for observation in observations:
        candidates.extend(_listing_from_normalized_observation(observation, fallback_source=fallback_source))
    if len(_dedupe_and_rank_listings(candidates)) < 2:
        for observation in observations:
            source = _text(observation.get("source")).lower() or fallback_source
            raw = _raw_payload(observation.get("raw_observation"))
            if raw is None:
                continue
            if source == "skroutz":
                candidates.extend(_extract_skroutz_raw_listings(raw, source=source))
            elif source == "bestprice":
                candidates.extend(_extract_bestprice_raw_listings(raw, source=source))
            candidates.extend(_extract_generic_raw_listings(raw, source=source or fallback_source))
    return _dedupe_and_rank_listings(candidates)[:3]


def _listing_from_normalized_observation(observation: dict[str, Any], *, fallback_source: str) -> list[TopListing]:
    price = _parse_decimal(observation.get("competitor_price"))
    if price is None or price <= 0:
        return []
    source = _text(observation.get("source")).lower() or fallback_source
    store = _text(observation.get("competitor_name")) or _text(observation.get("seller_name"))
    url = _text(observation.get("product_url"))
    raw = _raw_payload(observation.get("raw_observation"))
    if isinstance(raw, dict):
        if source == "bestprice":
            url = _text(raw.get("bestprice_best_store_url")) or url
        if not store:
            store = _first_present_any(raw, STORE_ALIASES)
        if not url:
            url = _first_present_any(raw, URL_ALIASES)
    return [
        TopListing(
            rank=0,
            store=store,
            price=price,
            url=url,
            source=source,
            raw_source="db_observation",
            evidence_source="normalized",
        )
    ]


def _extract_skroutz_raw_listings(raw: object, *, source: str) -> list[TopListing]:
    return _extract_from_collections(
        raw,
        collection_keys=("product_cards", "offers", "shops"),
        source=source,
        evidence_source="skroutz_raw",
        store_aliases=("shop", "seller", "seller_name", "shop_name", "store", "name"),
        price_aliases=("price", "final_price", "competitor_price", "price_found"),
        url_aliases=("url", "seller_url", "shop_url", "product_url", "href"),
    )


def _extract_bestprice_raw_listings(raw: object, *, source: str) -> list[TopListing]:
    candidates: list[TopListing] = []
    if isinstance(raw, dict):
        candidates.extend(
            [
                item
                for item in (
                    _listing_from_values(
                        store=raw.get("bestprice_best_store"),
                        price=raw.get("bestprice_best_store_price"),
                        url=raw.get("bestprice_best_store_url"),
                        source=source,
                        raw_source="bestprice_best_store",
                        evidence_source="bestprice_raw",
                    ),
                    _listing_from_values(
                        store=raw.get("bestprice_next_store"),
                        price=raw.get("bestprice_next_store_price"),
                        url=raw.get("bestprice_next_store_url"),
                        source=source,
                        raw_source="bestprice_next_store",
                        evidence_source="bestprice_raw",
                    ),
                )
                if item is not None
            ]
        )
    candidates.extend(
        _extract_from_collections(
            raw,
            collection_keys=("stores", "shops", "offers"),
            source=source,
            evidence_source="bestprice_raw",
            store_aliases=("merchant", "seller", "store", "shop", "shop_name", "seller_name", "name"),
            price_aliases=("price", "final_price", "sale_price", "competitor_price", "best_store_price"),
            url_aliases=("url", "product_url", "shop_url", "seller_url", "store_url", "href"),
        )
    )
    return candidates


def _extract_generic_raw_listings(raw: object, *, source: str) -> list[TopListing]:
    return _extract_from_collections(
        raw,
        collection_keys=tuple(GENERIC_LISTING_COLLECTION_KEYS),
        source=source,
        evidence_source="generic_raw",
        store_aliases=STORE_ALIASES,
        price_aliases=PRICE_ALIASES,
        url_aliases=URL_ALIASES,
    )


def _extract_from_collections(
    raw: object,
    *,
    collection_keys: tuple[str, ...],
    source: str,
    evidence_source: str,
    store_aliases: tuple[str, ...],
    price_aliases: tuple[str, ...],
    url_aliases: tuple[str, ...],
) -> list[TopListing]:
    candidates: list[TopListing] = []
    for item, raw_source in _iter_listing_candidates(raw, collection_keys=collection_keys):
        if not isinstance(item, dict):
            continue
        listing = _listing_from_values(
            store=_first_present_any(item, store_aliases),
            price=_first_present_any(item, price_aliases),
            url=_first_present_any(item, url_aliases),
            source=source,
            raw_source=raw_source,
            evidence_source=evidence_source,
        )
        if listing is not None:
            candidates.append(listing)
    return candidates


def _iter_listing_candidates(raw: object, *, collection_keys: tuple[str, ...], prefix: str = "raw") -> list[tuple[object, str]]:
    candidates: list[tuple[object, str]] = []
    if isinstance(raw, list):
        for index, item in enumerate(raw):
            candidates.append((item, f"{prefix}[{index}]"))
            candidates.extend(_iter_listing_candidates(item, collection_keys=collection_keys, prefix=f"{prefix}[{index}]"))
        return candidates
    if not isinstance(raw, dict):
        return candidates
    candidates.append((raw, prefix))
    collection_key_set = {key.casefold() for key in collection_keys}
    for key, value in raw.items():
        key_text = str(key)
        if key_text.casefold() in collection_key_set:
            if isinstance(value, list):
                for index, item in enumerate(value):
                    candidates.append((item, f"{prefix}.{key_text}[{index}]"))
                    candidates.extend(
                        _iter_listing_candidates(item, collection_keys=collection_keys, prefix=f"{prefix}.{key_text}[{index}]")
                    )
            elif isinstance(value, dict):
                candidates.append((value, f"{prefix}.{key_text}"))
                candidates.extend(_iter_listing_candidates(value, collection_keys=collection_keys, prefix=f"{prefix}.{key_text}"))
        elif isinstance(value, (dict, list)):
            candidates.extend(_iter_listing_candidates(value, collection_keys=collection_keys, prefix=f"{prefix}.{key_text}"))
    return candidates


def _listing_from_values(
    *,
    store: object,
    price: object,
    url: object,
    source: str,
    raw_source: str,
    evidence_source: str,
) -> TopListing | None:
    parsed_price = _parse_decimal(price)
    if parsed_price is None or parsed_price <= 0:
        return None
    return TopListing(
        rank=0,
        store=_text(store),
        price=parsed_price,
        url=_text(url),
        source=_text(source),
        raw_source=raw_source,
        evidence_source=evidence_source,
    )


def _dedupe_and_rank_listings(listings: list[TopListing]) -> list[TopListing]:
    deduped: dict[tuple[str, str, str], TopListing] = {}
    for listing in listings:
        if listing.price <= 0:
            continue
        key = (listing.store.casefold(), _money_text(listing.price), listing.url.casefold())
        if key not in deduped:
            deduped[key] = listing
    ranked: list[TopListing] = []
    for index, listing in enumerate(sorted(deduped.values(), key=lambda item: (item.price, item.store.casefold(), item.url)), start=1):
        ranked.append(
            TopListing(
                rank=index,
                store=listing.store,
                price=listing.price,
                url=listing.url,
                source=listing.source,
                raw_source=listing.raw_source,
                evidence_source=listing.evidence_source,
            )
        )
    return ranked


def _raw_payload(value: object) -> object | None:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, (dict, list)) else None
    return None


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


def _first_present_any(row: dict[str, Any], columns: tuple[str, ...]) -> str:
    for column in columns:
        value = _text(_value_by_case_any(row, column))
        if value:
            return value
    return ""


def _value_by_case(row: dict[str, str], column: str) -> str:
    for key, value in row.items():
        if key is not None and key.strip().casefold() == column.casefold():
            return value
    return ""


def _value_by_case_any(row: dict[str, Any], column: str) -> object:
    for key, value in row.items():
        if key is not None and str(key).strip().casefold() == column.casefold():
            return value
    return ""


def prices_nearly_equal(a: Decimal | None, b: Decimal | None) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= PRICE_EQUALITY_TOLERANCE


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
