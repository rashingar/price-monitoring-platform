from __future__ import annotations

import pytest

from pipeline.api.schemas import HealthResponse


def test_health_response_schema_defaults_to_ok() -> None:
    assert HealthResponse().model_dump() == {"status": "ok"}


def test_health_endpoint_returns_ok() -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from pipeline.api.app import create_app

    client = fastapi_testclient.TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
