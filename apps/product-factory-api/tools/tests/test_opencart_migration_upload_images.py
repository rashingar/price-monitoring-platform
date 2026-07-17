import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import opencart_migration_upload_images as uploader
from tools.opencart_upload_images import UploadError


class _Response:
    def __init__(self, status_code: int, content: bytes, url: str) -> None:
        self.status_code = status_code
        self.content = content
        self.url = url


def _operation(path: str, content: bytes) -> dict[str, str]:
    return {
        "new_path": path,
        "target_hash": hashlib.sha256(content).hexdigest(),
    }


def _mock_requests(monkeypatch: pytest.MonkeyPatch, get) -> None:
    monkeypatch.setattr(
        uploader,
        "requests",
        SimpleNamespace(
            get=get,
            RequestException=RuntimeError,
            Session=lambda: object(),
        ),
    )


def test_target_preflight_skips_identical_bytes_and_allows_404_or_410(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _operation("catalog/01_main/123456/existing.jpg", b"existing")
    missing = _operation("catalog/01_main/123456/missing.jpg", b"missing")
    gone = _operation("catalog/01_main/123456/gone.jpg", b"gone")

    def fake_get(url: str, **_kwargs):
        if url.endswith("existing.jpg"):
            return _Response(200, b"existing", url)
        if url.endswith("missing.jpg"):
            return _Response(404, b"", url)
        return _Response(410, b"", url)

    _mock_requests(monkeypatch, fake_get)

    result = uploader.preflight_public_images(
        store_base="https://store.example",
        operations=[existing, missing, gone],
    )

    assert [item["state"] for item in result] == [
        "verified_existing",
        "upload_required",
        "upload_required",
    ]
    assert [item["upload_required"] for item in result] == [False, True, True]


@pytest.mark.parametrize("status_code", [401, 403, 500, 503])
def test_target_preflight_rejects_ambiguous_http_status(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    operation = _operation("catalog/01_main/123456/target.jpg", b"target")
    _mock_requests(
        monkeypatch,
        lambda url, **_kwargs: _Response(status_code, b"", url),
    )
    results: list[dict] = []

    with pytest.raises(UploadError, match="ambiguous"):
        uploader.preflight_public_images(
            store_base="https://store.example",
            operations=[operation],
            results=results,
        )

    assert results[0]["state"] == "ambiguous_error"
    assert results[0]["upload_required"] is False


def test_target_preflight_rejects_existing_different_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _operation("catalog/01_main/123456/target.jpg", b"approved")
    _mock_requests(
        monkeypatch,
        lambda url, **_kwargs: _Response(200, b"different", url),
    )
    results: list[dict] = []

    with pytest.raises(UploadError, match="different bytes"):
        uploader.preflight_public_images(
            store_base="https://store.example",
            operations=[operation],
            results=results,
        )

    assert results[0]["state"] == "conflict"
    assert results[0]["observed_hash"] == hashlib.sha256(b"different").hexdigest()


def test_target_preflight_rejects_redirect_even_when_bytes_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _operation("catalog/01_main/123456/target.jpg", b"approved")
    _mock_requests(
        monkeypatch,
        lambda _url, **kwargs: (
            _Response(
                200,
                b"approved",
                "https://store.example/image/catalog/01_main/123456/legacy.jpg",
            )
            if kwargs.get("allow_redirects") is False
            else pytest.fail("image checks must never follow redirects")
        ),
    )
    results: list[dict] = []

    with pytest.raises(UploadError, match="redirected away"):
        uploader.preflight_public_images(
            store_base="https://store.example",
            operations=[operation],
            results=results,
        )

    assert results[0]["state"] == "redirect_rejected"


def _manifest(
    tmp_path: Path, *, operation: str = "apply"
) -> tuple[Path, Path]:
    now = datetime.now(timezone.utc)
    model = "123456"
    source = tmp_path / "legacy.jpg"
    source.write_bytes(b"legacy")
    target = tmp_path / "approved.jpg"
    target.write_bytes(b"approved")
    run_dir = tmp_path / "migration-run"
    manifest = run_dir / operation / "reports" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    target_identity = uploader.compute_opencart_target_identity(
        store_base="https://store.example",
        admin_path="/admin/index.php",
        profile="unbound",
    )
    operations = [
        {
            "model": model,
            "position": 1,
            "old_path": f"catalog/01_main/{model}/legacy.jpg",
            "new_path": f"catalog/01_main/{model}/{target.name}",
            "source_file": str(source),
            "source_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
            "target_file": str(target),
            "target_hash": hashlib.sha256(target.read_bytes()).hexdigest(),
            "original_retained": True,
        }
    ]
    scope = {
        "model": model,
        "csv_sha256": "c" * 64,
        "headers": ["Model", "Image", "Additional Images"],
        "image_operations_hash": uploader._canonical_content_hash(operations),
    }
    claim = (
        run_dir / "apply.claim.json"
        if operation == "apply"
        else run_dir / "rollback" / "claims" / f"{model}.claim.json"
    )
    claim.parent.mkdir(parents=True, exist_ok=True)
    claim.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "operation": operation,
                "migration_run_id": "migration-run",
                "snapshot_id": "snapshot-001",
                "approval_hash": "a" * 64,
                "plan_hash": "b" * 64,
                "target_identity": target_identity,
                "claimed_at": (now - timedelta(seconds=5)).isoformat(),
                "one_shot": True,
                "scopes": [scope],
            }
        ),
        encoding="utf-8",
    )
    authorization = {
        "schema_version": "1.0",
        "operation": operation,
        "migration_run_id": "migration-run",
        "snapshot_id": "snapshot-001",
        "approval_hash": "a" * 64,
        "plan_hash": "b" * 64,
        "target_identity": target_identity,
        **scope,
        "claim_path": str(claim),
        "claim_hash": hashlib.sha256(claim.read_bytes()).hexdigest(),
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
    }
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "model": model,
                "authorization": authorization,
                "operations": operations,
            }
        ),
        encoding="utf-8",
    )
    return manifest, target


