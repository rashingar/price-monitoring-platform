from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from ecommerce.api import routes_product_factory_telegram
from ecommerce.api.app import create_app
from ecommerce.product_factory_telegram import audit
from ecommerce.product_factory_telegram.client import (
    ProductFactoryClient,
    ProductFactoryClientError,
    ProductFactoryJob,
)
from ecommerce.product_factory_telegram.parser import (
    ProductFactoryCommandParseError,
    parse_product_factory_command,
)
from ecommerce.product_factory_telegram.service import (
    PendingSourceChoiceStore,
    process_telegram_product_factory_update,
)
from ecommerce.product_factory_telegram.source_resolution import (
    PreferredSourceConfig,
    ProductFactorySourceResolver,
    SourceResolutionCandidate,
    SourceResolutionConfig,
    SourceResolutionConfigError,
    SourceResolutionResult,
    load_source_resolution_config,
)
from ecommerce.product_factory_telegram.warehouse import (
    WarehouseCatalogError,
    WarehouseProduct,
    lookup_warehouse_product,
)
from ecommerce.source_url_agent.brave_search import BraveSearchResultItem

ACCEPTED_COMMANDS = [
    ("012345", True, False, False, None),
    ("012345 B", True, False, False, None),
    ("012345 S", True, True, False, None),
    ("012345 B S", True, True, False, None),
    ("012345 B B", True, False, True, None),
    ("012345 S B", True, True, True, None),
    ("012345 B S B", True, True, True, None),
    (
        "012345 https://example.com/product",
        True,
        False,
        False,
        "https://example.com/product",
    ),
    (
        "012345 B https://example.com/product",
        True,
        False,
        False,
        "https://example.com/product",
    ),
    (
        "012345 S https://example.com/product",
        True,
        True,
        False,
        "https://example.com/product",
    ),
    (
        "012345 B S https://example.com/product",
        True,
        True,
        False,
        "https://example.com/product",
    ),
    (
        "012345 B B https://example.com/product",
        True,
        False,
        True,
        "https://example.com/product",
    ),
    (
        "012345 S B https://example.com/product",
        True,
        True,
        True,
        "https://example.com/product",
    ),
    (
        "012345 B S B https://example.com/product",
        True,
        True,
        True,
        "https://example.com/product",
    ),
]


@pytest.mark.parametrize(
    ("text", "bestprice", "skroutz", "boxnow", "url"), ACCEPTED_COMMANDS
)
def test_parser_accepts_compact_product_factory_commands(
    text: str,
    bestprice: bool,
    skroutz: bool,
    boxnow: bool,
    url: str | None,
) -> None:
    command = parse_product_factory_command(text)

    assert command.model == "012345"
    assert command.bestprice_status == int(bestprice)
    assert command.skroutz_status == int(skroutz)
    assert command.boxnow == int(boxnow)
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
        lookup_warehouse_product(
            path=path, model="012345", model_column="model", name_column="title"
        )
    assert missing_model.value.code == "warehouse_catalog_model_column_missing"

    with pytest.raises(WarehouseCatalogError) as missing_name:
        lookup_warehouse_product(
            path=path, model="012345", model_column="sku", name_column="name"
        )
    assert missing_name.value.code == "warehouse_catalog_name_column_missing"


def test_warehouse_lookup_empty_product_name_fails(tmp_path: Path) -> None:
    path = tmp_path / "warehouse.csv"
    path.write_text("model,name\n012345,   \n", encoding="utf-8")

    with pytest.raises(WarehouseCatalogError) as exc_info:
        lookup_warehouse_product(path=path, model="012345")

    assert exc_info.value.code == "warehouse_catalog_empty_product_name"


def test_audit_logger_writes_jsonl_with_expected_fields(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"

    event = audit.append_event(
        path=path,
        event_type="telegram_command_received",
        chat_id="-100",
        user_id="42",
        model="012345",
        product_name="Warehouse Product",
        bestprice_status=1,
        status="received",
    )

    rows = list(audit.iter_events(path))
    assert len(rows) == 1
    assert rows[0]["event_id"] == event["event_id"]
    assert rows[0]["event_type"] == "telegram_command_received"
    assert rows[0]["created_at"].endswith("+00:00")
    assert rows[0]["chat_id"] == "-100"
    assert rows[0]["model"] == "012345"
    assert rows[0]["bestprice_status"] == 1


def test_audit_logger_creates_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "audit.jsonl"

    audit.append_event(path=path, event_type="telegram_command_received")

    assert path.exists()


def test_audit_logger_write_failure_is_non_fatal(tmp_path: Path) -> None:
    audit.append_event(path=tmp_path, event_type="telegram_command_received")


def test_latest_enqueued_job_for_model_returns_latest_matching_job_id(
    tmp_path: Path,
) -> None:
    path = tmp_path / "audit.jsonl"
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        model="012345",
        job_id="job-old",
    )
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        model="999999",
        job_id="job-other",
    )
    audit.append_event(
        path=path,
        event_type="product_factory_enqueue_succeeded",
        model="012345",
        job_id="job-new",
    )

    assert audit.latest_enqueued_job_for_model(path, "012345") == "job-new"


