"""FastAPI app for local Ecommerce API endpoints."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from fastapi import FastAPI

from ecommerce.env import load_local_env_if_present

load_local_env_if_present()

from ecommerce.api.routes_artifacts import router as artifacts_router
from ecommerce.api.routes_catalog import router as catalog_router
from ecommerce.api.routes_catalog_update import router as catalog_update_router
from ecommerce.api.routes_files import router as files_router
from ecommerce.api.routes_health import router as health_router
from ecommerce.api.routes_ignore import router as ignore_router
from ecommerce.api.routes_jobs import router as jobs_router
from ecommerce.api.routes_paths import router as paths_router
from ecommerce.api.routes_price_alerts import router as price_alerts_router
from ecommerce.api.routes_price_monitoring import router as price_monitoring_router
from ecommerce.api.routes_platform_health import router as platform_health_router
from ecommerce.api.routes_product_factory_telegram import router as product_factory_telegram_router
from ecommerce.api.routes_product_sources import router as product_sources_router
from ecommerce.api.routes_source_url_agent import router as source_url_agent_router
from ecommerce.api.routes_source_url_import import router as source_url_import_router
from ecommerce.api.routes_source_urls import router as source_urls_router
from ecommerce.api.routes_stock_sync import router as stock_sync_router
from ecommerce.api.routes_vendor_sources import router as vendor_sources_router


def create_app() -> FastAPI:
    app = FastAPI(title="Ecommerce API")
    app.include_router(health_router)
    app.include_router(catalog_router)
    app.include_router(catalog_update_router)
    app.include_router(ignore_router)
    app.include_router(files_router)
    app.include_router(paths_router)
    app.include_router(jobs_router)
    app.include_router(platform_health_router)
    app.include_router(price_monitoring_router)
    app.include_router(price_alerts_router)
    app.include_router(product_factory_telegram_router)
    app.include_router(product_sources_router)
    app.include_router(source_url_agent_router)
    app.include_router(vendor_sources_router)
    app.include_router(source_url_import_router)
    app.include_router(source_urls_router)
    app.include_router(stock_sync_router)
    app.include_router(artifacts_router)
    return app


app = create_app()


def main(argv: Sequence[str] | None = None) -> None:
    from ecommerce.dev.start import main as dev_start_main

    dev_start_main(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