def _args(tmp_path: Path, manifest: Path) -> argparse.Namespace:
    return argparse.Namespace(
        model="123456",
        manifest=str(manifest),
        repo_root=str(tmp_path),
        report_file=str(tmp_path / "report.json"),
    )


@pytest.mark.parametrize("operation", ["apply", "rollback"])
def test_manifest_accepts_exact_run_bound_authorization(
    tmp_path: Path, operation: str
) -> None:
    manifest, _target = _manifest(tmp_path, operation=operation)

    operations, authorization = uploader.load_manifest(manifest, "123456")

    assert authorization["operation"] == operation
    assert authorization["model"] == "123456"
    assert authorization["image_operations_hash"] == uploader._canonical_content_hash(
        json.loads(manifest.read_text(encoding="utf-8"))["operations"]
    )
    assert len(operations) == 1


def test_image_authorization_is_consumed_once(tmp_path: Path) -> None:
    manifest, _target = _manifest(tmp_path)
    _operations, authorization = uploader.load_manifest(manifest, "123456")

    first = uploader.consume_image_authorization(manifest, authorization)
    assert Path(first["marker"]).is_file()
    with pytest.raises(UploadError, match="already consumed"):
        uploader.consume_image_authorization(manifest, authorization)


def test_manifest_rejects_expired_image_authorization(tmp_path: Path) -> None:
    manifest, _target = _manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    payload["authorization"]["issued_at"] = (
        now - timedelta(hours=2)
    ).isoformat()
    payload["authorization"]["expires_at"] = (
        now - timedelta(hours=1)
    ).isoformat()
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(UploadError, match="expired"):
        uploader.load_manifest(manifest, "123456")


def test_manifest_rejects_operation_tampering_after_authorization(
    tmp_path: Path,
) -> None:
    manifest, _target = _manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["operations"][0]["position"] = 2
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(UploadError, match="operations no longer match"):
        uploader.load_manifest(manifest, "123456")


def test_manifest_rechecks_authorized_source_bytes(tmp_path: Path) -> None:
    manifest, _target = _manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    source = Path(payload["operations"][0]["source_file"])
    source.write_bytes(b"changed-after-authorization")

    with pytest.raises(UploadError, match="source hash changed"):
        uploader.load_manifest(manifest, "123456")


def test_manifest_rejects_authorization_without_exact_claim_scope(
    tmp_path: Path,
) -> None:
    manifest, _target = _manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    claim_path = Path(payload["authorization"]["claim_path"])
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    claim["scopes"][0]["csv_sha256"] = "d" * 64
    claim_path.write_text(json.dumps(claim), encoding="utf-8")
    payload["authorization"]["claim_hash"] = hashlib.sha256(
        claim_path.read_bytes()
    ).hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(UploadError, match="no exact claim scope"):
        uploader.load_manifest(manifest, "123456")


def test_manifest_rejects_extra_authorization_key(tmp_path: Path) -> None:
    manifest, _target = _manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["authorization"]["unreviewed"] = True
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(UploadError, match="invalid exact shape"):
        uploader.load_manifest(manifest, "123456")


