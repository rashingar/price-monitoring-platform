# Repo Guardrails

## Deprecated Legacy Marketplace Fetch

Legacy marketplace fetch/search code has been removed. Price Monitoring must
not call marketplace search or URL discovery for run fetch.

Price Monitoring uses existing active `source_urls`/`product_sources` only.
Products without active source URLs are not eligible for Price Monitoring and
must be skipped with `missing_active_source_url`. The default monitoring source
is all active source URLs across vendors; source/vendor filters are optional.

Vendor Sources owns URL discovery, source URL candidates, source URL review,
source URL capture, source health, Product Factory handoff import, and durable
Vendor Source Capture run history. Do not add fallback URL discovery,
marketplace MPN/search fallback, direct-vendor capture implementation, or
Vendor Source Capture storage under `price_monitoring`.
