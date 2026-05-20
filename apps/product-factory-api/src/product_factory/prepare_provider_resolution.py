from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .fetcher import ElectronetFetcher
from .models import CLIInput, FetchResult, ParsedProduct
from .parser_product_bestprice import BestPriceProductParser
from .parser_product_electronet import ElectronetProductParser
from .parser_product_manufacturer import ManufacturerProductParser
from .parser_product_skroutz import SkroutzProductParser
from .providers.base import ProviderError
from .providers.models import ProviderInputIdentity, ProviderResult
from .providers.registry import (
    ProviderRegistry,
    bootstrap_runtime_provider_registry,
    source_to_provider_id,
)
from .providers.skroutz_provider import SKROUTZ_CHALLENGE_REASON
from .repo_paths import SCHEMA_LIBRARY_PATH
from .schema_matcher import SchemaMatcher
from .source_detection import detect_source, validate_url_scope

SKROUTZ_V1_MPN_HINTS = {
    "344317": "CM5S1DE0",
}


@dataclass(slots=True)
class PrepareProviderResolutionResult:
    source: str
    provider_id: str
    fetch: FetchResult
    parsed: ParsedProduct


def _provider_result_to_fetch(provider_result: ProviderResult) -> FetchResult:
    snapshot = provider_result.snapshot
    response_headers = dict(snapshot.headers)
    for key in ("fetch_status", "blocked", "blocked_reason"):
        value = snapshot.metadata.get(key)
        if value not in (None, ""):
            response_headers[f"x-product-factory-{key.replace('_', '-')}"] = str(value)
    return FetchResult(
        url=snapshot.requested_url or provider_result.identity.url,
        final_url=snapshot.final_url
        or snapshot.requested_url
        or provider_result.identity.url,
        html=snapshot.body_text,
        status_code=int(snapshot.status_code or 0),
        method=str(snapshot.metadata.get("fetch_method", "")),
        fallback_used=bool(snapshot.metadata.get("fallback_used", False)),
        response_headers=response_headers,
    )


def _provider_result_to_parsed(provider_result: ProviderResult) -> ParsedProduct:
    return ParsedProduct(
        source=provider_result.product,
        provenance=dict(provider_result.provenance),
        field_diagnostics=dict(provider_result.field_diagnostics),
        missing_fields=list(provider_result.missing_fields),
        warnings=list(provider_result.warnings),
        critical_missing=list(provider_result.critical_missing),
    )


def apply_skroutz_contract_hints(cli: CLIInput, parsed: ParsedProduct) -> None:
    hinted_mpn = SKROUTZ_V1_MPN_HINTS.get(cli.model)
    if hinted_mpn and (
        not parsed.source.mpn
        or parsed.source.mpn.endswith("D")
        or parsed.source.mpn.endswith("DE")
    ):
        parsed.source.mpn = hinted_mpn