def test_latest_enqueued_job_for_model_ignores_malformed_jsonl_lines(
    tmp_path: Path,
) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text(
        "{bad json}\n"
        '{"event_type":"product_factory_enqueue_succeeded","model":"012345","job_id":"job-1"}\n',
        encoding="utf-8",
    )

    assert audit.latest_enqueued_job_for_model(path, "012345") == "job-1"


def test_webhook_rejects_disabled_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_env(monkeypatch, tmp_path, enabled=False)

    response = TestClient(create_app()).post(
        "/api/product-factory/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json=_telegram_update("012345"),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "telegram_intake_disabled"


def test_webhook_rejects_unauthorized_chat_and_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    monkeypatch.setattr(
        routes_product_factory_telegram,
        "_telegram_client",
        lambda _config: fake_telegram,
    )
    monkeypatch.setattr(
        routes_product_factory_telegram,
        "_product_factory_client",
        lambda _config: fake_product_factory,
    )

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
    assert payload["bestprice_status"] == 1
    assert payload["skroutz_status"] == 1
    assert payload["boxnow"] == 1
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
    monkeypatch.setattr(
        "ecommerce.product_factory_telegram.service.resolver_from_config_path",
        lambda _path: FakeSourceResolver(
            SourceResolutionResult(
                method="brave_weighted",
                selected=None,
                candidates=(),
                config=_resolution_config(),
            )
        ),
    )
    monkeypatch.setattr(
        routes_product_factory_telegram,
        "_telegram_client",
        lambda _config: fake_telegram,
    )
    monkeypatch.setattr(
        routes_product_factory_telegram,
        "_product_factory_client",
        lambda _config: fake_product_factory,
    )

    response = TestClient(create_app()).post(
        "/api/product-factory/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json=_telegram_update("012345 B S"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "source_resolution_no_usable_source"
    assert fake_product_factory.payloads == []
    assert "No confident scrape source was found" in fake_telegram.messages[0]["text"]
    assert (
        "Send the command again with a manual URL override"
        in fake_telegram.messages[0]["text"]
    )
    events = list(audit.iter_events(tmp_path / "audit" / "audit.jsonl"))
    assert "source_resolution_no_usable_source" in [
        event["event_type"] for event in events
    ]


def test_source_resolution_config_loads_defaults() -> None:
    config = load_source_resolution_config()

    assert config.minimum_confidence == 70
    assert config.suggestion_confidence == 40
    assert config.max_suggestions == 5
    assert config.pending_choice_ttl_minutes == 15
    assert config.preferred_source_names == ["electronet", "skroutz", "bestprice"]


def test_source_resolution_env_override_config_path_is_honored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "source_resolution.json"
    path.write_text(
        json.dumps(
            {
                "minimum_confidence": 80,
                "suggestion_confidence": 30,
                "max_suggestions": 3,
                "pending_choice_ttl_minutes": 7,
                "preferred_sources": [
                    {
                        "source_name": "custom",
                        "weight": 99,
                        "domains": ["custom.example"],
                        "aliases": ["custom-alias"],
                        "product_url_patterns": ["/p/"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_PATH", str(path))

    config = load_source_resolution_config()

    assert config.minimum_confidence == 80
    assert config.pending_choice_ttl_minutes == 7
    assert config.source_for_alias("custom-alias").source_name == "custom"


def test_invalid_source_resolution_config_fails_safely(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"minimum_confidence": 70}', encoding="utf-8")

    with pytest.raises(SourceResolutionConfigError) as exc_info:
        load_source_resolution_config(path)

    assert "suggestion_confidence must be an integer" in str(exc_info.value)


def test_source_aliases_classify_to_same_source() -> None:
    config = _resolution_config(
        preferred_sources=(
            PreferredSourceConfig(
                source_name="electronet",
                weight=100,
                domains=("electronet.gr",),
                aliases=("elnet",),
                product_url_patterns=("/",),
            ),
        )
    )

    assert config.source_for_alias("elnet") == config.classify_url(
        "https://www.electronet.gr/a/b/c/d"
    )


def test_custom_source_weights_change_ranking_without_code_changes() -> None:
    product = _warehouse_product()
    items = [
        _brave_item(
            "https://www.electronet.gr/a/b/c/d", "Brand MPN-1 Alpha Mixer", rank=1
        ),
        _brave_item(
            "https://www.skroutz.gr/s/123/product.html",
            "Brand MPN-1 Alpha Mixer",
            rank=2,
        ),
    ]

    default_result = ProductFactorySourceResolver(
        config=_resolution_config(), fetcher=StaticFetcher(items)
    ).resolve(product=product)
    custom_result = ProductFactorySourceResolver(
        config=_resolution_config(
            preferred_sources=(
                PreferredSourceConfig(
                    "electronet", 10, ("electronet.gr", "www.electronet.gr"), (), ("/",)
                ),
                PreferredSourceConfig(
                    "skroutz", 100, ("skroutz.gr", "www.skroutz.gr"), (), ("/s/",)
                ),
                PreferredSourceConfig(
                    "bestprice", 50, ("bestprice.gr", "www.bestprice.gr"), (), ("/",)
                ),
            )
        ),
        fetcher=StaticFetcher(items),
    ).resolve(product=product)

    assert default_result.selected.source_name == "electronet"
    assert custom_result.selected.source_name == "skroutz"


def test_default_ranking_prefers_electronet_then_skroutz_then_bestprice() -> None:
    product = _warehouse_product()
    all_sources = ProductFactorySourceResolver(
        config=_resolution_config(),
        fetcher=StaticFetcher(
            [
                _brave_item(
                    "https://www.bestprice.gr/item/123/brand-mpn-1.html",
                    "Brand MPN-1 Alpha Mixer",
                    rank=1,
                ),
                _brave_item(
                    "https://www.skroutz.gr/s/123/brand-mpn-1.html",
                    "Brand MPN-1 Alpha Mixer",
                    rank=2,
                ),
                _brave_item(
                    "https://www.electronet.gr/a/b/c/brand-mpn-1",
                    "Brand MPN-1 Alpha Mixer",
                    rank=3,
                ),
            ]
        ),
    ).resolve(product=product)
    without_electronet = ProductFactorySourceResolver(
        config=_resolution_config(),
        fetcher=StaticFetcher(
            [
                _brave_item(
                    "https://www.bestprice.gr/item/123/brand-mpn-1.html",
                    "Brand MPN-1 Alpha Mixer",
                    rank=1,
                ),
                _brave_item(
                    "https://www.skroutz.gr/s/123/brand-mpn-1.html",
                    "Brand MPN-1 Alpha Mixer",
                    rank=2,
                ),
            ]
        ),
    ).resolve(product=product)
    only_bestprice = ProductFactorySourceResolver(
        config=_resolution_config(),
        fetcher=StaticFetcher(
            [
                _brave_item(
                    "https://www.electronet.gr/search?q=mpn-1",
                    "Search results for MPN-1",
                    rank=1,
                ),
                _brave_item(
                    "https://www.bestprice.gr/item/123/brand-mpn-1.html",
                    "Brand MPN-1 Alpha Mixer",
                    rank=2,
                ),
            ]
        ),
    ).resolve(product=product)

    assert all_sources.selected.source_name == "electronet"
    assert without_electronet.selected.source_name == "skroutz"
    assert only_bestprice.selected.source_name == "bestprice"


def test_high_confidence_result_echoes_source_before_enqueue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    config = _telegram_config(tmp_path, monkeypatch)

    result = process_telegram_product_factory_update(
        _telegram_update("012345 B S"),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        source_resolver=FakeSourceResolver(
            _fake_resolution(selected=_candidate(confidence=91))
        ),
        pending_choices=PendingSourceChoiceStore(),
    )

    assert result.status == "queued"
    assert len(fake_product_factory.payloads) == 1
    assert fake_telegram.messages[0]["text"].startswith(
        "Resolved Product Factory source"
    )
    assert "page title: Brand MPN-1 Alpha Mixer" in fake_telegram.messages[0]["text"]
    assert (
        "URL: https://www.electronet.gr/a/b/c/brand-mpn-1"
        in fake_telegram.messages[0]["text"]
    )
    assert "confidence: 91" in fake_telegram.messages[0]["text"]
    assert (
        fake_product_factory.payloads[0]["source_resolution"]["method"]
        == "brave_weighted"
    )
    assert (
        fake_product_factory.payloads[0]["source_resolution"]["selected_source"]
        == "electronet"
    )
    assert "source_auto_selected" in _audit_event_types(config)
    assert "product_factory_enqueue_succeeded" in _audit_event_types(config)


def test_low_confidence_candidates_create_pending_suggestions_and_do_not_enqueue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    store = PendingSourceChoiceStore()
    config = _telegram_config(tmp_path, monkeypatch)

    result = process_telegram_product_factory_update(
        _telegram_update("012345"),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        source_resolver=FakeSourceResolver(
            _fake_resolution(candidates=(_candidate(confidence=55),))
        ),
        pending_choices=store,
    )

    assert result.status == "source_resolution_suggestions"
    assert fake_product_factory.payloads == []
    assert "1. electronet" in fake_telegram.messages[0]["text"]
    assert "title: Brand MPN-1 Alpha Mixer" in fake_telegram.messages[0]["text"]
    markup = fake_telegram.messages[0]["reply_markup"]
    callback_data = markup["inline_keyboard"][0][0]["callback_data"]
    assert callback_data.startswith("pfsrc:")
    assert "https://" not in callback_data
    assert "Cancel" == markup["inline_keyboard"][1][0]["text"]
    assert "source_suggestions_sent" in _audit_event_types(config)


def test_selecting_pending_suggestion_enqueues_with_selected_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    store = PendingSourceChoiceStore()
    config = _telegram_config(tmp_path, monkeypatch)
    process_telegram_product_factory_update(
        _telegram_update("012345 S"),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        source_resolver=FakeSourceResolver(
            _fake_resolution(candidates=(_candidate(confidence=55),))
        ),
        pending_choices=store,
    )
    callback_data = fake_telegram.messages[0]["reply_markup"]["inline_keyboard"][0][0][
        "callback_data"
    ]

    result = process_telegram_product_factory_update(
        _telegram_callback_update(callback_data),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        pending_choices=store,
    )

    assert result.status == "queued"
    assert (
        fake_product_factory.payloads[0]["source_url"]
        == "https://www.electronet.gr/a/b/c/brand-mpn-1"
    )
    assert fake_product_factory.payloads[0]["skroutz_status"] == 1
    assert (
        fake_product_factory.payloads[0]["source_resolution"]["selected_title"]
        == "Brand MPN-1 Alpha Mixer"
    )
    assert "source_suggestion_selected" in _audit_event_types(config)
    assert "product_factory_enqueue_succeeded" in _audit_event_types(config)


def test_expired_pending_suggestion_does_not_enqueue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    store = PendingSourceChoiceStore()
    config = _telegram_config(tmp_path, monkeypatch)
    process_telegram_product_factory_update(
        _telegram_update("012345"),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        source_resolver=FakeSourceResolver(
            _fake_resolution(candidates=(_candidate(confidence=55),))
        ),
        pending_choices=store,
    )
    callback_data = fake_telegram.messages[0]["reply_markup"]["inline_keyboard"][0][0][
        "callback_data"
    ]
    choice_id = callback_data.split(":")[1]
    choice = store.get(choice_id)
    store._choices[choice_id] = replace(
        choice, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )

    result = process_telegram_product_factory_update(
        _telegram_callback_update(callback_data),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        pending_choices=store,
    )

    assert result.status == "source_choice_expired"
    assert fake_product_factory.payloads == []
    assert store.get(choice_id) is None
    assert "source_choice_expired" in _audit_event_types(config)


def test_cancel_pending_suggestion_deletes_choice_and_does_not_enqueue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    store = PendingSourceChoiceStore()
    config = _telegram_config(tmp_path, monkeypatch)
    process_telegram_product_factory_update(
        _telegram_update("012345"),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        source_resolver=FakeSourceResolver(
            _fake_resolution(candidates=(_candidate(confidence=55),))
        ),
        pending_choices=store,
    )
    cancel_data = fake_telegram.messages[0]["reply_markup"]["inline_keyboard"][1][0][
        "callback_data"
    ]
    choice_id = cancel_data.split(":")[1]

    result = process_telegram_product_factory_update(
        _telegram_callback_update(cancel_data),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        pending_choices=store,
    )

    assert result.status == "source_choice_cancelled"
    assert fake_product_factory.payloads == []
    assert store.get(choice_id) is None
    assert "source_suggestion_cancelled" in _audit_event_types(config)


def test_manual_url_bypasses_brave_and_suggestions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    config = _telegram_config(tmp_path, monkeypatch)

    result = process_telegram_product_factory_update(
        _telegram_update("012345 B https://example.com/product"),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        source_resolver=ExplodingSourceResolver(),
        pending_choices=PendingSourceChoiceStore(),
    )

    assert result.status == "queued"
    assert (
        fake_product_factory.payloads[0]["source_resolution"]["method"] == "manual_url"
    )
    assert (
        fake_product_factory.payloads[0]["source_resolution"]["selected_source"]
        == "Manual URL"
    )
    assert fake_telegram.messages[0]["text"] == (
        "Selected scrape source: Manual URL\n"
        "URL: https://example.com/product\n"
        "Confidence: manual override"
    )
    assert "manual_url_selected" in _audit_event_types(config)
    assert "product_factory_enqueue_succeeded" in _audit_event_types(config)


def test_listing_flags_do_not_affect_selected_scraping_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    config = _telegram_config(tmp_path, monkeypatch)

    process_telegram_product_factory_update(
        _telegram_update("012345 B S"),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        source_resolver=FakeSourceResolver(
            _fake_resolution(
                selected=_candidate(source_name="electronet", confidence=91)
            )
        ),
        pending_choices=PendingSourceChoiceStore(),
    )

    payload = fake_product_factory.payloads[0]
    assert payload["bestprice_status"] == 1
    assert payload["skroutz_status"] == 1
    assert payload["source_resolution"]["selected_source"] == "electronet"


def test_product_factory_client_unavailable_has_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_connect_error(*_args: Any, **_kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", raise_connect_error)

    with pytest.raises(ProductFactoryClientError) as exc_info:
        ProductFactoryClient("http://127.0.0.1:9").start_full_pipeline(
            {"model": "012345"}
        )

    assert (
        str(exc_info.value) == "Product Factory API is unavailable; no job was started."
    )


def test_product_factory_client_get_job_maps_status_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(*_args: Any, **_kwargs: Any) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "job_id": "job-123",
                "job_type": "full_pipeline",
                "status": "running",
                "model": "012345",
                "message": "Running.",
                "error": None,
                "error_code": None,
                "created_at": "created",
                "updated_at": "updated",
                "started_at": "started",
                "finished_at": None,
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    job = ProductFactoryClient("http://127.0.0.1:8000").get_job("job-123")

    assert job.job_id == "job-123"
    assert job.job_type == "full_pipeline"
    assert job.status == "running"
    assert job.model == "012345"
    assert job.message == "Running."
    assert job.updated_at == "updated"


def test_product_factory_client_status_errors_are_clear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *_args, **_kwargs: httpx.Response(
            404, json={"detail": "Job not found."}
        ),
    )

    with pytest.raises(ProductFactoryClientError) as exc_info:
        ProductFactoryClient("http://127.0.0.1:8000").get_job("missing")

    assert str(exc_info.value) == "Product Factory job missing was not found."


def test_webhook_reports_product_factory_unavailable_to_telegram(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_telegram = FakeTelegramClient()
    _configure_env(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(
        routes_product_factory_telegram,
        "_telegram_client",
        lambda _config: fake_telegram,
    )
    monkeypatch.setattr(
        routes_product_factory_telegram,
        "_product_factory_client",
        lambda _config: FailingProductFactoryClient(),
    )

    response = TestClient(create_app()).post(
        "/api/product-factory/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json=_telegram_update("012345 https://example.com/product"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "product_factory_error"
    assert fake_telegram.messages[0]["text"].startswith(
        "Selected scrape source: Manual URL"
    )
    assert (
        fake_telegram.messages[1]["text"]
        == "Product Factory error: Product Factory API is unavailable; no job was started."
    )
    events = list(audit.iter_events(tmp_path / "audit" / "audit.jsonl"))
    assert "product_factory_enqueue_failed" in [event["event_type"] for event in events]
    assert not any(
        event.get("job_id")
        for event in events
        if event["event_type"] == "product_factory_enqueue_failed"
    )


def test_pfstatus_fetches_job_and_sends_status_fields_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    config = _telegram_config(tmp_path, monkeypatch)

    result = process_telegram_product_factory_update(
        _telegram_update("/pfstatus job-123"),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        pending_choices=PendingSourceChoiceStore(),
    )

    assert result.status == "status_reported"
    assert fake_product_factory.get_job_calls == ["job-123"]
    assert fake_product_factory.log_fetches == 0
    text = fake_telegram.messages[0]["text"]
    assert text == (
        "Product Factory status\n"
        "job_id: job-123\n"
        "type: full_pipeline\n"
        "model: 012345\n"
        "status: queued\n"
        "message: Queued.\n"
        "error: -\n"
        "updated_at: 2026-05-16T10:00:00+00:00"
    )
    assert "https://" not in text
    assert "confidence" not in text
    assert "log line" not in text
    assert "product_factory_status_requested" in _audit_event_types(config)


@pytest.mark.parametrize(
    "text", ["/pfstatus job_id: job-123", "/pfstatus job: job-123"]
)
def test_pfstatus_accepts_copied_job_id_forms(
    text: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    config = _telegram_config(tmp_path, monkeypatch)

    result = process_telegram_product_factory_update(
        _telegram_update(text),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        pending_choices=PendingSourceChoiceStore(),
    )

    assert result.status == "status_reported"
    assert fake_product_factory.get_job_calls == ["job-123"]


@pytest.mark.parametrize(
    "text", ["/pfstatus", "/pfstatus job-123 extra", "/pfstatus job_id: job-123 extra"]
)
def test_invalid_pfstatus_returns_usage_examples(
    text: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    config = _telegram_config(tmp_path, monkeypatch)

    result = process_telegram_product_factory_update(
        _telegram_update(text),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        pending_choices=PendingSourceChoiceStore(),
    )

    assert result.status == "status_command_error"
    assert "/pfstatus <job_id>" in fake_telegram.messages[0]["text"]
    assert "/pfstatus job_id: <job_id>" in fake_telegram.messages[0]["text"]
    assert "/pfstatus job: <job_id>" in fake_telegram.messages[0]["text"]


def test_status_model_uses_latest_audit_job_id_when_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    fake_product_factory.jobs["job-new"] = ProductFactoryJob(
        job_id="job-new",
        status="running",
        raw={"job_id": "job-new"},
        job_type="full_pipeline",
        model="012345",
        message="Running.",
        updated_at="2026-05-16T11:00:00+00:00",
    )
    config = _telegram_config(tmp_path, monkeypatch)
    audit.append_event(
        path=config.audit_log_path,
        event_type="product_factory_enqueue_succeeded",
        model="012345",
        job_id="job-old",
    )
    audit.append_event(
        path=config.audit_log_path,
        event_type="product_factory_enqueue_succeeded",
        model="012345",
        job_id="job-new",
    )

    result = process_telegram_product_factory_update(
        _telegram_update("status 012345"),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        pending_choices=PendingSourceChoiceStore(),
    )

    assert result.job_id == "job-new"
    assert fake_product_factory.get_job_calls == ["job-new"]
    assert fake_product_factory.by_model_calls == []
    assert "job_id: job-new" in fake_telegram.messages[0]["text"]


def test_status_model_falls_back_to_jobs_by_model_when_audit_has_no_match(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    fake_product_factory.jobs_by_model["012345"] = [
        ProductFactoryJob(
            job_id="job-latest",
            status="succeeded",
            raw={"job_id": "job-latest"},
            job_type="render",
            model="012345",
            message="Done.",
        ),
        ProductFactoryJob(
            job_id="job-old",
            status="failed",
            raw={"job_id": "job-old"},
            job_type="prepare",
            model="012345",
        ),
    ]
    config = _telegram_config(tmp_path, monkeypatch)

    result = process_telegram_product_factory_update(
        _telegram_update("status 012345"),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        pending_choices=PendingSourceChoiceStore(),
    )

    assert result.job_id == "job-latest"
    assert fake_product_factory.by_model_calls == ["012345"]
    assert "job_id: job-latest" in fake_telegram.messages[0]["text"]
    assert "job-old" not in fake_telegram.messages[0]["text"]


def test_status_model_read_failure_falls_back_to_jobs_by_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    fake_product_factory.jobs_by_model["012345"] = [
        ProductFactoryJob(
            job_id="job-any",
            status="queued",
            raw={"job_id": "job-any"},
            job_type="publish",
            model="012345",
        )
    ]
    config = replace(
        _telegram_config(tmp_path, monkeypatch), audit_log_path=str(tmp_path)
    )

    result = process_telegram_product_factory_update(
        _telegram_update("status 012345"),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        pending_choices=PendingSourceChoiceStore(),
    )

    assert result.job_id == "job-any"
    assert fake_product_factory.by_model_calls == ["012345"]


def test_status_model_preserves_leading_zeros_and_reports_no_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    config = _telegram_config(tmp_path, monkeypatch)

    result = process_telegram_product_factory_update(
        _telegram_update("status 000123"),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        pending_choices=PendingSourceChoiceStore(),
    )

    assert result.status == "status_not_found"
    assert fake_product_factory.by_model_calls == ["000123"]
    assert (
        fake_telegram.messages[0]["text"]
        == "No Product Factory job found for model 000123."
    )


@pytest.mark.parametrize("text", ["status", "status 12345", "status 012345 extra"])
def test_invalid_status_model_returns_usage_example(
    text: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_telegram = FakeTelegramClient()
    fake_product_factory = FakeProductFactoryClient()
    config = _telegram_config(tmp_path, monkeypatch)

    result = process_telegram_product_factory_update(
        _telegram_update(text),
        config=config,
        telegram_client=fake_telegram,
        product_factory_client=fake_product_factory,
        pending_choices=PendingSourceChoiceStore(),
    )

    assert result.status == "status_command_error"
    assert "status 012345" in fake_telegram.messages[0]["text"]


class FakeTelegramClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send_message(
        self, chat_id: str, text: str, *, reply_markup: dict[str, Any] | None = None
    ) -> None:
        self.messages.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )


class FakeProductFactoryClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.jobs: dict[str, ProductFactoryJob] = {
            "job-123": ProductFactoryJob(
                job_id="job-123",
                status="queued",
                raw={"job_id": "job-123"},
                job_type="full_pipeline",
                model="012345",
                message="Queued.",
                updated_at="2026-05-16T10:00:00+00:00",
            )
        }
        self.jobs_by_model: dict[str, list[ProductFactoryJob]] = {}
        self.get_job_calls: list[str] = []
        self.by_model_calls: list[str] = []
        self.log_fetches = 0

    def start_full_pipeline(self, payload: dict[str, Any]) -> ProductFactoryJob:
        self.payloads.append(json.loads(json.dumps(payload)))
        return self.jobs["job-123"]

    def get_job(self, job_id: str) -> ProductFactoryJob:
        self.get_job_calls.append(job_id)
        try:
            return self.jobs[job_id]
        except KeyError as exc:
            raise ProductFactoryClientError(
                f"Product Factory job {job_id} was not found."
            ) from exc

    def list_jobs_by_model(self, model: str) -> list[ProductFactoryJob]:
        self.by_model_calls.append(model)
        return self.jobs_by_model.get(model, [])

    def get_job_logs(self, job_id: str) -> list[str]:
        del job_id
        self.log_fetches += 1
        return ["unexpected log line"]


class FailingProductFactoryClient:
    def start_full_pipeline(self, payload: dict[str, Any]) -> ProductFactoryJob:
        del payload
        raise ProductFactoryClientError(
            "Product Factory API is unavailable; no job was started."
        )

    def get_job(self, job_id: str) -> ProductFactoryJob:
        del job_id
        raise ProductFactoryClientError(
            "Product Factory API is unavailable; job status could not be fetched."
        )

    def list_jobs_by_model(self, model: str) -> list[ProductFactoryJob]:
        del model
        raise ProductFactoryClientError(
            "Product Factory API is unavailable; jobs by model could not be fetched."
        )


class StaticFetcher:
    def __init__(self, items: list[BraveSearchResultItem]) -> None:
        self.items = items
        self.queries: list[str] = []

    def search(self, query: str, *, max_results: int) -> list[BraveSearchResultItem]:
        self.queries.append(query)
        return self.items[:max_results]


class FakeSourceResolver:
    def __init__(self, result: SourceResolutionResult) -> None:
        self.result = result

    def resolve(self, *, product: WarehouseProduct) -> SourceResolutionResult:
        del product
        return self.result


class ExplodingSourceResolver:
    def resolve(self, *, product: WarehouseProduct) -> SourceResolutionResult:
        del product
        raise AssertionError(
            "source resolver should not be called for manual URL commands"
        )


def _configure_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, enabled: bool
) -> None:
    catalog_path = tmp_path / "warehouse.csv"
    catalog_path.write_text(
        "model,name,manufacturer,mpn,barcode,category\n"
        "012345,Warehouse Product,Brand,MPN-1,5200000000000,Mixers\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "PRODUCT_FACTORY_TELEGRAM_ENABLED", "true" if enabled else "false"
    )
    monkeypatch.setenv("PRODUCT_FACTORY_TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setenv("PRODUCT_FACTORY_TELEGRAM_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("PRODUCT_FACTORY_TELEGRAM_ALLOWED_CHAT_IDS", "-100")
    monkeypatch.setenv("PRODUCT_FACTORY_TELEGRAM_ALLOWED_USER_IDS", "42")
    monkeypatch.setenv("PRODUCT_FACTORY_WAREHOUSE_CATALOG_PATH", str(catalog_path))
    monkeypatch.setenv("PRODUCT_FACTORY_WAREHOUSE_CATALOG_MODEL_COLUMN", "model")
    monkeypatch.setenv("PRODUCT_FACTORY_WAREHOUSE_CATALOG_NAME_COLUMN", "name")
    monkeypatch.setenv("PRODUCT_FACTORY_WAREHOUSE_CATALOG_ENCODING", "utf-8-sig")
    monkeypatch.setenv("PRODUCT_FACTORY_API_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv(
        "PRODUCT_FACTORY_TELEGRAM_AUDIT_LOG_PATH",
        str(tmp_path / "audit" / "audit.jsonl"),
    )


def _telegram_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    _configure_env(monkeypatch, tmp_path, enabled=True)
    from ecommerce.product_factory_telegram.config import (
        product_factory_telegram_config_from_env,
    )

    return product_factory_telegram_config_from_env()


def _audit_events(config: Any) -> list[dict[str, Any]]:
    return list(audit.iter_events(config.audit_log_path))


def _audit_event_types(config: Any) -> list[str]:
    return [event["event_type"] for event in _audit_events(config)]


def _telegram_update(
    text: str, *, chat_id: str = "-100", user_id: str = "42"
) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "chat": {"id": chat_id},
            "from": {"id": user_id},
            "text": text,
        },
    }


def _telegram_callback_update(
    data: str, *, chat_id: str = "-100", user_id: str = "42"
) -> dict[str, Any]:
    return {
        "update_id": 2,
        "callback_query": {
            "id": "callback-1",
            "from": {"id": user_id},
            "message": {
                "message_id": 11,
                "chat": {"id": chat_id},
            },
            "data": data,
        },
    }


def _resolution_config(
    *,
    preferred_sources: tuple[PreferredSourceConfig, ...] | None = None,
    minimum_confidence: int = 70,
    suggestion_confidence: int = 40,
    max_suggestions: int = 5,
    pending_choice_ttl_minutes: int = 15,
) -> SourceResolutionConfig:
    return SourceResolutionConfig(
        minimum_confidence=minimum_confidence,
        suggestion_confidence=suggestion_confidence,
        max_suggestions=max_suggestions,
        pending_choice_ttl_minutes=pending_choice_ttl_minutes,
        preferred_sources=preferred_sources
        or (
            PreferredSourceConfig(
                "electronet",
                100,
                ("electronet.gr", "www.electronet.gr"),
                ("electronet",),
                ("/",),
            ),
            PreferredSourceConfig(
                "skroutz", 70, ("skroutz.gr", "www.skroutz.gr"), ("skroutz",), ("/s/",)
            ),
            PreferredSourceConfig(
                "bestprice",
                50,
                ("bestprice.gr", "www.bestprice.gr"),
                ("bestprice",),
                ("/",),
            ),
        ),
    )


def _fake_resolution(
    *,
    selected: SourceResolutionCandidate | None = None,
    candidates: tuple[SourceResolutionCandidate, ...] | None = None,
) -> SourceResolutionResult:
    if candidates is None:
        candidates = (selected,) if selected is not None else ()
    return SourceResolutionResult(
        method="brave_weighted",
        selected=selected,
        candidates=candidates,
        config=_resolution_config(),
    )


def _candidate(
    *,
    source_name: str = "electronet",
    confidence: int,
    url: str = "https://www.electronet.gr/a/b/c/brand-mpn-1",
    title: str = "Brand MPN-1 Alpha Mixer",
) -> SourceResolutionCandidate:
    return SourceResolutionCandidate(
        source_name=source_name,
        url=url,
        title=title,
        description="Brand Alpha Mixer with MPN-1",
        confidence=confidence,
        result_rank=1,
    )


def _warehouse_product() -> WarehouseProduct:
    return WarehouseProduct(
        model="012345",
        name="Brand Alpha Mixer",
        metadata={
            "manufacturer": "Brand",
            "mpn": "MPN-1",
            "barcode": "5200000000000",
            "category": "Mixers",
        },
    )


def _brave_item(url: str, title: str, *, rank: int) -> BraveSearchResultItem:
    return BraveSearchResultItem(
        url=url,
        title=title,
        description=f"{title} product page",
        extra_snippets=(f"{title} barcode 5200000000000",),
        profile={},
        fetch_metadata={},
        rank=rank,
    )
