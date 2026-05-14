# Ecommerce DB Repository Map

Ecommerce DB query and persistence helpers live under
`src/ecommerce/db/repositories/`. The package follows the same workflow
ownership rules as the DB model package.

## Package Structure

- `repositories/catalog.py`: catalog repository namespace. Catalog import and browsing helpers currently remain in `ecommerce.catalog_db` until that workflow is moved.
- `repositories/source_urls.py`: source URL lifecycle, import, validation, discovery, and review persistence.
- `repositories/vendor_sources.py`: Vendor Sources capture run history persistence.
- `repositories/jobs.py`: durable background job row creation, lookup, leasing, status transitions, and serialization.
- `repositories/products.py`: products, product sources, product source serialization, and source-created product helpers.
- `repositories/price_monitoring.py`: Price Monitoring runs, catalog snapshots, observations, listings, history queries, and listing backfill.
- `repositories/alerts.py`: alert rules, alert events, alert status transitions, and alert serialization.
- `repositories/capture_persistence.py`: capture result persistence that writes source snapshots, observations, offers, listings, and source health.
- `repositories/source_convergence.py`: bridge helpers that mirror accepted `source_urls` into `product_sources` and product sources back into source URLs.
- `repositories/common.py`: shared serialization and scalar parsing helpers used by repository modules.

## Import Policy

New code should import from the workflow-owned module:

```python
from ecommerce.db.repositories.source_urls import get_source_url
from ecommerce.db.repositories.price_monitoring import get_monitoring_run
from ecommerce.db.repositories.jobs import create_queued_job
```

`ecommerce.db.repositories` remains a compatibility barrel for older imports.
Do not add new application imports from the barrel unless a compatibility path
is explicitly needed.

## Layering Rules

Repositories contain DB query and persistence mechanics: SQLAlchemy statements,
row creation, row updates, status transitions, and serialization of DB rows into
existing response dictionaries.

Services orchestrate workflows and compose repositories. They should decide
when persistence happens, how artifacts are read, and how workflow steps are
sequenced.

API routes should stay thin HTTP adapters. They should validate HTTP inputs,
translate exceptions into HTTP responses, and call services or repositories
without owning workflow logic.

## Bridge Modules

`source_convergence.py` and `capture_persistence.py` intentionally bridge
multiple workflow-owned models:

- Source convergence keeps `source_urls` and `product_sources` aligned without
moving ownership of either table.
- Capture persistence writes product source snapshots, Price Monitoring
observations, offer listings, and source health as one capture transaction.

Keep bridge modules small and explicit. If a helper only reads or writes one
workflow's state, place it in that workflow's repository module instead.

## Ownership Rules

- Catalog import/catalog browsing persistence -> `repositories/catalog.py` or `ecommerce.catalog_db` until moved.
- Source URL lifecycle/import/discovery/review -> `repositories/source_urls.py`.
- Vendor source capture/run history -> `repositories/vendor_sources.py`.
- Durable background jobs -> `repositories/jobs.py`.
- Product/product source/source snapshots -> `repositories/products.py`.
- Price Monitoring runs/observations/listings/review -> `repositories/price_monitoring.py`.
- Alerts/rules/events -> `repositories/alerts.py`.
- Capture result persistence helpers -> `repositories/capture_persistence.py`.
- Source URL/product source convergence helpers -> `repositories/source_convergence.py`.
