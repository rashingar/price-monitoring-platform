from __future__ import annotations

import argparse
import ipaddress
import socket
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pipeline.dev.start")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _validate_host(args.host)
        _validate_port(args.port)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    base_url = f"http://{args.host}:{args.port}"
    print("Product-Agent API")
    print(f"API URL: {base_url}")
    print(f"Health URL: {base_url}/api/health")
    print(f"Docs URL: {base_url}/docs")
    print(f"Jobs URL: {base_url}/api/jobs")
    if args.dry_run:
        return 0

    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is not installed. Start the API with: "
            f"python -m uvicorn pipeline.api.app:app --host {args.host} --port {args.port}",
            file=sys.stderr,
        )
        return 1

    uvicorn.run(
        "pipeline.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def _validate_host(host: str) -> None:
    if not host or host.strip() != host:
        raise ValueError("Host must be a non-empty value without leading or trailing whitespace.")
    if host == "localhost":
        return
    try:
        ipaddress.ip_address(host)
        return
    except ValueError:
        pass
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"Host is not resolvable: {host}") from exc


def _validate_port(port: int) -> None:
    if port < 1 or port > 65535:
        raise ValueError("Port must be between 1 and 65535.")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
