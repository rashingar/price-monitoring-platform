#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# See opencart_upload_images.py: this entry point is executed from Git Bash,
# so bootstrap native Python import paths instead of relying on PYTHONPATH.
APP_ROOT = Path(__file__).resolve().parents[1]
for import_root in (APP_ROOT, APP_ROOT / "src"):
    import_root_str = str(import_root)
    if import_root_str not in sys.path:
        sys.path.insert(0, import_root_str)

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from product_factory.publish_gallery_assets import (
    PublishGalleryResolutionError,
    resolve_publish_gallery_assets,
)
from tools.opencart_config import (
    compute_opencart_target_identity,
    resolve_opencart_config,
)

DEFAULT_HEADLESS = True
MIGRATION_AUTHORIZATION_TTL_SECONDS = 30 * 60


class ImportErrorRuntime(RuntimeError):
    pass


def discover_repo_root(explicit_repo_root: str | None) -> Path:
    candidates = []
    if explicit_repo_root:
        candidates.append(Path(explicit_repo_root).expanduser().resolve())

    env_root = os.environ.get("OPENCART_PIPELINE_REPO_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser().resolve())

    def walk_up(p: Path):
        return [p, *p.parents]

    candidates.extend(walk_up(Path.cwd().resolve()))
    candidates.extend(walk_up(Path(__file__).resolve().parent))

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (
            (candidate / ".git").exists()
            or (candidate / "products").is_dir()
            or (candidate / "work").is_dir()
        ):
            return candidate

    raise ImportErrorRuntime(
        "Could not auto-detect repo root. Pass --repo-root or set OPENCART_PIPELINE_REPO_ROOT."
    )


def resolve_csv_path(repo_root: Path, model: str, explicit_csv: str | None) -> Path:
    if explicit_csv:
        path = Path(explicit_csv).expanduser().resolve()
    else:
        path = (repo_root / "products" / f"{model}.csv").resolve()

    if not path.exists() or not path.is_file():
        raise ImportErrorRuntime(f"CSV file not found: {path}")

    return path


def normalize_admin_path(admin_path: str) -> str:
    value = (admin_path or "").strip().replace("\\", "/")
    if not value:
        return "/index.php"
    if re.match(r"^[A-Za-z]:/", value):
        parts = [part for part in value.split("/") if part]
        if len(parts) >= 2 and parts[-1].lower() == "index.php":
            return "/" + "/".join(parts[-2:])
    if "://" in value:
        return urlparse(value).path or "/index.php"
    return value if value.startswith("/") else f"/{value}"


def build_admin_index(store_base: str, admin_path: str) -> str:
    normalized_admin_path = normalize_admin_path(admin_path)
    return f"{store_base.rstrip('/')}/{normalized_admin_path.lstrip('/')}"


def csv_contract_check(
    csv_path: Path,
    model: str,
    *,
    repo_root: Path,
    allow_partial_csv: bool = False,
) -> dict[str, Any]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        headers = reader.fieldnames or []

    if not rows:
        raise ImportErrorRuntime(f"CSV has no data rows: {csv_path}")

    required = (
        ["model"] if allow_partial_csv else ["model", "image", "additional_image"]
    )
    missing = [h for h in required if h not in headers]
    if missing:
        raise ImportErrorRuntime(f"CSV missing required columns: {missing}")
    if len(headers) != len(set(headers)):
        raise ImportErrorRuntime("CSV contains duplicate headers.")
    if allow_partial_csv:
        if len(rows) != 1:
            raise ImportErrorRuntime(
                "Partial migration CSV must contain exactly one data row."
            )
        row_model = str(rows[0].get("model") or "").strip()
        if not re.fullmatch(r"[0-9]{6}", row_model) or row_model != model:
            raise ImportErrorRuntime(
                "Partial migration CSV model must be the exact requested six-digit model."
            )
        protected = {"price", "quantity", "status", "stock_status", "active"}
        if protected & set(headers):
            raise ImportErrorRuntime(
                "Partial migration CSV contains protected catalog columns."
            )

    assets = []
    if not allow_partial_csv:
        try:
            assets = resolve_publish_gallery_assets(model, csv_path, repo_root / "work")
        except PublishGalleryResolutionError as exc:
            raise ImportErrorRuntime(str(exc)) from exc

    return {
        "headers": headers,
        "row_count": len(rows),
        "first_row_model": str(rows[0].get("model") or ""),
        "first_row_image": assets[0].csv_public_path if assets else "",
        "first_row_additional_image": ":::".join(
            asset.csv_public_path for asset in assets[1:]
        ),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automate Karapuz CSV Product Import via Playwright."
    )
    parser.add_argument("--model", required=True, help="6-digit product model")
    parser.add_argument("--repo-root", default=None, help="Optional repo root")
    parser.add_argument(
        "--csv-file", default=None, help="Optional explicit CSV file path"
    )
    parser.add_argument("--store-base", default=None)
    parser.add_argument("--admin-path", default=None)
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--expected-target-identity", default=None)
    parser.add_argument("--expected-csv-sha256", default=None)
    parser.add_argument(
        "--headless", dest="headless", action="store_true", default=DEFAULT_HEADLESS
    )
    parser.add_argument("--headed", dest="headless", action="store_false")
    parser.add_argument("--slow-mo-ms", type=int, default=0)
    parser.add_argument(
        "--dry-run", action="store_true", help="Stop on Step 2 before final import"
    )
    parser.add_argument(
        "--allow-partial-csv",
        action="store_true",
        help="Allow update CSVs that contain only model plus selected fields",
    )
    parser.add_argument(
        "--migration-authorization-file",
        default=None,
        help=(
            "Run-bound machine authorization required for a non-dry-run "
            "--allow-partial-csv migration import"
        ),
    )
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--poll-interval-sec", type=float, default=2.0)
    parser.add_argument("--max-wait-sec", type=int, default=900)
    parser.add_argument(
        "--report-file",
        default=None,
        help="Optional report file. Default: work/{model}/import.opencart.json",
    )
    return parser.parse_args()


def login(
    page, admin_index: str, username: str, password: str, timeout_ms: int
) -> None:
    login_url = f"{admin_index}?route=common/login"
    page.goto(login_url, wait_until="domcontentloaded", timeout=timeout_ms)

    user = page.locator('input[name="username"]')
    pwd = page.locator('input[name="password"]')

    user.wait_for(state="visible", timeout=timeout_ms)
    user.fill(username)
    pwd.fill(password)

    page.locator('button[type="submit"], input[type="submit"]').first.click()
    wait_for_load_state_if_possible(page, "networkidle", timeout_ms)

    if "route=common/login" in page.url:
        raise ImportErrorRuntime(
            "Admin login appears to have failed; still on login route."
        )


def _append_session_token(target_url: str, current_url: str) -> str:
    user_token = parse_qs(urlparse(current_url).query).get("user_token", [None])[0]
    if not user_token:
        return target_url

    parsed = urlparse(target_url)
    query = parse_qs(parsed.query)
    query["user_token"] = [user_token]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def open_import_page(
    page, admin_index: str, profile: str, timeout_ms: int
) -> dict[str, Any]:
    url = _append_session_token(
        f"{admin_index}?route=extension/ka_extensions/csv_product_import/ka_product_import",
        page.url,
    )
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    wait_for_load_state_if_possible(page, "networkidle", timeout_ms)

    page.locator('select[name="profile_id"]').wait_for(
        state="visible", timeout=timeout_ms
    )
    page.locator('select[name="profile_id"]').select_option(label=profile)
    page.locator('input[value="Load"], button:has-text("Load")').first.click()
    wait_for_load_state_if_possible(page, "networkidle", timeout_ms)

    # allow success banner/profile change to settle
    try:
        page.locator("text=Profile has been loaded successfully").wait_for(timeout=5000)
    except PlaywrightTimeoutError:
        pass
    return inspect_import_profile_safety(page)


def step1_upload_and_next(page, csv_path: Path, timeout_ms: int) -> None:
    page.locator('#input_file, input[type="file"][name="file"]').set_input_files(
        str(csv_path)
    )

    # ensure Local computer is selected if radio exists
    local_radio = page.locator(
        'input[type="radio"][value="local"], input[type="radio"][value="local computer"]'
    )
    if local_radio.count() > 0:
        local_radio.first.check(force=True)

    next_button = page.locator(
        'button[form="form-step1"]:has-text("Next"), button[type="submit"][form="form-step1"]'
    )
    next_button.first.click()
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    wait_for_load_state_if_possible(page, "networkidle", timeout_ms)

    if "step2" not in page.url:
        raise ImportErrorRuntime(
            f"Expected to reach Step 2, but current URL is: {page.url}"
        )


def assert_step2_mapping(
    page,
    profile: str,
    timeout_ms: int,
    expected_headers: list[str] | None = None,
    prior_profile_safety: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    page.locator("#form-step2").wait_for(state="visible", timeout=timeout_ms)
    model_select = page.locator('select[name="fields[model]"]')
    model_select.wait_for(state="visible", timeout=timeout_ms)
    selected_text = model_select.locator("option:checked").inner_text().strip()

    profile_name = page.locator('input[name="profile_name"]').input_value().strip()

    expected = list(expected_headers or ["model"])
    observed_mappings: dict[str, str] = {}
    selects = page.locator('#form-step2 select[name^="fields["]')
    for index in range(selects.count()):
        select = selects.nth(index)
        name = str(select.get_attribute("name") or "")
        match = re.fullmatch(r"fields\[(.+)]", name)
        if match is None:
            continue
        observed_mappings[match.group(1)] = (
            select.locator("option:checked").inner_text().strip()
        )
    missing_or_mismatched = {
        header: observed_mappings.get(header, "")
        for header in expected
        if observed_mappings.get(header, "") != header
    }
    strict_partial = expected_headers is not None
    protected_targets = {"price", "quantity", "status", "stock_status", "active"}
    ignored_mapping_values = {
        "",
        "-",
        "--",
        "ignore",
        "ignored",
        "none",
        "not assigned",
        "not imported",
        "do not import",
        "skip",
    }
    unexpected_mappings = {
        source: target
        for source, target in observed_mappings.items()
        if strict_partial
        and source not in expected
        and target.strip().casefold() not in ignored_mapping_values
    }
    protected_mappings = {
        source: target
        for source, target in observed_mappings.items()
        if strict_partial
        and target.strip().casefold() not in ignored_mapping_values
        and (
            source.strip().casefold() in protected_targets
            or target.strip().casefold() in protected_targets
        )
    }
    profile_safety = combine_partial_profile_safety(
        prior_profile_safety or {}, inspect_import_profile_safety(page)
    )

    return {
        "profile_name": profile_name,
        "selected_model_mapping": selected_text,
        "profile_expected": profile,
        "expected_headers": expected,
        "observed_mappings": observed_mappings,
        "missing_or_mismatched": missing_or_mismatched,
        "unexpected_mappings": unexpected_mappings,
        "protected_mappings": protected_mappings,
        "profile_safety": profile_safety,
        "mapping_ok": (
            selected_text == "model"
            and profile_name == profile
            and not missing_or_mismatched
            and (not strict_partial or not unexpected_mappings)
            and (not strict_partial or not protected_mappings)
            and (not strict_partial or profile_safety.get("safe") is True)
        ),
    }


_DESTRUCTIVE_PROFILE_RE = re.compile(
    r"(?i)(delete|deletion|disable|disabled|disabling|deactivate|deactivated|deactivation|remove|removal)"
)
_DELETE_PROFILE_RE = re.compile(r"(?i)(delete|deletion|remove|removal)")
_DISABLE_PROFILE_RE = re.compile(
    r"(?i)(disable|disabled|disabling|deactivate|deactivated|deactivation)"
)
_CREATE_PROFILE_RE = re.compile(
    r"(?i)(create|creation|insert|add[_ -]?new|new[_ -]?products?)"
)
_NEGATED_PROFILE_RE = re.compile(
    r"(?i)(do[_ -]?not|don't|never|skip|prevent|update[_ -]?only|existing[_ -]?only|only[_ -]?existing)"
)
_SAFE_PROFILE_VALUE_RE = re.compile(
    r"(?i)(?:^|\b)(0|false|off|no|none|keep|ignore|do not|don't|never)(?:\b|$)"
)
_UNSAFE_PROFILE_VALUE_RE = re.compile(
    r"(?i)(?:^|\b)(1|true|on|yes|delete|disable|disabled|deactivate|remove)(?:\b|$)"
)


def inspect_import_profile_safety(page) -> dict[str, Any]:
    """Collect non-secret import-option controls for fail-closed evaluation."""

    controls: list[dict[str, Any]] = []
    locator = page.locator("form input, form select, form textarea")
    for index in range(locator.count()):
        control = locator.nth(index)
        raw = control.evaluate(
            """element => ({
                tag: (element.tagName || '').toLowerCase(),
                type: (element.type || '').toLowerCase(),
                name: element.name || '',
                id: element.id || '',
                value: element.value || '',
                checked: Boolean(element.checked),
                disabled: Boolean(element.disabled),
                selected_text: element.tagName === 'SELECT' && element.selectedIndex >= 0
                    ? (element.options[element.selectedIndex].text || '') : '',
                label: Array.from(element.labels || []).map(item => item.innerText || '').join(' '),
                parent_text: element.parentElement ? (element.parentElement.innerText || '').slice(0, 500) : ''
            })"""
        )
        if not isinstance(raw, Mapping):
            continue
        item = {str(key): value for key, value in raw.items()}
        name = str(item.get("name") or "")
        if name.startswith("fields[") or str(item.get("type") or "") in {
            "password",
            "file",
            "submit",
            "button",
        }:
            continue
        controls.append(item)
    return evaluate_partial_profile_safety(controls)


def evaluate_partial_profile_safety(
    controls: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Require create/delete/disable controls to be present and safely bounded."""

    relevant: list[dict[str, Any]] = []
    unsafe: list[dict[str, Any]] = []
    concepts: set[str] = set()
    seen: set[tuple[str, str, str]] = set()
    for raw in controls:
        if not isinstance(raw, Mapping) or raw.get("disabled") is True:
            continue
        name = str(raw.get("name") or "")
        control_id = str(raw.get("id") or "")
        control_type = str(raw.get("type") or raw.get("tag") or "").casefold()
        label = str(raw.get("label") or "")
        selected = " ".join(
            str(raw.get(key) or "") for key in ("value", "selected_text")
        ).strip()
        # Parent text can include sibling controls with unrelated negations.
        # Bind concepts to the control's own stable identity/label and bind the
        # selected safety state only to its own label/value.
        context = " ".join((name, control_id, label))
        if not (
            _DESTRUCTIVE_PROFILE_RE.search(context)
            or _CREATE_PROFILE_RE.search(context)
        ):
            continue
        if control_type == "radio" and raw.get("checked") is not True:
            # Only the selected member of a radio group has operational effect.
            continue
        if _DELETE_PROFILE_RE.search(context):
            concepts.add("delete")
        if _DISABLE_PROFILE_RE.search(context):
            concepts.add("disable")
        if _CREATE_PROFILE_RE.search(context):
            concepts.add("create")
        negated = bool(_NEGATED_PROFILE_RE.search(" ".join((label, selected))))
        if control_type in {"checkbox", "radio"}:
            enabled = raw.get("checked") is True
            state = (
                "safe_on"
                if enabled and negated
                else "unsafe_enabled"
                if enabled
                else "ambiguous_negated_off"
                if negated
                else "safe_off"
            )
        else:
            safe_selected = bool(_SAFE_PROFILE_VALUE_RE.search(selected))
            unsafe_selected = bool(_UNSAFE_PROFILE_VALUE_RE.search(selected))
            if safe_selected and unsafe_selected:
                state = "ambiguous_mixed_safe_and_unsafe_tokens"
            elif unsafe_selected:
                state = "unsafe_enabled"
            elif safe_selected:
                state = "safe_off"
            else:
                state = "ambiguous"
        evidence = {
            "name": name,
            "id": control_id,
            "type": control_type,
            "selected": selected[:160],
            "state": state,
        }
        dedupe_key = (name, control_id, state)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        relevant.append(evidence)
        if state not in {"safe_off", "safe_on"}:
            unsafe.append(evidence)
    missing_concepts = sorted({"create", "delete", "disable"} - concepts)
    return {
        "safe": not unsafe and not missing_concepts,
        "required_concepts": ["create", "delete", "disable"],
        "attested_concepts": sorted(concepts),
        "missing_concepts": missing_concepts,
        "unsafe_or_ambiguous": unsafe,
        "controls": relevant,
    }


def combine_partial_profile_safety(
    *reports: Mapping[str, Any],
) -> dict[str, Any]:
    concepts = {
        str(item)
        for report in reports
        for item in report.get("attested_concepts", [])
        if str(item)
    }
    controls = [
        dict(item)
        for report in reports
        for item in report.get("controls", [])
        if isinstance(item, Mapping)
    ]
    unsafe = [
        dict(item)
        for report in reports
        for item in report.get("unsafe_or_ambiguous", [])
        if isinstance(item, Mapping)
    ]
    missing = sorted({"create", "delete", "disable"} - concepts)
    return {
        "safe": not unsafe and not missing,
        "required_concepts": ["create", "delete", "disable"],
        "attested_concepts": sorted(concepts),
        "missing_concepts": missing,
        "unsafe_or_ambiguous": unsafe,
        "controls": controls,
    }


def step2_next(page, timeout_ms: int) -> None:
    next_button = page.locator(
        'button[form="form-step2"]:has-text("Next"), button[type="submit"][form="form-step2"]'
    )
    next_button.first.click()
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    wait_for_load_state_if_possible(page, "networkidle", timeout_ms)

    if "step3" not in page.url:
        raise ImportErrorRuntime(
            f"Expected to reach Step 3, but current URL is: {page.url}"
        )


def step3_monitor(
    page,
    timeout_ms: int,
    poll_interval_sec: float,
    max_wait_sec: int,
    *,
    admin_path: str = "",
) -> dict[str, Any]:
    page.locator("#import_status").wait_for(state="visible", timeout=timeout_ms)

    started_at = time.time()
    final_status = None
    status_text = None
    messages_html = None
    counters: dict[str, str] = {}

    while True:
        elapsed = time.time() - started_at
        if elapsed > max_wait_sec:
            raise ImportErrorRuntime(
                f"Timed out waiting for import completion after {max_wait_sec}s"
            )

        status_text = page.locator("#import_status").inner_text().strip()
        try:
            messages_html = page.locator("#scroll").inner_html()
        except Exception:
            messages_html = ""

        # collect visible counters from left column table, if present
        labels = [
            "Completion at",
            "Time Passed",
            "Lines Processed",
            "Products Created",
            "Products Updated",
            "Products Deleted",
            "Products Disabled",
            "Categories Created",
        ]
        for label in labels:
            cell = page.locator(f'text="{label}"').first
            if cell.count() > 0:
                try:
                    row = cell.locator("xpath=ancestor::tr[1]")
                    tds = row.locator("td").all_inner_texts()
                    if len(tds) >= 2:
                        counters[label] = tds[1].strip()
                except Exception:
                    pass

        # derive status from buttons/displayed text
        if (
            page.locator("#buttons_completed:visible").count() > 0
            or "complete" in status_text.lower()
        ):
            final_status = "completed"
            break
        if (
            page.locator("#buttons_stopped:visible").count() > 0
            or "stopped" in status_text.lower()
        ):
            final_status = "stopped"
            break
        if "server script error" in status_text.lower():
            final_status = "fatal_error"
            break
        if "fatal import error" in status_text.lower():
            final_status = "error"
            break

        time.sleep(poll_interval_sec)

    return {
        "final_status": final_status,
        "status_text": redact_sensitive_text(status_text or "", admin_path=admin_path),
        "elapsed_sec": round(time.time() - started_at, 2),
        # Server-supplied monitor HTML can contain admin routes, session tokens,
        # or extension diagnostics. Persist only whether it was present.
        "messages_present": bool(messages_html),
        "counters": counters,
    }


def write_report(report_path: Path, payload: dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _partial_import_safety(
    monitor: Mapping[str, Any], *, headers: list[str]
) -> dict[str, Any]:
    counters = monitor.get("counters", {})
    counters = counters if isinstance(counters, Mapping) else {}
    lines_processed = _counter_int(counters.get("Lines Processed"))
    created = _counter_int(counters.get("Products Created"))
    updated = _counter_int(counters.get("Products Updated"))
    deleted = _counter_int(counters.get("Products Deleted"))
    disabled = _counter_int(counters.get("Products Disabled"))
    categories_created = _counter_int(counters.get("Categories Created"))
    protected = {"price", "quantity", "status", "stock_status", "active"}
    return {
        "lines_processed": lines_processed,
        "products_created": created,
        "products_updated": updated,
        "products_deleted": deleted,
        "products_disabled": disabled,
        "categories_created": categories_created,
        "destructive_counts_verified": deleted == 0 and disabled == 0,
        "scope_counts_verified": (
            lines_processed == 1
            and created == 0
            and updated == 1
            and categories_created == 0
        ),
        "protected_columns_absent": not bool(protected & set(headers)),
    }


def _counter_int(value: object) -> int | None:
    match = re.search(r"-?[0-9]+", str(value or ""))
    return int(match.group(0)) if match else None


_HASH_RE = re.compile(r"[0-9a-f]{64}")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_TARGET_ID_RE = re.compile(r"opencart-target:sha256:[0-9a-f]{64}")
_AUTHORIZATION_KEYS = {
    "schema_version",
    "operation",
    "migration_run_id",
    "snapshot_id",
    "approval_hash",
    "plan_hash",
    "target_identity",
    "model",
    "csv_sha256",
    "headers",
    "image_operations_hash",
    "claim_path",
    "claim_hash",
    "issued_at",
    "expires_at",
}
_CLAIM_KEYS = {
    "schema_version",
    "operation",
    "migration_run_id",
    "snapshot_id",
    "approval_hash",
    "plan_hash",
    "target_identity",
    "claimed_at",
    "one_shot",
    "scopes",
}
_SCOPE_KEYS = {
    "model",
    "csv_sha256",
    "headers",
    "image_operations_hash",
}


def validate_migration_authorization(
    authorization_path: Path,
    *,
    model: str,
    contract: Mapping[str, Any],
    target_identity: str,
) -> dict[str, Any]:
    """Validate a partial-import authorization against current immutable inputs."""

    authorization_path = authorization_path.expanduser().resolve()
    authorization = _read_authorization_json(
        authorization_path, label="migration authorization"
    )
    if set(authorization) != _AUTHORIZATION_KEYS:
        raise ImportErrorRuntime(
            "Migration authorization has an invalid exact field set."
        )
    if authorization.get("schema_version") != "1.0":
        raise ImportErrorRuntime("Migration authorization schema_version must be 1.0.")
    if authorization.get("operation") not in {"apply", "rollback"}:
        raise ImportErrorRuntime(
            "Migration authorization operation must be apply or rollback."
        )
    for key in ("migration_run_id", "snapshot_id"):
        if not _ID_RE.fullmatch(str(authorization.get(key) or "")):
            raise ImportErrorRuntime(f"Migration authorization {key} is invalid.")
    run_id = str(authorization["migration_run_id"])
    run_roots = [parent for parent in authorization_path.parents if parent.name == run_id]
    if not run_roots:
        raise ImportErrorRuntime(
            "Migration authorization file is outside its declared migration run."
        )
    run_root = run_roots[0]
    for key in (
        "approval_hash",
        "plan_hash",
        "csv_sha256",
        "image_operations_hash",
        "claim_hash",
    ):
        if not _HASH_RE.fullmatch(str(authorization.get(key) or "")):
            raise ImportErrorRuntime(f"Migration authorization {key} is invalid.")
    if not _TARGET_ID_RE.fullmatch(str(authorization.get("target_identity") or "")):
        raise ImportErrorRuntime("Migration authorization target_identity is invalid.")
    issued_at, expires_at = _validate_authorization_window(
        authorization.get("issued_at"), authorization.get("expires_at")
    )

    headers = authorization.get("headers")
    if (
        not isinstance(headers, list)
        or not headers
        or any(not isinstance(header, str) or not header for header in headers)
        or len(headers) != len(set(headers))
    ):
        raise ImportErrorRuntime("Migration authorization headers are invalid.")

    expected_scope = {
        "model": model,
        "csv_sha256": str(contract.get("csv_sha256") or ""),
        "headers": list(contract.get("headers") or []),
        "image_operations_hash": str(authorization["image_operations_hash"]),
    }
    if authorization.get("model") != model:
        raise ImportErrorRuntime("Migration authorization model does not match the CSV.")
    if authorization.get("csv_sha256") != expected_scope["csv_sha256"]:
        raise ImportErrorRuntime("Migration authorization CSV hash does not match.")
    if headers != expected_scope["headers"]:
        raise ImportErrorRuntime(
            "Migration authorization ordered CSV headers do not match."
        )
    if authorization.get("target_identity") != target_identity:
        raise ImportErrorRuntime(
            "Migration authorization target identity does not match."
        )

    raw_claim_path = authorization.get("claim_path")
    if not isinstance(raw_claim_path, str) or not raw_claim_path.strip():
        raise ImportErrorRuntime("Migration authorization claim_path is invalid.")
    claim_path = Path(raw_claim_path).expanduser().resolve()
    try:
        claim_path.relative_to(run_root)
    except ValueError as exc:
        raise ImportErrorRuntime(
            "Migration authorization claim is outside its declared migration run."
        ) from exc
    if not claim_path.is_file():
        raise ImportErrorRuntime("Migration authorization claim is missing.")
    try:
        claim_bytes = claim_path.read_bytes()
    except OSError as exc:
        raise ImportErrorRuntime("Could not read migration claim JSON.") from exc
    if hashlib.sha256(claim_bytes).hexdigest() != authorization["claim_hash"]:
        raise ImportErrorRuntime("Migration authorization claim hash does not match.")
    try:
        raw_claim = json.loads(claim_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ImportErrorRuntime("Could not read migration claim JSON.") from exc
    if not isinstance(raw_claim, Mapping):
        raise ImportErrorRuntime("Migration claim must be a JSON object.")
    claim = dict(raw_claim)
    if set(claim) != _CLAIM_KEYS:
        raise ImportErrorRuntime("Migration claim has an invalid exact field set.")
    if claim.get("schema_version") != "1.0":
        raise ImportErrorRuntime("Migration claim schema_version must be 1.0.")
    if claim.get("operation") != authorization.get("operation"):
        raise ImportErrorRuntime("Migration claim operation does not match authorization.")
    if claim.get("one_shot") is not True:
        raise ImportErrorRuntime("Migration claim must assert one_shot=true.")
    if not _is_rfc3339(str(claim.get("claimed_at") or "")):
        raise ImportErrorRuntime("Migration claim claimed_at must be RFC3339.")
    claimed_at = _parse_rfc3339(str(claim["claimed_at"]), label="claim claimed_at")
    if issued_at < claimed_at:
        raise ImportErrorRuntime(
            "Migration authorization predates its immutable run claim."
        )
    for key in (
        "migration_run_id",
        "snapshot_id",
        "approval_hash",
        "plan_hash",
        "target_identity",
    ):
        if claim.get(key) != authorization.get(key):
            raise ImportErrorRuntime(
                f"Migration claim {key} does not match authorization."
            )

    scopes = claim.get("scopes")
    if not isinstance(scopes, list) or not scopes:
        raise ImportErrorRuntime("Migration claim scopes must be a non-empty array.")
    normalized_scopes: list[dict[str, Any]] = []
    seen_models: set[str] = set()
    for raw_scope in scopes:
        if not isinstance(raw_scope, Mapping) or set(raw_scope) != _SCOPE_KEYS:
            raise ImportErrorRuntime("Migration claim scope has an invalid exact shape.")
        scope = dict(raw_scope)
        scope_model = scope.get("model")
        if not isinstance(scope_model, str) or not re.fullmatch(r"[0-9]{6}", scope_model):
            raise ImportErrorRuntime("Migration claim scope model is invalid.")
        if scope_model in seen_models:
            raise ImportErrorRuntime("Migration claim contains duplicate model scopes.")
        seen_models.add(scope_model)
        for key in ("csv_sha256", "image_operations_hash"):
            if not _HASH_RE.fullmatch(str(scope.get(key) or "")):
                raise ImportErrorRuntime(f"Migration claim scope {key} is invalid.")
        scope_headers = scope.get("headers")
        if (
            not isinstance(scope_headers, list)
            or not scope_headers
            or any(
                not isinstance(header, str) or not header for header in scope_headers
            )
            or len(scope_headers) != len(set(scope_headers))
        ):
            raise ImportErrorRuntime("Migration claim scope headers are invalid.")
        normalized_scopes.append(scope)

    if expected_scope not in normalized_scopes:
        raise ImportErrorRuntime(
            "Migration authorization scope is not present in the run claim."
        )
    for key in _SCOPE_KEYS:
        if authorization.get(key) != expected_scope[key]:
            raise ImportErrorRuntime(
                f"Migration authorization {key} does not match its claimed scope."
            )

    return {
        "authorized": True,
        "schema_version": "1.0",
        "operation": authorization["operation"],
        "migration_run_id": authorization["migration_run_id"],
        "snapshot_id": authorization["snapshot_id"],
        "model": model,
        "approval_hash": authorization["approval_hash"],
        "plan_hash": authorization["plan_hash"],
        "target_identity": target_identity,
        "csv_sha256": authorization["csv_sha256"],
        "headers": list(headers),
        "image_operations_hash": authorization["image_operations_hash"],
        "claim_hash": authorization["claim_hash"],
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


def attest_partial_import_authorization(
    authorization_file: str | None,
    *,
    allow_partial_csv: bool,
    dry_run: bool,
    model: str,
    contract: Mapping[str, Any],
    target_identity: str,
) -> dict[str, Any] | None:
    """Require machine authorization only at the partial production boundary."""

    if not allow_partial_csv or dry_run:
        return None
    if not authorization_file:
        raise ImportErrorRuntime(
            "A non-dry-run partial migration import requires "
            "--migration-authorization-file."
        )
    return validate_migration_authorization(
        Path(authorization_file),
        model=model,
        contract=contract,
        target_identity=target_identity,
    )


def consume_migration_authorization(
    authorization_file: str,
    attestation: Mapping[str, Any],
    *,
    adapter: str,
) -> dict[str, Any]:
    """Atomically consume one model/adapter authorization before a live write."""

    _validate_authorization_window(
        attestation.get("issued_at"), attestation.get("expires_at")
    )

    authorization_path = Path(authorization_file).expanduser().resolve()
    run_id = str(attestation.get("migration_run_id") or "")
    run_roots = [parent for parent in authorization_path.parents if parent.name == run_id]
    if not run_roots:
        raise ImportErrorRuntime("Migration authorization is outside its run.")
    if adapter not in {"partial_import", "image_upload"}:
        raise ImportErrorRuntime("Migration authorization adapter is invalid.")
    marker = (
        run_roots[0]
        / "consumption"
        / f"{adapter}.{attestation.get('model')}.{attestation.get('claim_hash')}.json"
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "adapter": adapter,
        "operation": attestation.get("operation"),
        "migration_run_id": run_id,
        "snapshot_id": attestation.get("snapshot_id"),
        "model": attestation.get("model"),
        "claim_hash": attestation.get("claim_hash"),
        "csv_sha256": attestation.get("csv_sha256"),
        "consumed_at": datetime.now().astimezone().isoformat(),
    }
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ImportErrorRuntime(
            "Migration authorization was already consumed for this adapter/model; "
            "replay is forbidden."
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception as exc:
        # Leave an uncertain marker in place; replay must remain fail closed.
        raise ImportErrorRuntime(
            "Could not durably consume migration authorization."
        ) from exc
    return {**payload, "marker": str(marker)}


def _read_authorization_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ImportErrorRuntime(f"Could not read {label} JSON.") from exc
    if not isinstance(raw, Mapping):
        raise ImportErrorRuntime(f"{label.capitalize()} must be a JSON object.")
    return dict(raw)


def _is_rfc3339(value: str) -> bool:
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})",
        value,
    ):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _parse_rfc3339(value: str, *, label: str) -> datetime:
    if not _is_rfc3339(value):
        raise ImportErrorRuntime(f"Migration authorization {label} must be RFC3339.")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def _validate_authorization_window(
    issued_value: Any, expires_value: Any
) -> tuple[datetime, datetime]:
    issued = _parse_rfc3339(str(issued_value or ""), label="issued_at")
    expires = _parse_rfc3339(str(expires_value or ""), label="expires_at")
    now = datetime.now(timezone.utc)
    lifetime = (expires - issued).total_seconds()
    if (
        issued > now
        or expires <= now
        or lifetime <= 0
        or lifetime > MIGRATION_AUTHORIZATION_TTL_SECONDS
    ):
        raise ImportErrorRuntime(
            "Migration authorization is expired, future-dated, or exceeds its maximum lifetime."
        )
    return issued, expires


def redact_sensitive_url(value: str) -> str:
    parsed = urlparse(str(value or ""))
    query = parse_qs(parsed.query, keep_blank_values=True)
    for key in list(query):
        if key.casefold() in {
            "user_token",
            "token",
            "access_token",
            "password",
            "secret",
            "api_key",
        }:
            query[key] = ["<redacted>"]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def redact_sensitive_text(value: str, *, admin_path: str = "") -> str:
    redacted = re.sub(
        r"(?i)(user_token|access_token|token|password|secret|api_key)=([^&\s'\"]+)",
        r"\1=<redacted>",
        str(value or ""),
    )
    normalized_admin = str(admin_path or "").strip()
    if normalized_admin:
        for variant in {
            normalized_admin,
            normalized_admin.replace("\\", "/"),
            normalized_admin.strip("/\\"),
        }:
            if variant:
                redacted = redacted.replace(variant, "<redacted-admin-path>")
    return redacted


def wait_for_load_state_if_possible(page, state: str, timeout_ms: int) -> bool:
    try:
        page.wait_for_load_state(state, timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        return False


def main() -> int:
    args = parse_args()
    repo_root = discover_repo_root(args.repo_root)
    resolved_config = resolve_opencart_config(
        repo_root=repo_root,
        store_base=args.store_base,
        admin_path=args.admin_path,
        username=args.username,
        password=args.password,
        profile=args.profile,
    )
    target_identity = compute_opencart_target_identity(
        store_base=resolved_config["store_base"],
        admin_path=resolved_config["admin_path"],
        profile=resolved_config["profile"],
    )
    if (
        args.expected_target_identity is not None
        and args.expected_target_identity != target_identity
    ):
        raise ImportErrorRuntime(
            "Resolved OpenCart target does not match the expected migration target identity."
        )
    csv_path = resolve_csv_path(repo_root, args.model, args.csv_file)
    contract = csv_contract_check(
        csv_path,
        args.model,
        repo_root=repo_root,
        allow_partial_csv=args.allow_partial_csv,
    )
    if (
        args.expected_csv_sha256 is not None
        and args.expected_csv_sha256 != contract["csv_sha256"]
    ):
        raise ImportErrorRuntime(
            "Partial migration CSV hash does not match the orchestrator-approved patch."
        )
    authorization_attestation = attest_partial_import_authorization(
        args.migration_authorization_file,
        allow_partial_csv=args.allow_partial_csv,
        dry_run=args.dry_run,
        model=args.model,
        contract=contract,
        target_identity=target_identity,
    )
    if not resolved_config["username"] or not resolved_config["password"]:
        raise ImportErrorRuntime(
            "Missing admin credentials. Pass --username/--password or set OPENCART_ADMIN_USER and OPENCART_ADMIN_PASS."
        )
    admin_index = build_admin_index(
        resolved_config["store_base"], resolved_config["admin_path"]
    )
    report_path = (
        Path(args.report_file).expanduser().resolve()
        if args.report_file
        else (repo_root / "work" / args.model / "import.opencart.json")
    )

    result: dict[str, Any] = {
        "ok": False,
        "dry_run": bool(args.dry_run),
        "target_identity": target_identity,
        "profile": resolved_config["profile"],
        "csv_file": str(csv_path),
        "csv_contract": contract,
        "model": args.model,
    }
    if authorization_attestation is not None:
        result["migration_authorization"] = authorization_attestation

    print(
        json.dumps(
            {
                "model": args.model,
                "csv_file": str(csv_path),
                "profile": resolved_config["profile"],
                "target_identity": target_identity,
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=args.slow_mo_ms)
        context = browser.new_context()
        page = context.new_page()

        try:
            login(
                page,
                admin_index,
                resolved_config["username"],
                resolved_config["password"],
                args.timeout_ms,
            )
            result["login"] = {"ok": True, "state": "authenticated"}

            step1_profile_safety = open_import_page(
                page, admin_index, resolved_config["profile"], args.timeout_ms
            )
            result["step1_opened"] = {
                "ok": True,
                "state": "profile_loaded",
                "profile_safety": step1_profile_safety,
            }

            step1_upload_and_next(page, csv_path, args.timeout_ms)
            step2_info = assert_step2_mapping(
                page,
                resolved_config["profile"],
                args.timeout_ms,
                expected_headers=(contract["headers"] if args.allow_partial_csv else None),
                prior_profile_safety=step1_profile_safety,
            )
            result["step2"] = step2_info

            if not step2_info["mapping_ok"]:
                raise ImportErrorRuntime(
                    f"Unexpected Step 2 mapping/profile state: {json.dumps(step2_info, ensure_ascii=False)}"
                )

            if args.dry_run:
                result["ok"] = True
                result["message"] = (
                    "Dry run passed. Stopped on Step 2 before final import trigger."
                )
                write_report(report_path, result)
                print(f"Dry run OK. Report written to: {report_path}")
                return 0

            if hashlib.sha256(csv_path.read_bytes()).hexdigest() != contract[
                "csv_sha256"
            ]:
                raise ImportErrorRuntime(
                    "Partial migration CSV changed after mapping preflight."
                )
            if authorization_attestation is not None:
                current_attestation = attest_partial_import_authorization(
                    args.migration_authorization_file,
                    allow_partial_csv=args.allow_partial_csv,
                    dry_run=False,
                    model=args.model,
                    contract=contract,
                    target_identity=target_identity,
                )
                if current_attestation != authorization_attestation:
                    raise ImportErrorRuntime(
                        "Migration authorization changed after mapping preflight."
                    )
                result["migration_authorization_consumption"] = (
                    consume_migration_authorization(
                        str(args.migration_authorization_file),
                        current_attestation,
                        adapter="partial_import",
                    )
                )
                write_report(report_path, result)

            step2_next(page, args.timeout_ms)
            result["step3_opened"] = {"ok": True, "state": "import_triggered"}

            monitor = step3_monitor(
                page,
                args.timeout_ms,
                args.poll_interval_sec,
                args.max_wait_sec,
                admin_path=resolved_config["admin_path"],
            )
            result["step3"] = monitor

            if monitor["final_status"] != "completed":
                raise ImportErrorRuntime(
                    f"Import did not complete successfully: {monitor['final_status']}"
                )

            if args.allow_partial_csv:
                safety = _partial_import_safety(
                    monitor, headers=list(contract["headers"])
                )
                result["partial_import_safety"] = safety
                if not all(
                    safety[key]
                    for key in (
                        "destructive_counts_verified",
                        "scope_counts_verified",
                        "protected_columns_absent",
                    )
                ):
                    raise ImportErrorRuntime(
                        "Partial import did not prove an exact one-existing-product "
                        "update with protected fields absent and zero deletion/disable: "
                        f"{json.dumps(safety, ensure_ascii=False)}"
                    )

            result["ok"] = True
            write_report(report_path, result)
            print(f"Import OK. Report written to: {report_path}")
            return 0
        except PlaywrightTimeoutError as exc:
            result["ok"] = False
            result["error_type"] = "playwright_timeout"
            result["error"] = redact_sensitive_text(
                str(exc), admin_path=resolved_config["admin_path"]
            )
            result["route_state"] = "playwright_timeout"
            write_report(report_path, result)
            print(
                f"ERROR: Playwright timeout. Report written to: {report_path}",
                file=sys.stderr,
            )
            return 1
        except Exception as exc:
            result["ok"] = False
            result["error_type"] = exc.__class__.__name__
            result["error"] = redact_sensitive_text(
                str(exc), admin_path=resolved_config["admin_path"]
            )
            result["route_state"] = "adapter_error"
            write_report(report_path, result)
            print(
                "ERROR: "
                f"{redact_sensitive_text(str(exc), admin_path=resolved_config['admin_path'])}. "
                f"Report written to: {report_path}",
                file=sys.stderr,
            )
            return 1
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImportErrorRuntime as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
