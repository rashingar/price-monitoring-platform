from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check" / "operator-smoke.ps1"


class _RouteHandler(BaseHTTPRequestHandler):
    routes: dict[str, tuple[int, Any]] = {}
    requests_seen: list[tuple[str, str]] = []

    def do_GET(self) -> None:  # noqa: N802
        self.requests_seen.append(("GET", self.path))
        status, payload = self.routes.get(self.path, (404, {"detail": "not found"}))
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        self.requests_seen.append(("POST", self.path))
        self.send_response(405)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return None


class FakeHttpServer:
    def __init__(self, routes: dict[str, tuple[int, Any]]) -> None:
        self.routes = routes
        self.requests_seen: list[tuple[str, str]] = []
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "FakeHttpServer":
        requests_seen = self.requests_seen
        routes = self.routes

        class Handler(_RouteHandler):
            pass

        Handler.routes = routes
        Handler.requests_seen = requests_seen
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)

    @property
    def base_url(self) -> str:
        if self.server is None:
            raise RuntimeError("server is not started")
        host, port = self.server.server_address
        return f"http://{host}:{port}"


def test_operator_smoke_json_uses_read_only_status_endpoints() -> None:
    ecommerce_routes = {
        "/api/health": (200, {"status": "ok", "service": "ecommerce-api"}),
        "/api/price-monitoring/db/status": (
            200,
            {
                "price_monitoring_database_mode": "ready",
                "configured": True,
                "reachable": True,
                "required_tables_present": True,
                "ready_for_catalog": True,
                "ready_for_price_monitoring": True,
                "alembic_up_to_date": True,
                "alembic_current_revision": "abc",
                "alembic_head_revision": "abc",
                "blocking_reasons": [],
            },
        ),
        "/api/catalog/summary": (200, {"total_products": 42}),
        "/api/jobs?limit=1": (200, {"items": []}),
        "/api/catalog/update-db/latest": (200, None),
        "/api/vendor-sources/source-urls/summary": (200, {"total": 10}),
    }
    product_factory_routes = {"/api/health": (200, {"status": "ok", "service": "product-factory-api"})}
    web_routes = {"/": (200, b"<html><body>ok</body></html>")}

    with FakeHttpServer(product_factory_routes) as product_factory, FakeHttpServer(ecommerce_routes) as ecommerce, FakeHttpServer(web_routes) as web:
        completed = _run_operator_smoke(
            "-ProductFactoryBaseUrl",
            product_factory.base_url,
            "-EcommerceBaseUrl",
            ecommerce.base_url,
            "-WebBaseUrl",
            web.base_url,
            "-Json",
        )

        assert completed.returncode == 0, completed.stderr
        payload = json.loads(completed.stdout)
        statuses = {item["id"]: item["status"] for item in payload}
        assert statuses["product_factory_health"] == "passed"
        assert statuses["ecommerce_db_readiness"] == "passed"
        assert statuses["alembic_at_head"] == "passed"
        assert statuses["web_dev_server"] == "passed"
        assert all(method == "GET" for method, _path in product_factory.requests_seen + ecommerce.requests_seen + web.requests_seen)


def test_operator_smoke_skip_web_does_not_call_web_server() -> None:
    ecommerce_routes = {
        "/api/health": (200, {"status": "ok"}),
        "/api/price-monitoring/db/status": (
            200,
            {
                "price_monitoring_database_mode": "ready",
                "configured": True,
                "reachable": True,
                "required_tables_present": True,
                "ready_for_catalog": True,
                "ready_for_price_monitoring": True,
                "alembic_up_to_date": None,
                "blocking_reasons": [],
            },
        ),
        "/api/catalog/summary": (200, {"total_products": 1}),
        "/api/jobs?limit=1": (200, {"items": []}),
        "/api/catalog/update-db/latest": (200, None),
        "/api/vendor-sources/source-urls/summary": (200, {"total": 1}),
    }
    product_factory_routes = {"/api/health": (200, {"status": "ok"})}

    with FakeHttpServer(product_factory_routes) as product_factory, FakeHttpServer(ecommerce_routes) as ecommerce:
        completed = _run_operator_smoke(
            "-ProductFactoryBaseUrl",
            product_factory.base_url,
            "-EcommerceBaseUrl",
            ecommerce.base_url,
            "-SkipWeb",
            "-Json",
        )

        assert completed.returncode == 0, completed.stderr
        payload = json.loads(completed.stdout)
        statuses = {item["id"]: item["status"] for item in payload}
        assert statuses["web_dev_server"] == "skipped"
        assert statuses["alembic_at_head"] == "warn"


def _run_operator_smoke(*args: str) -> subprocess.CompletedProcess[str]:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT_PATH),
        *args,
    ]
    return subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=60, check=False)
