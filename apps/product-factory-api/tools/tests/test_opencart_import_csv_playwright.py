from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.opencart_import_csv_playwright import (
    ImportErrorRuntime,
    attest_partial_import_authorization,
    consume_migration_authorization,
    csv_contract_check,
    evaluate_partial_profile_safety,
    step3_monitor,
    validate_migration_authorization,
)


TARGET_IDENTITY = "opencart-target:sha256:" + "a" * 64


def test_partial_profile_safety_requires_delete_and_disable_controls_off() -> None:
    report = evaluate_partial_profile_safety(
        [
            {
                "name": "create_new_products",
                "type": "checkbox",
                "checked": False,
            },
            {
                "name": "delete_missing_products",
                "type": "checkbox",
                "checked": False,
            },
            {
                "name": "disable_missing_products",
                "type": "checkbox",
                "checked": False,
            },
        ]
    )

    assert report["safe"] is True
    assert report["attested_concepts"] == ["create", "delete", "disable"]


@pytest.mark.parametrize(
    "controls",
    [
        [
            {
                "name": "create_new_products",
                "type": "checkbox",
                "checked": False,
            },
            {
                "name": "delete_missing_products",
                "type": "checkbox",
                "checked": False,
            }
        ],
        [
            {
                "name": "create_new_products",
                "type": "checkbox",
                "checked": False,
            },
            {
                "name": "delete_missing_products",
                "type": "checkbox",
                "checked": False,
            },
            {
                "name": "disable_missing_products",
                "type": "radio",
                "checked": True,
                "value": "disabled",
            },
        ],
    ],
)
def test_partial_profile_safety_fails_closed_on_missing_or_enabled_controls(
    controls: list[dict[str, object]],
) -> None:
    assert evaluate_partial_profile_safety(controls)["safe"] is False


def test_partial_profile_safety_does_not_borrow_sibling_negation() -> None:
    report = evaluate_partial_profile_safety(
        [
            {
                "name": "create_new_products",
                "label": "Create products",
                "parent_text": "Create products. Do not delete missing products.",
                "type": "checkbox",
                "checked": True,
            },
            {
                "name": "delete_missing_products",
                "type": "checkbox",
                "checked": False,
            },
            {
                "name": "disable_missing_products",
                "type": "checkbox",
                "checked": False,
            },
        ]
    )

    assert report["safe"] is False
    assert any(
        item["name"] == "create_new_products"
        and item["state"] == "unsafe_enabled"
        for item in report["unsafe_or_ambiguous"]
    )


def test_partial_profile_safety_rejects_mixed_destructive_select_text() -> None:
    report = evaluate_partial_profile_safety(
        [
            {
                "name": "create_new_products",
                "type": "checkbox",
                "checked": False,
            },
            {
                "name": "delete_missing_products",
                "tag": "select",
                "value": "delete",
                "selected_text": "Delete products with no matching row",
            },
            {
                "name": "disable_missing_products",
                "type": "checkbox",
                "checked": False,
            },
        ]
    )

    assert report["safe"] is False
    assert any(
        item["state"] == "ambiguous_mixed_safe_and_unsafe_tokens"
        for item in report["unsafe_or_ambiguous"]
    )


def _write(path: Path, value: str) -> Path:
    path.write_text(value, encoding="utf-8")
    return path


def test_partial_contract_attests_one_exact_existing_model_row(tmp_path: Path) -> None:
    path = _write(tmp_path / "patch.csv", "model,meta_title\n123456,Updated\n")

    contract = csv_contract_check(
        path,
        "123456",
        repo_root=tmp_path,
        allow_partial_csv=True,
    )

    assert contract["row_count"] == 1
    assert contract["first_row_model"] == "123456"
    assert len(contract["csv_sha256"]) == 64


@pytest.mark.parametrize(
    "contents,match",
    [
        ("model,meta_title\n654321,Updated\n", "exact requested"),
        ("model,meta_title\n123456,One\n123456,Two\n", "exactly one"),
        ("model,model\n123456,123456\n", "duplicate headers"),
        ("model,price\n123456,1.00\n", "protected catalog columns"),
    ],
)
def test_partial_contract_rejects_unsafe_scope(
    tmp_path: Path, contents: str, match: str
) -> None:
    path = _write(tmp_path / "unsafe.csv", contents)
    with pytest.raises(ImportErrorRuntime, match=match):
        csv_contract_check(
            path,
            "123456",
            repo_root=tmp_path,
            allow_partial_csv=True,
        )


