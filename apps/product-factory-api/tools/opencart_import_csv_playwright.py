#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from tools.opencart_config import resolve_opencart_config

DEFAULT_HEADLESS = True


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
    csv_path: Path, model: str, *, allow_partial_csv: bool = False
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

    first = rows[0]
    if str(first.get("model", "")).strip() != model:
        raise ImportErrorRuntime(
            f"CSV model mismatch. Expected {model}, got {first.get('model')!r} in {csv_path.name}"
        )

    image = str(first.get("image", "")).strip()
    if not allow_partial_csv and image != f"catalog/01_main/{model}/{model}-1.jpg":
        raise ImportErrorRuntime(
            "CSV image path does not match expected contract: "
            f"{image!r} != 'catalog/01_main/{model}/{model}-1.jpg'"
        )

    return {
        "headers": headers,
        "row_count": len(rows),
        "first_row_model": first.get("model"),
        "first_row_image": image,
        "first_row_additional_image": first.get("additional_image", ""),
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


def open_import_page(page, admin_index: str, profile: str, timeout_ms: int) -> None:
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


def assert_step2_mapping(page, profile: str, timeout_ms: int) -> dict[str, Any]:
    page.locator("#form-step2").wait_for(state="visible", timeout=timeout_ms)
    model_select = page.locator('select[name="fields[model]"]')
    model_select.wait_for(state="visible", timeout=timeout_ms)
    selected_text = model_select.locator("option:checked").inner_text().strip()

    profile_name = page.locator('input[name="profile_name"]').input_value().strip()

    return {
        "profile_name": profile_name,
        "selected_model_mapping": selected_text,
        "profile_expected": profile,
        "mapping_ok": selected_text == "model" and profile_name == profile,
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
    page, timeout_ms: int, poll_interval_sec: float, max_wait_sec: int
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
        "status_text": status_text,
        "elapsed_sec": round(time.time() - started_at, 2),
        "messages_html": messages_html or "",
        "counters": counters,
    }


def write_report(report_path: Path, payload: dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


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
    if not resolved_config["username"] or not resolved_config["password"]:
        raise ImportErrorRuntime(
            "Missing admin credentials. Pass --username/--password or set OPENCART_ADMIN_USER and OPENCART_ADMIN_PASS."
        )
    csv_path = resolve_csv_path(repo_root, args.model, args.csv_file)
    contract = csv_contract_check(
        csv_path, args.model, allow_partial_csv=args.allow_partial_csv
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
        "admin_index": admin_index,
        "profile": resolved_config["profile"],
        "csv_file": str(csv_path),
        "csv_contract": contract,
        "model": args.model,
    }

    print(
        json.dumps(
            {
                "model": args.model,
                "csv_file": str(csv_path),
                "profile": resolved_config["profile"],
                "admin_index": admin_index,
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
            result["login"] = {"ok": True, "url_after_login": page.url}

            open_import_page(
                page, admin_index, resolved_config["profile"], args.timeout_ms
            )
            result["step1_opened"] = {"ok": True, "url": page.url}

            step1_upload_and_next(page, csv_path, args.timeout_ms)
            step2_info = assert_step2_mapping(
                page, resolved_config["profile"], args.timeout_ms
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

            step2_next(page, args.timeout_ms)
            result["step3_opened"] = {"ok": True, "url": page.url}

            monitor = step3_monitor(
                page, args.timeout_ms, args.poll_interval_sec, args.max_wait_sec
            )
            result["step3"] = monitor

            if monitor["final_status"] != "completed":
                raise ImportErrorRuntime(
                    f"Import did not complete successfully: {monitor['final_status']}"
                )

            result["ok"] = True
            write_report(report_path, result)
            print(f"Import OK. Report written to: {report_path}")
            return 0
        except PlaywrightTimeoutError as exc:
            result["ok"] = False
            result["error_type"] = "playwright_timeout"
            result["error"] = str(exc)
            result["url"] = page.url
            write_report(report_path, result)
            print(
                f"ERROR: Playwright timeout. Report written to: {report_path}",
                file=sys.stderr,
            )
            return 1
        except Exception as exc:
            result["ok"] = False
            result["error_type"] = exc.__class__.__name__
            result["error"] = str(exc)
            result["url"] = page.url
            write_report(report_path, result)
            print(f"ERROR: {exc}. Report written to: {report_path}", file=sys.stderr)
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