def test_manifest_rejects_claim_outside_migration_run(tmp_path: Path) -> None:
    manifest, _target = _manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    original_claim = Path(payload["authorization"]["claim_path"])
    external_claim = tmp_path / "outside-claim.json"
    external_claim.write_bytes(original_claim.read_bytes())
    payload["authorization"]["claim_path"] = str(external_claim)
    payload["authorization"]["claim_hash"] = hashlib.sha256(
        external_claim.read_bytes()
    ).hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(UploadError, match="outside its run"):
        uploader.load_manifest(manifest, "123456")


def test_target_identity_binding_is_checked_before_public_or_admin_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, _target = _manifest(tmp_path)
    args = _args(tmp_path, manifest)
    monkeypatch.setattr(uploader, "parse_args", lambda: args)
    monkeypatch.setattr(
        uploader,
        "resolve_opencart_config",
        lambda **_kwargs: {
            "store_base": "https://other-store.example",
            "admin_path": "/admin/index.php",
            "username": "",
            "password": "",
        },
    )
    public_calls: list[str] = []

    def unexpected_get(url: str, **_kwargs):
        public_calls.append(url)
        raise AssertionError("public access must not start")

    _mock_requests(monkeypatch, unexpected_get)

    with pytest.raises(UploadError, match="authorization target"):
        uploader.main()

    assert public_calls == []
    report = json.loads(Path(args.report_file).read_text(encoding="utf-8"))
    assert report["write_state"]["external_write_attempted"] is False


def test_conflict_failure_writes_atomic_machine_report_before_admin_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, _target = _manifest(tmp_path)
    args = _args(tmp_path, manifest)
    monkeypatch.setattr(uploader, "parse_args", lambda: args)
    monkeypatch.setattr(
        uploader,
        "resolve_opencart_config",
        lambda **_kwargs: {
            "store_base": "https://store.example",
            "admin_path": "/admin/index.php",
            "username": "",
            "password": "",
        },
    )
    _mock_requests(
        monkeypatch,
        lambda url, **_kwargs: _Response(200, b"different", url),
    )
    replace_calls: list[tuple[Path, Path]] = []
    real_replace = uploader.os.replace

    def recording_replace(source, destination):
        replace_calls.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(uploader.os, "replace", recording_replace)

    with pytest.raises(UploadError, match="different bytes"):
        uploader.main()

    report_path = Path(args.report_file)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert replace_calls[-1][1] == report_path
    assert replace_calls[-1][0] != report_path
    assert report["ok"] is False
    assert report["status"] == "failed"
    assert report["target_preflight"][0]["state"] == "conflict"
    assert report["write_state"]["external_write_attempted"] is False
    assert report["write_state"]["upload_attempted"] is False
    assert not list(tmp_path.glob(".report.json.*.tmp"))


def test_post_upload_verification_failure_records_confirmed_write_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, _target = _manifest(tmp_path)
    args = _args(tmp_path, manifest)
    monkeypatch.setattr(uploader, "parse_args", lambda: args)
    monkeypatch.setattr(
        uploader,
        "resolve_opencart_config",
        lambda **_kwargs: {
            "store_base": "https://store.example",
            "admin_path": "/admin/index.php",
            "username": "operator",
            "password": "secret",
        },
    )
    responses = iter(
        [
            _Response(
                404,
                b"",
                "https://store.example/image/catalog/01_main/123456/approved.jpg",
            ),
            _Response(
                503,
                b"",
                "https://store.example/image/catalog/01_main/123456/approved.jpg",
            ),
        ]
    )
    _mock_requests(monkeypatch, lambda _url, **_kwargs: next(responses))
    monkeypatch.setattr(uploader, "login", lambda *_args: "token")
    monkeypatch.setattr(
        uploader, "permission_probe", lambda *_args: {"can_modify": True}
    )
    monkeypatch.setattr(uploader, "ensure_remote_nested_dir", lambda *_args: None)
    monkeypatch.setattr(uploader, "upload_files", lambda *_args: {"success": True})

    with pytest.raises(UploadError, match="verification failed"):
        uploader.main()

    report = json.loads(Path(args.report_file).read_text(encoding="utf-8"))
    state = report["write_state"]
    expected_path = "catalog/01_main/123456/approved.jpg"
    assert report["ok"] is False
    assert state["external_write_attempted"] is True
    assert state["upload_attempted"] is True
    assert state["upload_confirmed"] is True
    assert state["upload_outcome"] == "confirmed"
    assert state["uploaded_paths"] == [expected_path]
    assert state["post_upload_verification_attempted"] is True
    assert state["post_upload_verification_complete"] is False
    assert state["verified_paths"] == []
    assert report["public_hash_verification"][0]["state"] == "verification_failed"
