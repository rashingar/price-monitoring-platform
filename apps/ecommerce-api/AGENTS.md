# Repo Guardrails

## Removed Marketplace Fetch

Marketplace fetch/search code has been removed. Price Monitoring must
not call marketplace search or URL discovery for run fetch.

Price Monitoring uses existing active `source_urls`/`product_sources` only.
Products without active source URLs are not eligible for Price Monitoring and
must be skipped with `missing_active_source_url`. The default monitoring source
is all active source URLs across vendors; source/vendor filters are optional.

Source URL Agent, shown in the UI as Find Source, owns product source URL
discovery, candidate runs, candidate review, and source URL candidate
promotion. Its canonical backend namespace is `/api/source-url-agent/...`; web
frontend calls must resolve through `/commerce-api/source-url-agent/...`.

Vendor Sources owns vendor/source health, source URL capture, diagnostics, and
durable Vendor Source Capture run history. Do not add Source URL Agent routes
under `/api/vendor-sources/...`. Do not reintroduce DB-backed candidate review
layout preferences unless explicitly requested; candidate review layout stays
frontend-local.

Do not add fallback URL discovery, marketplace MPN/search fallback,
direct-vendor capture implementation, or Vendor Source Capture storage under
`price_monitoring`.
