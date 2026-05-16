from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from ecommerce.api import routes_product_factory_telegram
from ecommerce.api.app import create_app
from ecommerce.product_factory_telegram.client import ProductFactoryClient, ProductFactoryClientError, ProductFactoryJob
from ecommerce.product_factory_telegram.parser import ProductFactoryCommandParseError, parse_product_factory_command
from ecommerce.product_factory_telegram.warehouse import WarehouseCatalogError, lookup_warehouse_product


ACCEPTED_COMMANDS = [
    ("012345", False, False, False, None),
    ("012345 B", True, False, False, None),
    ("012345 S", False, True, False, None),
    ("012345 B S", True, True, False, None),
    ("012345 B B", True, False, True, None),
    ("012345 S B", False, True, True, None),
    ("012345 B S B", True, True, True, None),
    ("012345 https://example.com/product", False, False, False, "https://example.com/product"),
    ("012345 B https://example.com/product", True, False, False, "https://example.com/product"),
    ("012345 S https://example.com/product", False, True, False, "https://example.com/product"),
    ("012345 B S https://example.com/product", True, True, False, "https://example.com/product"),
    ("012345 B B https://example.com/product", True, False, True, "https://example.com/product"),
    ("012345 S B https://example.com/product", False, True, True, "https://example.com/product"),
    ("012345 B S B https://example.com/product", True, True, True, "https://example.com/product"),
]


@pytest.mark.parametrize(("text", "bestprice", "skroutz", "boxnow", "url"), ACCEPTED_COMMANDS)
def test_parser_accepts_compact_product_factory_commands(
    text: str,
    bestprice: bool,
    skroutz: bool,
    boxnow: bool,
    url: str | None,
) -> None:
    command = parse_product_factory_command(text)

    assert command.model == "012345"
    assert command.bestprice_enabled is bestprice
    assert command.skroutz_enabled is skroutz
    assert command.boxnow_enabled is boxnow
    assert command.manual_url == url


@pytest.mark.parametrize(
    "text",
    [
        "",
        "12345",
        "1234567",
        "ABCDEF",
        "012345 X",
        "012345 B S S",
        "012345 S S",
        "012345 S B B",
        "012345 ftp://example.com/product",
        "012345 https://example.com/product B",
    ],
)
def test_parser_rejects_invalid_formats(text: str) -> None:
    with pytest.raises(ProductFactoryCommandParseError):
        parse_product_factory_command(text)


def test_parser_preserves_leading_zeros() -> None:
    assert parse_product_factory_command("000123 B S").model == "000123"


def test_warehouse_lookup_exact_model_match_with_leading_zeros(tmp_path: Path) -> None:
    path = tmp_path / "warehouse.csv"
    path.write_text(
        "model,name,manufacturer,mpn,barcode,category,price,quantity\n"
        "12345,Wrong Product,,,,,,\n"
        "012345,Correct Product,Brand,MPN-1,5200000000000,Kitchen,10.90,7\n",
        encoding="utf-8",
    )

    product = lookup_warehouse_product(path=path, model="012345")

    assert product.model == "012345"
    assert product.name == "Correct Product"
    assert product.metadata == {
        "manufacturer": "Brand",
        "mpn": "MPN-1",
        "barcode": "5200000000000",
        "category": "Kitchen",
        "price": "10.90",
        "quantity": "7",
    }


def test_warehouse_lookup_duplicate_model_fails(tmp_path: Path) -> None:
    path = tmp_path / "warehouse.csv"
    path.write_text("model,name\n012345,One\n012345,Two\n", encoding="utf-8")

    with pytest.raises(WarehouseCatalogError) as exc_info:
        lookup_warehouse_product(path=path, model="012345")

    assert exc_info.value.code == "warehouse_catalog_duplicate_model"


def test_warehouse_lookup_missing_configured_columns_fails(tmp_path: Path) -> None:
    path = tmp_path / "warehouse.csv"
    path.write_text("sku,title\n012345,Product\n", encoding="utf-8")

    with pytest.raises(WarehouseCatalogError) as missing_model:
        lookup_warehouse_product(path=path, model="012345", model_column="model", name_column="title")
    assert missing_model.value.code == "warehouse_catalog_model_column_missing"

    with pytest.raises(WarehouseCatalogError) as missing_name:
        lookup_warehouse_product(path=path, model="012345", model_column="sku", name_column="name")
    assert missing_name.value.code == "warehouse_catalog_name_column_missing"


def test_warehouse_lookup_empty_product_name_fails(tmp_path: Path) -> None:
    path = tmp_path / "warehouse.csv"
    path.write_text("model,name\n012345,   \n", encoding="utf-8")

    with pytest.raises(WarehouseCatalogError) as exc_info:
        lookup_warehouse_product(path=path, model="012345")

    assert exc_info.value.code == "warehouse_catalog_empty_product_name"


