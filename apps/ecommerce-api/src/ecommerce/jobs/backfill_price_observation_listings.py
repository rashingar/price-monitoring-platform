"""Backfill normalized listing rows from legacy offer observations."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from ecommerce.db.repositories import backfill_price_observation_listings_from_offer_observations
from ecommerce.db.session import session_scope
from ecommerce.env import load_local_env_if_present


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None, help="Optional Price Monitoring run id to backfill.")
    args = parser.parse_args(argv)

    load_local_env_if_present()
    with session_scope() as session:
        inserted = backfill_price_observation_listings_from_offer_observations(session, run_id=args.run_id)
    print(f"price_observation_listings inserted: {inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
