from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import CLIInput, FetchResult, ParsedProduct, SourceProductData
from .utils import ensure_directory, first_non_empty, utcnow_iso, write_json

SCHEMA_VERSION = "1.0"
HANDOFF_FILENAME = "price_fetcher_source_handoff.json"


def price_fetcher_handoff_path(model_dir: Path) -> Path:
    model_root = Path(model_dir).parent if Path(model_dir).name == "scrape" else Path(model_dir)
    return model_root / "integrations" / HANDOFF_FILENAME


def write_price_fetcher_source_handoff(
    *,
    cli: CLIInput,
    source: str,
    provider_id: str,
    fetch: FetchResult,
    parsed: ParsedProduct,
    model_dir: Path,
) -> Path:
    path = price_fetcher_handoff_path(model_dir)
    ensure_directory(path.parent)
    write_json(
        path,
        build_price_fetcher_source_handoff(
            cli=cli,
            source=source,
            provider_id=provider_id,
            fetch=fetch,
            parsed=parsed,
        ),
    )
    return path


def write_price_fetcher_source_failure_handoff(
    *,
    cli: CLIInput,
    source: str,
    provider_id: str,
    fetch: FetchResult,
    parsed: ParsedProduct,
    model_dir: Path,
    error: BaseException,
) -> Path:
    path = price_fetcher_handoff_path(model_dir)
    ensure_directory(path.parent)
    payload = build_price_fetcher_source_handoff(
        cli=cli,
        source=source,
        provider_id=provider_id,
        fetch=fetch,
        parsed=parsed,
    )
    payload["status"] = "failed"
    payload["error"] = {
        "type": error.__class__.__name__,
        "message": str(error),
    }
    write_json(path, payload)
    return path


def build_price_fetcher_source_handoff(
    *,
    cli: CLIInput,
    source: str,
    provider_id: str,
    fetch: FetchResult,
    parsed: ParsedProduct,
) -> dict[str, Any]:
    product = parsed.source
    source_name = first_non_empty([product.source_name, source])
    canonical_url = str(product.canonical_url or "")
    source_domain = _domain_for(first_non_empty([fetch.final_url, canonical_url, fetch.url, cli.url]))
    product_payload = _build_product_payload(product)
    computed_missing = _missing_schema_fields(product_payload)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utcnow_iso(),
        "model": cli.model,
        "input_url": cli.url,
        "source": source,
        "provider_id": provider_id,
        "requested_url": fetch.url,
        "final_url": fetch.final_url,
        "canonical_url": canonical_url,
        "source_name": source_name,
        "source_domain": source_domain,
        "product": product_payload,
        "evidence": {
            "title": product.name,
            "mpn": product.mpn,
            "model": cli.model,
            "brand": product.brand,
            "price": product.price_value,
            "category": _category_evidence(product),
            "provenance": dict(parsed.provenance),
            "field_diagnostics": _serialize_field_diagnostics(parsed.field_diagnostics),
        },
        "fetch": {
            "method": fetch.method,
            "status_code": fetch.status_code if fetch.status_code else None,
            "content_type": _content_type(fetch.response_headers),
            "fallback_used": bool(fetch.fallback_used),
        },
        "warnings": list(parsed.warnings),
        "missing_fields": _stable_unique([*parsed.missing_fields, *computed_missing]),
        "critical_missing": list(parsed.critical_missing),
        "artifact_refs": {
            "source_json": f"work/{cli.model}/scrape/{cli.model}.source.json",
            "report_json": f"work/{cli.model}/scrape/{cli.model}.report.json",
        },
    }


def _build_product_payload(product: SourceProductData) -> dict[str, Any]:
    price = product.price_value
    return {
        "name": product.name,
        "brand": product.brand,
        "manufacturer": str(getattr(product, "manufacturer", "") or ""),
        "mpn": product.mpn,
        "product_code": product.product_code,
        "page_type": product.page_type,
        "price": price,
        "currency": "EUR" if price is not None else None,
        "availability": first_non_empty([str(getattr(product, "availability", "") or ""), product.delivery_text, product.pickup_text]),
        "stock_status": str(getattr(product, "stock_status", "") or ""),
    }


def _missing_schema_fields(product_payload: dict[str, Any]) -> list[str]:
    missing = []
    for key, value in product_payload.items():
        if key == "currency":
            continue
        if value in (None, ""):
            missing.append(f"product.{key}")
    return missing


def _category_evidence(product: SourceProductData) -> str:
    return first_non_empty(
        [
            product.taxonomy_source_category,
            product.category_tag_text,
            " > ".join(item for item in product.breadcrumbs if item),
        ]
    )


def _content_type(headers: dict[str, str]) -> str:
    for key, value in headers.items():
        if key.lower() == "content-type":
            return str(value)
    return ""


def _domain_for(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return parsed.netloc.lower()


def _serialize_field_diagnostics(field_diagnostics: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for key, value in field_diagnostics.items():
        if hasattr(value, "to_dict"):
            serialized[key] = value.to_dict()
        else:
            serialized[key] = value
    return serialized


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
