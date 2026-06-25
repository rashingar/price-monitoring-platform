from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from product_factory.local_env import load_local_env_if_present

load_local_env_if_present()

from product_factory.jobs.runner import SequentialJobRunner
from product_factory.jobs.recovery import reconcile_persisted_jobs
from product_factory.jobs.store import JobStore
from .routes_filter_review import router as filter_review_router
from .routes_filters import router as filters_router
from .routes_health import router as health_router
from .routes_jobs import router as jobs_router
from .routes_authoring import router as authoring_router
from .routes_settings import router as settings_router


def create_app(
    *,
    job_store: JobStore | None = None,
    job_runner: SequentialJobRunner | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        reconcile_persisted_jobs(app.state.job_store, app.state.job_runner)
        try:
            yield
        finally:
            app.state.job_runner.stop()

    app = FastAPI(title="Product Factory Local Jobs API", lifespan=lifespan)
    app.state.job_store = job_store or JobStore()
    app.state.job_runner = job_runner or SequentialJobRunner(app.state.job_store)
    app.include_router(health_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(filters_router, prefix="/api")
    app.include_router(filter_review_router, prefix="/api")
    app.include_router(authoring_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    return app


app = create_app()
