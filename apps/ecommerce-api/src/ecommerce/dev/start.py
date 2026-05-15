"""Start the Ecommerce backend API for local development."""

from __future__ import annotations

import argparse
import json
import socket
from collections.abc import Sequence
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from ecommerce.db.config import DATABASE_URL_ENV_VAR, is_database_configured
from ecommerce.db.diagnostics import collect_database_status
from ecommerce.env import describe_local_env_warnings, load_local_env_if_present

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the Ecommerce FastAPI backend.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--reload", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    env_status = load_local_env_if_present()
    args = build_parser().parse_args(argv)
    base_url = f"http://{args.host}:{args.port}"

    print(f"API URL: {base_url}")
    print(f"Health URL: {base_url}/api/health")
    print(f"Docs URL: {base_url}/docs")
    print(f"Price Monitoring DB status URL: {base_url}/api/price-monitoring/db/status")
    for warning in describe_local_env_warnings(env_status):
        print(f"Local env warning: {warning}")
    _print_db_setup_hints()

    if _print_existing_ecommerce_api_status(args.host, args.port):
        return

    uvicorn.run("ecommerce.api.app:app", host=args.host, port=args.port, reload=args.reload)


def _print_existing_ecommerce_api_status(host: str, port: int) -> bool:
    if _can_bind(host, port):
        return False

    health_url = f"http://{host}:{port}/api/health"
    health = _read_json_url(health_url)
    if health.get("status") == "ok" and health.get("service") == "ecommerce-api":
        print(f"Ecommerce API is already running on {host}:{port}.")
        print(f"Health URL: {health_url}")
        return True

    raise SystemExit(
        f"Cannot start Ecommerce API because {host}:{port} is already in use by another process. "
        f"Stop that process or start this server with --port <free-port>."
    )


def _can_bind(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
    except OSError:
        return False
    return True


def _read_json_url(url: str) -> dict[str, object]:
    try:
        with urlopen(url, timeout=2) as response:
            payload = response.read().decode("utf-8")
    except (OSError, URLError, TimeoutError):
        return {}
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _print_db_setup_hints() -> None:
    if not is_database_configured():
        print(f"{DATABASE_URL_ENV_VAR} is not set; PostgreSQL persistence is optional for local file-backed workflows.")
        print("Set ECOMMERCE_DATABASE_URL and run alembic upgrade head to enable Price Monitoring DB persistence.")
        return
    status = collect_database_status()
    if status.get("reachable") and status.get("required_tables_present"):
        return
    print("Price Monitoring DB status needs attention.")
    for hint in status.get("setup_hints") or []:
        print(f"- {hint}")


if __name__ == "__main__":
    main()
