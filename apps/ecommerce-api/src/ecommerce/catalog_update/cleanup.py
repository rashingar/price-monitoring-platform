"""Catalog-owned cleanup for excluded models."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select, update

from ecommerce.catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.catalog_update.types import CatalogExclusionCleanupResult, CatalogUpdateError
from ecommerce.db.config import sanitize_database_error
from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.products import Product, ProductSource
from ecommerce.db.models.source_urls import SourceUrl, SourceUrlCandidate, SourceUrlDiscoveryTask
from ecommerce.db.session import session_scope


def purge_excluded_catalog_state(
    excluded_models: frozenset[str] | set[str],
    *,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
) -> CatalogExclusionCleanupResult:
    models = frozenset(str(item).strip() for item in excluded_models if str(item).strip())
    if not models:
        return CatalogExclusionCleanupResult()

    purged_catalog_products = 0
    purged_source_urls = 0
    purged_source_url_discovery_tasks = 0
    purged_source_url_candidates = 0
    purged_product_sources = 0
    deactivated_products = 0

    try:
        with session_scope() as session:
            for batch in model_batches(models):
                product_ids = select(Product.id).where(Product.catalog_source == catalog_source, Product.model.in_(batch))
                purged_product_sources += rowcount(
                    session.execute(
                        delete(ProductSource)
                        .where(ProductSource.product_id.in_(product_ids))
                        .execution_options(synchronize_session=False)
                    )
                )

                purged_source_urls += rowcount(
                    session.execute(
                        delete(SourceUrl)
                        .where(SourceUrl.catalog_source == catalog_source, SourceUrl.model.in_(batch))
                        .execution_options(synchronize_session=False)
                    )
                )
                purged_source_url_candidates += rowcount(
                    session.execute(
                        delete(SourceUrlCandidate).where(
                            SourceUrlCandidate.catalog_source == catalog_source,
                            SourceUrlCandidate.model.in_(batch),
                        ).execution_options(synchronize_session=False)
                    )
                )
                purged_source_url_discovery_tasks += rowcount(
                    session.execute(
                        delete(SourceUrlDiscoveryTask)
                        .where(SourceUrlDiscoveryTask.model.in_(batch))
                        .execution_options(synchronize_session=False)
                    )
                )
                deactivated_products += rowcount(
                    session.execute(
                        update(Product)
                        .where(Product.catalog_source == catalog_source, Product.model.in_(batch), Product.active.is_(True))
                        .values(active=False)
                        .execution_options(synchronize_session=False)
                    )
                )
                purged_catalog_products += rowcount(
                    session.execute(
                        delete(CatalogProductRow).where(
                            CatalogProductRow.catalog_source == catalog_source,
                            CatalogProductRow.model.in_(batch),
                        ).execution_options(synchronize_session=False)
                    )
                )
    except Exception as exc:
        raise CatalogUpdateError(f"Catalog exclusion cleanup failed: {sanitize_database_error(exc)}") from exc

    return CatalogExclusionCleanupResult(
        purged_catalog_products=purged_catalog_products,
        purged_source_urls=purged_source_urls,
        purged_source_url_discovery_tasks=purged_source_url_discovery_tasks,
        purged_source_url_candidates=purged_source_url_candidates,
        purged_product_sources=purged_product_sources,
        deactivated_products=deactivated_products,
    )


def model_batches(models: frozenset[str] | set[str], size: int = 500) -> list[list[str]]:
    ordered = sorted(models)
    return [ordered[index : index + size] for index in range(0, len(ordered), size)]


def rowcount(result: Any) -> int:
    return int(result.rowcount or 0)
