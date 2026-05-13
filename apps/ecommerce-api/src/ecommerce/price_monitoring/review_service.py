"""Price Monitoring review workflow helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ecommerce.artifacts import artifact_link_payload
from ecommerce.price_monitoring.export import export_price_update_csv
from ecommerce.price_monitoring.persistence import backfill_run_listing_evidence
from ecommerce.price_monitoring.review import (
    PriceActionInput,
    apply_price_actions_to_rows,
    load_price_review_rows,
    load_price_review_rows_from_observations,
    load_review_csv,
    summarize_review_rows,
)


def get_review_response(
    run_id: str,
    run_dir: Path,
    enriched_path: Path | None,
    *,
    include_all_listings: bool,
    session_scope_fn: Callable,
    list_price_observations_fn: Callable,
    list_price_observation_listings_fn: Callable,
) -> dict:
    rows, warnings = load_price_review_rows_for_route(
        run_id,
        run_dir,
        enriched_path,
        include_all_listings=include_all_listings,
        session_scope_fn=session_scope_fn,
        list_price_observations_fn=list_price_observations_fn,
        list_price_observation_listings_fn=list_price_observation_listings_fn,
    )
    return {
        "run_id": run_id,
        "items": [row.to_api_dict() for row in rows],
        "summary": summarize_review_rows(rows),
        "warnings": warnings,
    }


def apply_review_actions_response(
    run_id: str,
    run_dir: Path,
    enriched_path: Path | None,
    actions: list[PriceActionInput],
    *,
    session_scope_fn: Callable,
    list_price_observations_fn: Callable,
    list_price_observation_listings_fn: Callable,
) -> dict:
    rows, _warnings = load_price_review_rows_for_route(
        run_id,
        run_dir,
        enriched_path,
        include_all_listings=False,
        session_scope_fn=session_scope_fn,
        list_price_observations_fn=list_price_observations_fn,
        list_price_observation_listings_fn=list_price_observation_listings_fn,
    )
    result = apply_price_actions_to_rows(run_dir, rows, actions)
    return {
        "run_id": run_id,
        "status": "review_actions_applied",
        "review_csv_path": str(result.review_csv_path),
        "review_actions_path": str(result.review_actions_path),
        "artifacts": [
            artifact_link_payload(result.review_csv_path),
            artifact_link_payload(result.review_actions_path),
        ],
        "summary": result.summary,
    }


def export_price_update_response(
    run_id: str,
    run_dir: Path,
    review_csv_path: Path,
    output_path: Path | None,
) -> dict:
    rows = load_review_csv(review_csv_path)
    result = export_price_update_csv(run_dir, rows, output_path)
    return {
        "run_id": run_id,
        "status": "price_update_exported",
        "output_path": str(result.output_path),
        "artifact": artifact_link_payload(result.output_path),
        "rows_exported": result.rows_exported,
        "columns": result.columns,
    }


def backfill_listing_response(run_id: str) -> dict:
    result = backfill_run_listing_evidence(run_id)
    return {
        "run_id": run_id,
        "status": "listings_backfilled",
        "inserted_count": result.inserted_count,
        "listing_count": result.listing_count,
    }


def load_price_review_rows_for_route(
    run_id: str,
    run_dir: Path,
    enriched_path: Path | None,
    *,
    include_all_listings: bool = False,
    session_scope_fn: Callable,
    list_price_observations_fn: Callable,
    list_price_observation_listings_fn: Callable,
):
    try:
        return load_price_review_rows(run_dir, enriched_path), []
    except FileNotFoundError:
        if enriched_path is not None:
            raise
        return load_price_review_rows_from_db_observations(
            run_id,
            run_dir,
            include_all_listings=include_all_listings,
            session_scope_fn=session_scope_fn,
            list_price_observations_fn=list_price_observations_fn,
            list_price_observation_listings_fn=list_price_observation_listings_fn,
        )


def load_price_review_rows_from_db_observations(
    run_id: str,
    run_dir: Path,
    *,
    include_all_listings: bool = False,
    session_scope_fn: Callable,
    list_price_observations_fn: Callable,
    list_price_observation_listings_fn: Callable,
):
    warnings: list[str] = []
    with session_scope_fn() as session:
        observations, count = list_price_observations_fn(
            session,
            run_id=run_id,
            include_unmatched=True,
            limit=5000,
        )
        if hasattr(session, "execute") and observations:
            observation_ids = [int(item["id"]) for item in observations if item.get("id") is not None]
            listings = list_price_observation_listings_fn(
                session,
                price_observation_ids=observation_ids,
                limit=20_000,
            )
            attach_price_observation_listings(observations, listings)
            if review_listing_backfill_needed(observations, listings):
                warnings.append(
                    "Persisted listing rows are missing for this run. "
                    f"POST /api/price-monitoring/runs/{run_id}/backfill-listings to attach listing evidence, then reload review."
                )
    if count <= 0 or not observations:
        raise FileNotFoundError(
            f"Enriched CSV not found in run folder and no persisted price observations found for run: {run_id}"
        )
    return load_price_review_rows_from_observations(run_dir, observations, include_all_listings=include_all_listings), warnings


def review_listing_backfill_needed(observations: list[dict], listings: list[dict]) -> bool:
    listed_observation_ids = {
        int(listing["price_observation_id"])
        for listing in listings
        if listing.get("price_observation_id") is not None
    }
    for observation in observations:
        observation_id = observation.get("id")
        if observation_id is None:
            continue
        if observation.get("source_capture_snapshot_id") is not None and int(observation_id) not in listed_observation_ids:
            return True
    return False


def attach_price_observation_listings(observations: list[dict], listings: list[dict]) -> None:
    by_observation_id: dict[int, list[dict]] = {}
    for listing in listings:
        observation_id = listing.get("price_observation_id")
        if observation_id is None:
            continue
        by_observation_id.setdefault(int(observation_id), []).append(listing)
    for observation in observations:
        observation_id = observation.get("id")
        if observation_id is None:
            continue
        observation["price_observation_listings"] = by_observation_id.get(int(observation_id), [])