def validate_prepare_provider_resolution_result(
    cli: CLIInput,
    result: PrepareProviderResolutionResult,
    *,
    validate_url_scope_fn: Callable[[str], tuple[str, bool, str]] = validate_url_scope,
) -> PrepareProviderResolutionResult:
    source = result.source
    parsed = result.parsed
    fetch = result.fetch
    if not parsed.source.source_name:
        parsed.source.source_name = source

    final_source, final_scope_ok, _final_scope_reason = validate_url_scope_fn(
        fetch.final_url
    )
    if final_source != source or not final_scope_ok:
        raise RuntimeError("Resolved URL is not a supported product page")

    if source == "electronet":
        source_code = parsed.source.product_code
        if not source_code:
            parsed.warnings.append(f"source_product_code_missing:input={cli.model}")
        elif source_code != cli.model:
            parsed.warnings.append(
                f"source_product_code_mismatch:input={cli.model}:page={source_code}"
            )
    elif source == "skroutz":
        apply_skroutz_contract_hints(cli, parsed)
        if parsed.source.page_type == SKROUTZ_CHALLENGE_REASON:
            if "blocked_by_challenge" not in parsed.warnings:
                parsed.warnings.append("blocked_by_challenge")
            return result
        if parsed.source.page_type != "product":
            detail = (
                parsed.source.taxonomy_escalation_reason
                or "unsupported_skroutz_page_type"
            )
            raise RuntimeError(f"Unsupported Skroutz page type: {detail}")
    elif source == "bestprice":
        if parsed.source.page_type != "product":
            detail = (
                parsed.source.taxonomy_escalation_reason
                or "unsupported_bestprice_page_type"
            )
            raise RuntimeError(f"Unsupported BestPrice page type: {detail}")
    else:
        if parsed.source.page_type != "product":
            detail = (
                parsed.source.taxonomy_escalation_reason
                or "unsupported_manufacturer_page_type"
            )
            raise RuntimeError(f"Unsupported manufacturer page type: {detail}")

    if (
        parsed.source.page_type != SKROUTZ_CHALLENGE_REASON
        and not parsed.source.name
        and not parsed.source.spec_sections
    ):
        raise RuntimeError("Total parse failure")

    return result


def resolve_prepare_provider_resolution(
    cli: CLIInput,
    *,
    detect_source_fn: Callable[[str], str] = detect_source,
    validate_url_scope_fn: Callable[[str], tuple[str, bool, str]] = validate_url_scope,
    schema_matcher_factory: Callable[..., SchemaMatcher] = SchemaMatcher,
    bestprice_parser_factory: Callable[
        [], BestPriceProductParser
    ] = BestPriceProductParser,
    electronet_parser_factory: Callable[
        ..., ElectronetProductParser
    ] = ElectronetProductParser,
    skroutz_parser_factory: Callable[[], SkroutzProductParser] = SkroutzProductParser,
    manufacturer_parser_factory: Callable[
        [], ManufacturerProductParser
    ] = ManufacturerProductParser,
    fetcher_factory: Callable[[], ElectronetFetcher] = ElectronetFetcher,
    bootstrap_provider_registry_fn: Callable[
        ..., ProviderRegistry
    ] = bootstrap_runtime_provider_registry,
    source_to_provider_id_fn: Callable[[str], str | None] = source_to_provider_id,
) -> PrepareProviderResolutionResult:
    source = detect_source_fn(cli.url)
    schema_matcher = schema_matcher_factory(str(SCHEMA_LIBRARY_PATH))
    bestprice_parser = bestprice_parser_factory()
    electronet_parser = electronet_parser_factory(
        known_section_titles=schema_matcher.known_section_titles
    )
    skroutz_parser = skroutz_parser_factory()
    manufacturer_parser = manufacturer_parser_factory()
    fetcher = fetcher_factory()
    registry = bootstrap_provider_registry_fn(
        fetcher=fetcher,
        bestprice_parser=bestprice_parser,
        electronet_parser=electronet_parser,
        skroutz_parser=skroutz_parser,
        manufacturer_parser=manufacturer_parser,
    )
    provider_id = source_to_provider_id_fn(source)
    if not provider_id:
        raise RuntimeError(f"No provider configured for supported source: {source}")
    try:
        provider = registry.require(provider_id)
    except ProviderError as exc:
        raise RuntimeError(str(exc)) from exc

    identity = ProviderInputIdentity(model=cli.model, url=cli.url)
    try:
        provider_result = provider.normalize(
            provider.fetch_snapshot(identity), identity
        )
    except ProviderError as exc:
        raise RuntimeError(str(exc)) from exc

    fetch = _provider_result_to_fetch(provider_result)
    parsed = _provider_result_to_parsed(provider_result)

    return validate_prepare_provider_resolution_result(
        cli,
        PrepareProviderResolutionResult(
            source=source,
            provider_id=provider_id,
            fetch=fetch,
            parsed=parsed,
        ),
        validate_url_scope_fn=validate_url_scope_fn,
    )