def test_webhook_rejects_disabled_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path, enabled=False)

    response = TestClient(create_app()).post(
        "/api/product-factory/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json=_telegram_update("012345"),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "telegram_intake_disabled"


def test_webhook_rejects_unauthorized_chat_and_user(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_env(monkeypatch, tmp_path, enabled=True)

    response = TestClient(create_app()).post(
        "/api/product-factory/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json=_telegram_update("012345", chat_id="-2", user_id="999"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"


def test_webhook_with_manual_url_calls_product_factory_with_correct_flags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    _configure_env(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(routes_product_factory_telegram, "_telegram_client", lambda _config: fake_telegram)
    monkeypatch.setattr(routes_product_factory_telegram, "_product_factory_client", lambda _config: fake_product_factory)

    response = TestClient(create_app()).post(
        "/api/product-factory/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json=_telegram_update("012345 B S B https://example.com/product"),
    )

    assert response.status_code == 200
    assert response.json()["job_id"] == "job-123"
    assert len(fake_product_factory.payloads) == 1
    payload = fake_product_factory.payloads[0]
    assert payload["model"] == "012345"
    assert payload["product_name"] == "Warehouse Product"
    assert payload["source_url"] == "https://example.com/product"
    assert payload["bestprice_enabled"] is True
    assert payload["skroutz_enabled"] is True
    assert payload["boxnow_enabled"] is True
    assert payload["photos"] == 20
    assert payload["sections"] == 20
    assert payload["trigger_source"] == "telegram"
    assert payload["telegram_chat_id"] == "-100"
    assert payload["source_resolution"]["method"] == "manual_url"
    assert payload["source_resolution"]["manual_override"] is True
    assert fake_telegram.messages[0]["text"] == (
        "Selected scrape source: Manual URL\n"
        "URL: https://example.com/product\n"
        "Confidence: manual override"
    )
    assert "job_id: job-123" in fake_telegram.messages[1]["text"]


def test_webhook_without_manual_url_does_not_enqueue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    _configure_env(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(routes_product_factory_telegram, "_telegram_client", lambda _config: fake_telegram)
    monkeypatch.setattr(routes_product_factory_telegram, "_product_factory_client", lambda _config: fake_product_factory)

    response = TestClient(create_app()).post(
        "/api/product-factory/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json=_telegram_update("012345 B S"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "source_resolution_not_implemented"
    assert fake_product_factory.payloads == []
    assert "Automatic source resolution is not implemented yet" in fake_telegram.messages[0]["text"]
    assert "no Product Factory job was started" in fake_telegram.messages[0]["text"]


def test_product_factory_client_unavailable_has_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_connect_error(*_args: Any, **_kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", raise_connect_error)

    with pytest.raises(ProductFactoryClientError) as exc_info:
        ProductFactoryClient("http://127.0.0.1:9").start_full_pipeline({"model": "012345"})

    assert str(exc_info.value) == "Product Factory API is unavailable; no job was started."


def test_webhook_reports_product_factory_unavailable_to_telegram(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_telegram = FakeTelegramClient()
    _configure_env(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(routes_product_factory_telegram, "_telegram_client", lambda _config: fake_telegram)
    monkeypatch.setattr(routes_product_factory_telegram, "_product_factory_client", lambda _config: FailingProductFactoryClient())

    response = TestClient(create_app()).post(
        "/api/product-factory/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json=_telegram_update("012345 https://example.com/product"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "product_factory_error"
    assert fake_telegram.messages[0]["text"].startswith("Selected scrape source: Manual URL")
    assert fake_telegram.messages[1]["text"] == "Product Factory error: Product Factory API is unavailable; no job was started."


class FakeTelegramClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def send_message(self, chat_id: str, text: str) -> None:
        self.messages.append({"chat_id": chat_id, "text": text})


class FakeProductFactoryClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def start_full_pipeline(self, payload: dict[str, Any]) -> ProductFactoryJob:
        self.payloads.append(json.loads(json.dumps(payload)))
        return ProductFactoryJob(job_id="job-123", status="queued", raw={"job_id": "job-123"})


class FailingProductFactoryClient:
    def start_full_pipeline(self, payload: dict[str, Any]) -> ProductFactoryJob:
        del payload
        raise ProductFactoryClientError("Product Factory API is unavailable; no job was started.")


def _configure_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, enabled: bool) -> None:
    catalog_path = tmp_path / "warehouse.csv"
    catalog_path.write_text("model,name,manufacturer\n012345,Warehouse Product,Brand\n", encoding="utf-8")
    monkeypatch.setenv("PRODUCT_FACTORY_TELEGRAM_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("PRODUCT_FACTORY_TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setenv("PRODUCT_FACTORY_TELEGRAM_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("PRODUCT_FACTORY_TELEGRAM_ALLOWED_CHAT_IDS", "-100")
    monkeypatch.setenv("PRODUCT_FACTORY_TELEGRAM_ALLOWED_USER_IDS", "42")
    monkeypatch.setenv("PRODUCT_FACTORY_WAREHOUSE_CATALOG_PATH", str(catalog_path))
    monkeypatch.setenv("PRODUCT_FACTORY_WAREHOUSE_CATALOG_MODEL_COLUMN", "model")
    monkeypatch.setenv("PRODUCT_FACTORY_WAREHOUSE_CATALOG_NAME_COLUMN", "name")
    monkeypatch.setenv("PRODUCT_FACTORY_WAREHOUSE_CATALOG_ENCODING", "utf-8-sig")
    monkeypatch.setenv("PRODUCT_FACTORY_API_BASE_URL", "http://127.0.0.1:8000")


def _telegram_update(text: str, *, chat_id: str = "-100", user_id: str = "42") -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "chat": {"id": chat_id},
            "from": {"id": user_id},
            "text": text,
        },
    }
