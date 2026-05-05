# Testing Runbook

Install dependencies:

```bash
npm install
```

Build production assets:

```bash
npm run build
```

Run fast mocked checks:

```bash
npm run test:fast
```

Run API client contract fixture tests only:

```bash
npm run test:contracts
```

Run page-level smoke tests only:

```bash
npm run test:smoke
```

## Coverage

`test:contracts` calls the UI API clients directly with mocked Product-Agent and commerce responses. It checks client normalization, preserved status/model values, Catalog source URL list/write/validate/import payloads, Filters Manager `expected_revision` write bodies, artifact URL conversion, Price Monitoring DB readiness states, Catalog import warnings, structured DB-required 503 errors, and useful API error messages.

`test:smoke` renders key operator pages with mocked backend responses and asserts headings, navigation, core rows, status text, and critical page shells. It verifies Price Monitoring workflow, execution history, and alerts lock when PostgreSQL is not ready, Catalog source URL management and import preview/apply guards, Catalog shows its separate database/import-required state when Catalog endpoints return structured 503 responses, and CSV/Bridge still renders independently. Filters Manager smoke coverage also verifies the loaded revision display, successful write revision updates, stale 409 conflict messaging, no silent write retry, and reload-category behavior.

`test:fixture-contracts` compares mocked fixture routes against the backend OpenAPI snapshots. It keeps `/commerce-api` to `/api` normalization, checks Price Monitoring DB status fixture fields, validates structured Price Monitoring DB-required 503 fixtures, and validates separate structured Catalog DB/import-required 503 fixtures including source URL routes. Importer/reporting source URL fixture routes are allowed as pending when the backend snapshot has not documented them yet. For Product-Agent Filters Manager, it checks revision fields on response fixtures and `expected_revision` awareness on the group/value write request examples.

`test:fast` runs both contract and smoke suites once in Vitest/jsdom.

## Intentional Limits

These tests do not require Product-Agent or price-fetcher to be running. They do not use live network calls, real CSV files, local Windows paths, PostgreSQL, OpenCart, OpenAI, backend subprocesses, or browser end-to-end tooling.

PostgreSQL is mandatory for live Catalog browsing and Price Monitoring workflows, alerts, and
execution history. Catalog also requires an active imported catalog. In mocked tests,
Price Monitoring DB-not-ready and Catalog DB/import-not-ready are represented as separate
blocking conditions; neither must imply the commerce health, CSV/Bridge, files, paths, or
artifacts APIs are down.

For Filters Manager, a 409 stale revision response means the backend rejected a write because the category changed after the UI loaded it. The operator path is to reload the category, inspect the current values, and save again with the new backend revision token.

Real cross-repo integration checks and backend OpenAPI snapshot exports/checks are separate later tasks.
