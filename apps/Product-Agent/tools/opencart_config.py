#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
from pathlib import Path


def discover_repo_root(explicit_repo_root: str | None) -> Path:
    candidates: list[Path] = []
    if explicit_repo_root:
        candidates.append(Path(explicit_repo_root).expanduser().resolve())

    env_root = os.environ.get("OPENCART_PIPELINE_REPO_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser().resolve())

    def walk_up(start: Path) -> list[Path]:
        return [start, *start.parents]

    candidates.extend(walk_up(Path.cwd().resolve()))
    candidates.extend(walk_up(Path(__file__).resolve().parent))

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / ".git").exists() or (candidate / "products").is_dir() or (candidate / "work").is_dir():
            return candidate
    raise RuntimeError("Could not auto-detect repo root for OpenCart config resolution.")


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _resolve_value(
    explicit_value: str | None,
    env_key: str,
    env_file_values: dict[str, str],
    fallback: str = "",
) -> str:
    if explicit_value is not None and str(explicit_value).strip():
        return str(explicit_value).strip()
    env_value = os.environ.get(env_key)
    if env_value is not None and str(env_value).strip():
        return str(env_value).strip()
    file_value = env_file_values.get(env_key)
    if file_value is not None and str(file_value).strip():
        return str(file_value).strip()
    return fallback


def resolve_opencart_config(
    *,
    repo_root: Path,
    store_base: str | None = None,
    admin_path: str | None = None,
    username: str | None = None,
    password: str | None = None,
    profile: str | None = None,
) -> dict[str, str]:
    env_file = repo_root / ".secrets" / "opencart.env"
    env_file_values = load_env_file(env_file)
    return {
        "env_file": str(env_file),
        "store_base": _resolve_value(store_base, "OPENCART_STORE_BASE", env_file_values, ""),
        "admin_path": _resolve_value(admin_path, "OPENCART_ADMIN_PATH", env_file_values, ""),
        "username": _resolve_value(username, "OPENCART_ADMIN_USER", env_file_values, ""),
        "password": _resolve_value(password, "OPENCART_ADMIN_PASS", env_file_values, ""),
        "profile": _resolve_value(profile, "OPENCART_IMPORT_PROFILE", env_file_values, ""),
    }


def _export_shell(args: argparse.Namespace) -> int:
    repo_root = discover_repo_root(args.repo_root)
    config = resolve_opencart_config(
        repo_root=repo_root,
        store_base=args.store_base,
        admin_path=args.admin_path,
        username=args.username,
        password=args.password,
        profile=args.profile,
    )
    print(f"OPENCART_STORE_BASE={shlex.quote(config['store_base'])}")
    print(f"OPENCART_ADMIN_PATH={shlex.quote(config['admin_path'])}")
    print(f"OPENCART_ADMIN_USER={shlex.quote(config['username'])}")
    print(f"OPENCART_ADMIN_PASS={shlex.quote(config['password'])}")
    print(f"OPENCART_IMPORT_PROFILE={shlex.quote(config['profile'])}")
    print(f"OPENCART_ENV_FILE={shlex.quote(config['env_file'])}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve shared OpenCart runtime configuration.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_shell = subparsers.add_parser("export-shell", help="Print shell assignments for resolved OpenCart settings.")
    export_shell.add_argument("--repo-root", default=None)
    export_shell.add_argument("--store-base", default=None)
    export_shell.add_argument("--admin-path", default=None)
    export_shell.add_argument("--username", default=None)
    export_shell.add_argument("--password", default=None)
    export_shell.add_argument("--profile", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "export-shell":
        return _export_shell(args)
    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
