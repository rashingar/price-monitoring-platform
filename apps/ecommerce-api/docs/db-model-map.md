# Ecommerce DB Model Map

Ecommerce SQLAlchemy declarations live under `src/ecommerce/db/models/`. The
package is split by workflow ownership so new tables have an obvious home and
application imports can point at the workflow they use.

## Package Structure

- `models/base.py`: shared `Base` and `JSON_DOCUMENT`.
- `models/catalog.py`: catalog import and catalog browsing rows.
- `models/source_urls.py`: source URL lifecycle, discovery runs, discovery tasks, and candidate review rows.
- `models/vendor_sources.py`: vendor records and Vendor Sources capture run history.
- `models/jobs.py`: durable Ecommerce background jobs.
- `models/products.py`: products, product sources, and source capture snapshots.
- `models/price_monitoring.py`: Price Monitoring runs, catalog snapshots, observations, listings, and review persistence owned by Price Monitoring.
- `models/alerts.py`: alert rules, alert events, and alert-owned state.

## Import Policy

Application code should import model classes from the workflow module that owns
them:

```python
from ecommerce.db.models.source_urls import SourceUrl
from ecommerce.db.models.jobs import EcommerceJob
from ecommerce.db.models.price_monitoring import MonitoringRun, PriceObservation
```

`ecommerce.db.models.__init__` exists only to register all model modules for
metadata consumers. It does not re-export `Base`, `JSON_DOCUMENT`, or model
classes. Do not add application imports from `ecommerce.db.models` for model
classes.

## Alembic Metadata Loading

Alembic should import `Base` from `ecommerce.db.models.base` and import
`ecommerce.db.models` for side-effect registration before `Base.metadata` is
read, so autogeneration and migration checks see all declared tables:

```python
import ecommerce.db.models as _model_registration  # noqa: F401
from ecommerce.db.models.base import Base

target_metadata = Base.metadata
```

Direct imports from `ecommerce.db.models.base` are for model modules that need
the shared declarative base without triggering package registration, and for
tests that explicitly import the model submodules required by their schema
setup. Use the package loader when a caller needs full metadata registration.

## Ownership Rules

Choose the destination module by the workflow that owns the table's lifecycle:

- Catalog import/catalog browsing tables -> `models/catalog.py`.
- Source URL lifecycle/discovery/review -> `models/source_urls.py`.
- Vendor source capture/run history -> `models/vendor_sources.py`.
- Durable background jobs -> `models/jobs.py`.
- Product/product source/source snapshots -> `models/products.py`.
- Price Monitoring runs/observations/listings/review -> `models/price_monitoring.py`.
- Alerts/rules/events -> `models/alerts.py`.

If a table is referenced by several workflows, place it with the workflow that
creates and mutates the row as its durable state. Other workflows should import
that model from the owning module rather than moving the declaration.

Repository ownership follows the same workflow map; see `db-repository-map.md`.
