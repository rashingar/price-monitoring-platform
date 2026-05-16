import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.platform_health import collectors as platform_health_collectors  # noqa: E402
from ecommerce.source_url_agent.brave_search import BRAVE_SEARCH_API_KEY_ENV_VAR  # noqa: E402


def _client(monkeypatch) -> TestClient:
    _install_ready_collectors(monkeypatch)
    return TestClient(create_app())


def _install_ready_collectors(monkeypatch) -> None:
    monkeypatch.setattr(platform_health_collectors, "collect_catalog_database_readiness", lambda: _catalog_ready())
    monkeypatch.setattr(platform_health_collectors, "collect_price_monitoring_database_readiness", lambda: _price_ready())
    monkeypatch.setattr(platform_health_collectors, "get_source_url_agent_readiness", lambda: _source_ready())
    monkeypatch.setattr(platform_health_collectors, "_latest_catalog_update_job", lambda: None)
    monkeypatch.setattr(platform_health_collectors, "_active_skroutz_source_url_count", lambda: 0)


def _set_opencart_config(monkeypatch, *, secret: str = "opencart-secret-value") -> None:
    monkeypatch.setenv("OPENCART_STORE_BASE", "https://shop.example")
    monkeypatch.setenv("OPENCART_ADMIN_PATH", "admin")
    monkeypatch.setenv("OPENCART_ADMIN_USER", "admin@example.test")
    monkeypatch.setenv("OPENCART_ADMIN_PASS", secret)


def _clear_product_factory_config(monkeypatch) -> None:
    monkeypatch.setenv("PRODUCT_FACTORY_API_BASE_URL", "")
    monkeypatch.setenv("VITE_API_PROXY_TARGET", "")


def _catalog_ready() -> dict:
    return {
        "configured": True,
        "reachable": True,
        "required_tables_present": True,
        "alembic_up_to_date": True,
        "ready_for_catalog": True,
        "ready_for_price_monitoring": True,
        "active_catalog_count": 12,
        "active_catalog_imported_at": "2026-05-15T10:00:00+00:00",
        "blocking_reasons": [],
        "warnings": [],
    }


def _price_ready() -> dict:
    return {
        **_catalog_ready(),
        "ready_for_price_monitoring": True,
    }


def _db_blocked() -> dict:
    return {
        "configured": False,
        "reachable": False,
        "required_tables_present": False,
        "alembic_up_to_date": None,
        "ready_for_catalog": False,
        "ready_for_price_monitoring": False,
        "active_catalog_count": None,
        "blocking_reasons": ["database_not_configured"],
        "warnings": [],
    }


def _source_ready():
    provider = SimpleNamespace(
        provider_name="brave_search",
        provider_type="brave",
        enabled=True,
        configured=True,
        missing_env_keys=[],
    )
    return SimpleNamespace(
        status="ready",
        providers=[provider],
        default_provider_order=["brave_search"],
        warnings=[],
        blocking_reasons=[],
    )


def _source_blocked():
    provider = SimpleNamespace(
        provider_name="brave_search",
        provider_type="brave",
        enabled=True,
        configured=False,
        missing_env_keys=[BRAVE_SEARCH_API_KEY_ENV_VAR],
    )
    return SimpleNamespace(
        status="blocked",
        providers=[provider],
        default_provider_order=["brave_search"],
        warnings=[],
        blocking_reasons=[
            "No enabled configured Source URL Agent search provider is available; "
            f"missing required environment keys: {BRAVE_SEARCH_API_KEY_ENV_VAR}."
        ],
    )


def _groups(payload: dict) -> dict[str, dict]:
    return {group["id"]: group for group in payload["groups"]}


def test_platform_health_returns_ecommerce_api_group(monkeypatch) -> None:
    _set_opencart_config(monkeypatch)
    _clear_product_factory_config(monkeypatch)
    response = _client(monkeypatch).get("/api/platform/health")

    assert response.status_code == 200
    group = _groups(response.json())["ecommerce_api"]
    assert group["status"] == "ready"
    assert group["summary"] == "Ecommerce API is responding."


def test_platform_health_source_url_agent_reflects_ready_and_blocked(monkeypatch) -> None:
    _set_opencart_config(monkeypatch)
    _clear_product_factory_config(monkeypatch)
    client = _client(monkeypatch)
    ready = _groups(client.get("/api/platform/health").json())["source_url_agent"]
    assert ready["status"] == "ready"

    monkeypatch.setattr(platform_health_collectors, "get_source_url_agent_readiness", lambda: _source_blocked())
    blocked_response = client.get("/api/platform/health")
    blocked = _groups(blocked_response.json())["source_url_agent"]
    assert blocked["status"] == "blocked"
    assert BRAVE_SEARCH_API_KEY_ENV_VAR in blocked["blocking_reasons"][0]
    assert blocked_response.json()["status"] == "blocked"