def _authorization_fixture(
    tmp_path: Path,
    *,
    model: str = "123456",
    target_identity: str = TARGET_IDENTITY,
) -> tuple[Path, dict[str, object], dict[str, object]]:
    now = datetime.now(timezone.utc)
    csv_path = _write(tmp_path / "patch.csv", "model,meta_title\n123456,Updated\n")
    contract = csv_contract_check(
        csv_path,
        model,
        repo_root=tmp_path,
        allow_partial_csv=True,
    )
    scope = {
        "model": model,
        "csv_sha256": contract["csv_sha256"],
        "headers": contract["headers"],
        "image_operations_hash": "b" * 64,
    }
    claim = {
        "schema_version": "1.0",
        "operation": "apply",
        "migration_run_id": "migration-001",
        "snapshot_id": "snapshot-001",
        "approval_hash": "c" * 64,
        "plan_hash": "d" * 64,
        "target_identity": target_identity,
        "claimed_at": (now - timedelta(seconds=5)).isoformat(),
        "one_shot": True,
        "scopes": [scope],
    }
    run_root = tmp_path / "migration-001"
    report_root = run_root / "reports"
    report_root.mkdir(parents=True)
    claim_path = run_root / "apply.claim.json"
    claim_path.write_text(
        json.dumps(claim, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    authorization = {
        "schema_version": "1.0",
        "operation": "apply",
        "migration_run_id": "migration-001",
        "snapshot_id": "snapshot-001",
        "approval_hash": "c" * 64,
        "plan_hash": "d" * 64,
        "target_identity": target_identity,
        **scope,
        "claim_path": str(claim_path),
        "claim_hash": hashlib.sha256(claim_path.read_bytes()).hexdigest(),
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
    }
    authorization_path = report_root / "authorization.json"
    authorization_path.write_text(
        json.dumps(authorization, indent=2) + "\n", encoding="utf-8"
    )
    return authorization_path, contract, authorization


def test_non_dry_run_partial_import_requires_machine_authorization(
    tmp_path: Path,
) -> None:
    _, contract, _ = _authorization_fixture(tmp_path)

    with pytest.raises(ImportErrorRuntime, match="requires.*authorization"):
        attest_partial_import_authorization(
            None,
            allow_partial_csv=True,
            dry_run=False,
            model="123456",
            contract=contract,
            target_identity=TARGET_IDENTITY,
        )


@pytest.mark.parametrize(
    "allow_partial_csv,dry_run",
    [(True, True), (False, False), (False, True)],
)
def test_preflight_and_normal_full_import_do_not_require_migration_authorization(
    tmp_path: Path, allow_partial_csv: bool, dry_run: bool
) -> None:
    _, contract, _ = _authorization_fixture(tmp_path)

    assert (
        attest_partial_import_authorization(
            None,
            allow_partial_csv=allow_partial_csv,
            dry_run=dry_run,
            model="123456",
            contract=contract,
            target_identity=TARGET_IDENTITY,
        )
        is None
    )


def test_valid_run_bound_authorization_attests_exact_scope(tmp_path: Path) -> None:
    authorization_path, contract, authorization = _authorization_fixture(tmp_path)

    attestation = attest_partial_import_authorization(
        str(authorization_path),
        allow_partial_csv=True,
        dry_run=False,
        model="123456",
        contract=contract,
        target_identity=TARGET_IDENTITY,
    )

    assert attestation is not None
    assert attestation["authorized"] is True
    assert attestation["claim_hash"] == authorization["claim_hash"]
    assert attestation["headers"] == ["model", "meta_title"]


def test_partial_import_authorization_is_consumed_once(tmp_path: Path) -> None:
    authorization_path, contract, _ = _authorization_fixture(tmp_path)
    attestation = validate_migration_authorization(
        authorization_path,
        model="123456",
        contract=contract,
        target_identity=TARGET_IDENTITY,
    )

    first = consume_migration_authorization(
        str(authorization_path), attestation, adapter="partial_import"
    )
    assert Path(first["marker"]).is_file()
    with pytest.raises(ImportErrorRuntime, match="already consumed"):
        consume_migration_authorization(
            str(authorization_path), attestation, adapter="partial_import"
        )


def test_partial_import_authorization_rejects_expired_window(tmp_path: Path) -> None:
    authorization_path, contract, authorization = _authorization_fixture(tmp_path)
    now = datetime.now(timezone.utc)
    authorization["issued_at"] = (now - timedelta(hours=2)).isoformat()
    authorization["expires_at"] = (now - timedelta(hours=1)).isoformat()
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")

    with pytest.raises(ImportErrorRuntime, match="expired"):
        validate_migration_authorization(
            authorization_path,
            model="123456",
            contract=contract,
            target_identity=TARGET_IDENTITY,
        )


def test_authorization_rejects_tampered_claim(tmp_path: Path) -> None:
    authorization_path, contract, authorization = _authorization_fixture(tmp_path)
    Path(str(authorization["claim_path"])).write_text("{}\n", encoding="utf-8")

    with pytest.raises(ImportErrorRuntime, match="claim hash"):
        validate_migration_authorization(
            authorization_path,
            model="123456",
            contract=contract,
            target_identity=TARGET_IDENTITY,
        )


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda value: value.update({"unexpected": True}), "exact field set"),
        (lambda value: value.update({"model": "654321"}), "model does not match"),
        (
            lambda value: value.update({"headers": ["meta_title", "model"]}),
            "headers do not match",
        ),
        (
            lambda value: value.update(
                {"target_identity": "opencart-target:sha256:" + "e" * 64}
            ),
            "target identity",
        ),
    ],
)
def test_authorization_rejects_non_exact_current_scope(
    tmp_path: Path, mutation, match: str
) -> None:
    authorization_path, contract, authorization = _authorization_fixture(tmp_path)
    mutation(authorization)
    authorization_path.write_text(
        json.dumps(authorization, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(ImportErrorRuntime, match=match):
        validate_migration_authorization(
            authorization_path,
            model="123456",
            contract=contract,
            target_identity=TARGET_IDENTITY,
        )


def test_authorization_rejects_scope_not_present_in_claim(tmp_path: Path) -> None:
    authorization_path, contract, authorization = _authorization_fixture(tmp_path)
    claim_path = Path(str(authorization["claim_path"]))
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    claim["scopes"][0]["image_operations_hash"] = "f" * 64
    claim_path.write_text(json.dumps(claim) + "\n", encoding="utf-8")
    authorization["claim_hash"] = hashlib.sha256(claim_path.read_bytes()).hexdigest()
    authorization_path.write_text(json.dumps(authorization) + "\n", encoding="utf-8")

    with pytest.raises(ImportErrorRuntime, match="not present"):
        validate_migration_authorization(
            authorization_path,
            model="123456",
            contract=contract,
            target_identity=TARGET_IDENTITY,
        )


def test_authorization_rejects_claim_outside_declared_run(tmp_path: Path) -> None:
    authorization_path, contract, authorization = _authorization_fixture(tmp_path)
    original_claim = Path(str(authorization["claim_path"]))
    outside_claim = tmp_path / "copied.claim.json"
    outside_claim.write_bytes(original_claim.read_bytes())
    authorization["claim_path"] = str(outside_claim)
    authorization["claim_hash"] = hashlib.sha256(outside_claim.read_bytes()).hexdigest()
    authorization_path.write_text(json.dumps(authorization) + "\n", encoding="utf-8")

    with pytest.raises(ImportErrorRuntime, match="outside.*migration run"):
        validate_migration_authorization(
            authorization_path,
            model="123456",
            contract=contract,
            target_identity=TARGET_IDENTITY,
        )


def test_monitor_report_omits_raw_html_and_redacts_admin_route() -> None:
    class Locator:
        def __init__(self, selector: str) -> None:
            self.selector = selector
            self.first = self

        def wait_for(self, **_kwargs) -> None:
            return None

        def inner_text(self) -> str:
            return (
                "Complete https://shop.example/secret-admin/index.php?"
                "user_token=private"
            )

        def inner_html(self) -> str:
            return "<a href='/secret-admin/index.php?user_token=private'>details</a>"

        def count(self) -> int:
            return int(self.selector == "#buttons_completed:visible")

    class Page:
        def locator(self, selector: str) -> Locator:
            return Locator(selector)

    monitor = step3_monitor(
        Page(),
        timeout_ms=100,
        poll_interval_sec=0,
        max_wait_sec=1,
        admin_path="/secret-admin/index.php",
    )

    assert monitor["final_status"] == "completed"
    assert monitor["messages_present"] is True
    assert "messages_html" not in monitor
    assert "secret-admin" not in monitor["status_text"]
    assert "private" not in monitor["status_text"]