def test_platform_health_missing_opencart_config_returns_safe_key_names(monkeypatch) -> None:
    for key in platform_health_collectors.OPENCART_REQUIRED_KEYS:
        monkeypatch.delenv(key, raising=False)
    _clear_product_factory_config(monkeypatch)

    response = _client(monkeypatch).get("/api/platform/health")

    group = _groups(response.json())["catalog_update_opencart"]
    assert group["status"] == "blocked"
    assert sorted(reason.rsplit(": ", 1)[-1].rstrip(".") for reason in group["blocking_reasons"]) == sorted(
        platform_health_collectors.OPENCART_REQUIRED_KEYS
    )
    assert "OPENCART_ADMIN_PASS" in response.text


def test_platform_health_does_not_return_env_values_or_secrets(monkeypatch) -> None:
    secret = "do-not-leak-this-value"
    _set_opencart_config(monkeypatch, secret=secret)
    monkeypatch.setenv("PRODUCT_FACTORY_API_BASE_URL", f"http://user:{secret}@127.0.0.1:9")
    monkeypatch.setattr(platform_health_collectors, "get_source_url_agent_readiness", lambda: _source_ready())
    monkeypatch.setattr(
        platform_health_collectors.httpx,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    response = _client(monkeypatch).get("/api/platform/health")

    assert response.status_code == 200
    assert secret not in response.text
    assert f"user:{secret}" not in response.text
    assert "PRODUCT_FACTORY_API_BASE_URL" in response.text


def test_platform_health_product_factory_unconfigured_warns_without_crashing(monkeypatch) -> None:
    _set_opencart_config(monkeypatch)
    _clear_product_factory_config(monkeypatch)

    response = _client(monkeypatch).get("/api/platform/health")

    group = _groups(response.json())["product_factory_api"]
    assert group["status"] == "warning"
    assert group["warnings"]


def test_platform_health_vendor_sources_capture_reports_firecrawl_readiness(monkeypatch) -> None:
    secret = "fc-secret-value"
    _set_opencart_config(monkeypatch)
    _clear_product_factory_config(monkeypatch)
    monkeypatch.setenv("FIRECRAWL_API_KEY", secret)

    response = _client(monkeypatch).get("/api/platform/health")

    group = _groups(response.json())["vendor_sources_capture"]
    assert group["label"] == "Vendor Sources Capture"
    assert group["status"] == "ready"
    assert "Skroutz capture strategy: Firecrawl." in group["details"]
    assert "Firecrawl API key configured: yes." in group["details"]
    assert "Direct JSON fallback: removed." in group["details"]
    assert secret not in response.text


def test_platform_health_vendor_sources_capture_blocks_when_skroutz_sources_need_missing_key(monkeypatch) -> None:
    _set_opencart_config(monkeypatch)
    _clear_product_factory_config(monkeypatch)
    monkeypatch.setenv("FIRECRAWL_API_KEY", "")
    client = _client(monkeypatch)
    monkeypatch.setattr(platform_health_collectors, "_active_skroutz_source_url_count", lambda: 3)

    response = client.get("/api/platform/health")

    group = _groups(response.json())["vendor_sources_capture"]
    assert group["status"] == "blocked"
    assert group["blocking_reasons"] == ["FIRECRAWL_API_KEY is missing for Skroutz Firecrawl capture."]
    assert "Firecrawl API key configured: no." in group["details"]


def test_platform_health_overall_blocked_when_required_group_blocked(monkeypatch) -> None:
    _set_opencart_config(monkeypatch)
    _clear_product_factory_config(monkeypatch)
    monkeypatch.setattr(platform_health_collectors, "collect_catalog_database_readiness", lambda: _db_blocked())
    monkeypatch.setattr(platform_health_collectors, "collect_price_monitoring_database_readiness", lambda: _db_blocked())

    response = TestClient(create_app()).get("/api/platform/health")

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"


def test_platform_health_overall_warning_when_no_blocked_but_warning_exists(monkeypatch) -> None:
    _set_opencart_config(monkeypatch)
    _clear_product_factory_config(monkeypatch)

    response = _client(monkeypatch).get("/api/platform/health")

    payload = response.json()
    assert payload["status"] == "warning"
    assert _groups(payload)["product_factory_api"]["status"] == "warning"


def test_platform_health_response_shape_is_stable(monkeypatch) -> None:
    _set_opencart_config(monkeypatch)
    _clear_product_factory_config(monkeypatch)

    payload = _client(monkeypatch).get("/api/platform/health").json()

    assert set(payload) == {"status", "groups", "updated_at"}
    assert [group["id"] for group in payload["groups"]] == [
        "ecommerce_api",
        "ecommerce_database",
        "catalog",
        "catalog_update_opencart",
        "source_url_agent",
        "price_monitoring",
        "vendor_sources_capture",
        "product_factory_api",
    ]
    for group in payload["groups"]:
        assert set(group) == {
            "id",
            "label",
            "status",
            "summary",
            "details",
            "blocking_reasons",
            "warnings",
            "links",
        }
