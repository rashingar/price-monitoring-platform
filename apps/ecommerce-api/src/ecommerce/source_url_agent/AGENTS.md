# AGENTS.md — Source URL Agent

## Scope

This file applies to code under:


src/ecommerce/source_url_agent/


This package implements local, supervised source URL discovery for catalog products.

The goal is to find, score, review, and optionally store public product URLs for catalog products across marketplaces and direct vendors.

This package should support:

* CSV-driven discovery
* DB catalog-driven discovery
* marketplace/vendor source adapters
* candidate generation
* evidence extraction
* conservative match scoring
* review artifacts
* dry-run mode
* high-confidence apply mode
* manual review import/apply
* run summaries
* generic resolver improvement


## Relationship to the Rest of `ecommerce-api`

This package should reuse existing repository functionality:

* `ecommerce.source_urls`
* `ecommerce.db.source_url_repository`
* `ecommerce.db.models`
* `ecommerce.source_url_import`
* `ecommerce.source_url_agent.search`
* `ecommerce.price_monitoring.source_url_coverage`
* existing artifact, CSV, timestamp, config, and DB session helpers

Do not duplicate existing URL normalization, source-name inference, source URL persistence, or BestPrice/Skroutz MPN matching unless there is a clear reason.

Final accepted source URLs normally belong in the existing `source_urls` table. Candidate data, review data, and run history may use dedicated source URL agent tables or artifacts.

## Package Responsibility

The Source URL Agent is responsible for:

1. Selecting products to check.
2. Selecting target sources.
3. Generating safe search queries.
4. Navigating public pages where allowed.
5. Extracting candidate product URLs.
6. Loading candidate product pages.
7. Extracting visible evidence.
8. Scoring matches conservatively.
9. Writing run artifacts.
10. Writing candidate records where configured.
11. Applying only high-confidence or reviewed URLs to `source_urls`.

The Source URL Agent is not responsible for:

* updating OpenCart
* changing product prices
* publishing products
* rewriting product descriptions
* managing frontend UI
* replacing the existing Price Monitoring fetch workflow unless explicitly requested

## External Site Access Rules

All source adapters and browser/search code must follow these rules:

* Do not create high-speed crawling behavior.


## Product-Specific Data Rule

Do not hard-code product-specific URLs, product-specific exceptions, or one-off model hacks in code.

Product-specific results belong in:

* `source_urls` DB rows
* candidate records
* review artifacts
* run artifacts

Generic resolver improvements are allowed. Examples:

* better model-token normalization
* better brand normalization
* better category compatibility checks
* better canonical URL extraction
* better source-specific product URL pattern recognition

## Target Sources

The source registry may include:


bestprice   -> bestprice.gr     -> marketplace
skroutz     -> skroutz.gr        -> marketplace
electronet  -> electronet.gr     -> direct_vendor
kotsovolos  -> kotsovolos.gr     -> direct_vendor
public      -> public.gr         -> direct_vendor
plaisio     -> plaisio.gr        -> direct_vendor



Use a source registry rather than scattering source configuration across code.

A source definition should include, where relevant:


source_name
source_domain
source_type
enabled
expected_listing_field
public_search_url_templates
product_url_patterns
blocked_url_patterns
rate_limit_seconds
max_candidates_per_product
max_searches_per_product
notes


## Suggested Module Layout

Prefer a small, explicit module structure:


src/ecommerce/source_url_agent/
  __init__.py
  agent.py
  products.py
  sources.py
  browser.py
  search.py
  candidates.py
  evidence.py
  scoring.py
  artifacts.py
  persistence.py
  review.py
  analysis.py


Suggested responsibilities:


agent.py
  Orchestrates runs and product-source tasks.

products.py
  Reads products from CSV or DB catalog.
  Preserves model values as strings.

sources.py
  Loads source registry and source definitions.

browser.py
  Owns Playwright/browser session, safe navigation, caching, throttling, and block detection.

search.py
  Generates search queries and public search URLs.

candidates.py
  Represents candidate URLs and source-specific candidate extraction.

evidence.py
  Extracts visible product evidence from pages and HTML.

scoring.py
  Applies conservative match scoring and status rules.

artifacts.py
  Writes CSV/JSON run outputs.

persistence.py
  Writes discovery runs, candidates, and accepted source URLs.

review.py
  Imports and applies human-reviewed CSV decisions.

analysis.py
  Summarizes failures and proposes generic resolver improvements.


Do not let one module accumulate all browser, scoring, DB, and artifact logic.

## Data Model Expectations

Use explicit dataclasses or typed structures for internal records.

Core product input fields:


catalog_product_id
catalog_source
model
mpn
name
manufacturer
category
price
status
bestprice_status
skroutz_status


Core source fields:


source_name
source_domain
source_type
expected_listing


Core candidate fields:


catalog_product_id
model
mpn
manufacturer
product_name
category
own_price
source_name
source_domain
source_type
expected_listing
candidate_url
canonical_url
candidate_title
candidate_price
match_status
confidence_score
match_method
evidence
competing_candidates_count
searched_queries
notes
checked_at


## Input Rules

CSV inputs must preserve identifiers as text.

Rules:

* Preserve `model` as text, including leading zeroes.
* Strip surrounding whitespace from fields.
* Process `status = 1` by default.
* Allow inactive rows only when explicitly requested by CLI/API options.
* Treat missing MPN as valid input, but lower match confidence unless there is strong replacement evidence.
* Use `bestprice_status` as the expected-listing hint for BestPrice.
* Use `skroutz_status` as the expected-listing hint for Skroutz.
* Use `unknown` expected-listing for direct vendors unless source-specific status fields exist later.

## Search Strategy

For each product/source pair, use a bounded strategy.

Preferred query order:


1. "{manufacturer}" "{mpn}" site:{domain}
2. source-specific public search page for the manufacturer + MPN query, when allowed and configured


Rules:

* Do not spend unbounded searches on one product/source.
* Respect `max_searches_per_product`.
* Respect `max_candidates_per_product`.
* Stop early when there is one high-confidence exact match and no competing candidate.
* If multiple plausible candidates exist, mark `needs_review`.
* If blocked or CAPTCHA appears, mark `error`.

## Candidate URL Rules

Only product pages should become candidates.

Reject or ignore:


search result pages
category pages
cart pages
checkout pages
account pages
login pages
wishlist pages
support pages
PDF/manual pages unless explicitly useful as evidence, not final URL
tracking redirect URLs
private or session URLs


Normalize candidate URLs using existing `ecommerce.source_urls.normalize_source_url`.

Remove common tracking parameters through existing utilities.

Prefer canonical product URLs when the page exposes them.

## Evidence Extraction

Evidence may come from:

* page title
* visible body text
* product detail/specification sections
* canonical link
* product URL path
* public structured data embedded in HTML, such as JSON-LD Product
* visible price text
* visible brand/manufacturer text
* visible MPN/model fields


Evidence fields should include:


evidence_mpn
evidence_brand
evidence_model
evidence_category
evidence_price
evidence_title
evidence_url
evidence_source_details


Evidence should be stored in a compact JSON-compatible form.

## Match Scoring

Use conservative scoring.

Suggested confidence levels:


1.00
  Exact MPN and manufacturer match on product page.

0.90 or lower
  Candidate requires manual review, including exact MPN without matching manufacturer, exact model-only evidence, title/name similarity, or any ambiguous result.

0.00
  No reliable match.


Suggested status mapping:


matched
  confidence > 0.90 with `exact_mpn_and_brand` only.

needs_review
  any discovered candidate that is not a `confidence > 0.90` `exact_mpn_and_brand` match.

not_found
  no credible product page found.

error
  blocked, timeout, inaccessible, malformed page, source unavailable, or navigation error.

skipped
  inactive product or intentionally skipped source.


Hard rule:


Title-only matches must never be auto-applied to source_urls.


## Ambiguity Rules

Mark `needs_review` when:

* multiple plausible product pages exist
* exact MPN appears on more than one candidate
* brand differs
* category differs materially
* title is similar but no MPN/model evidence exists
* price is a major outlier and identifiers are weak
* source page contains insufficient detail
* canonical URL cannot be determined but page looks plausible

Do not guess in ambiguous cases.

## Persistence Rules

Default behavior must be dry-run.

Only write final accepted URLs to `source_urls` when:

* the command explicitly permits apply behavior
* the match is high-confidence, or
* the review file explicitly approves the URL

For automatically discovered URLs:


url_type = discovered
trust_level = high_confidence
status = active


For reviewed accepted URLs:


url_type = discovered or manual, depending on review context
trust_level = manual
status = active


For ambiguous candidates:


status = needs_review


Never overwrite existing manual URLs without explicit instruction.

Never disable or mark existing URLs broken merely because a discovery run fails.

Do not delete existing `source_urls` rows from this package.

## Candidate and Run Storage

If DB-backed candidate/run storage exists, use it.

If it does not exist yet, artifact-only mode is acceptable for a first implementation.

Run storage should track:


run_id
source_name
mode
status
input_path
filters
selected_count
candidate_count
matched_count
needs_review_count
not_found_count
error_count
started_at
completed_at
created_at
updated_at


Candidate storage should track enough evidence to review and reproduce decisions.

## Review Workflow

Review CSVs must be editable by a human or by a separate assistant.

Review columns:


review_decision
reviewed_url
review_notes
reviewed_by
reviewed_at


Valid decisions:


accept
reject
replace_url
not_found
needs_manual_review


Apply behavior:


accept
  Write candidate URL to source_urls.

replace_url
  Validate reviewed_url, then write reviewed_url to source_urls.

reject
  Mark candidate rejected. Do not write final source URL.

not_found
  Record not_found. Do not write final source URL.

needs_manual_review
  Keep pending. Do not write final source URL.


Review apply should support dry-run and apply modes.

## Artifact Rules

Every run should write artifacts under:


output/ecommerce/source-url-agent/runs/{run_id}/


Expected files:


source_url_results.csv
approved_source_urls.csv
needs_review_source_urls.csv
not_found_source_urls.csv
errors.csv
source_url_run_summary.json
searched_queries.json
rule_suggestions.json


CSV outputs should include:


model
catalog_product_id
catalog_name
mpn
manufacturer
category
own_price
source_name
source_domain
source_type
expected_listing
candidate_url
canonical_url
candidate_title
candidate_price
match_status
confidence_score
match_method
evidence_mpn
evidence_brand
evidence_model
evidence_category
evidence_price
competing_candidates_count
searched_queries
notes
checked_at


Review CSVs should additionally include review columns.

Do not write secrets or cookies to artifacts.

## CLI Expectations

This package is primarily operated through local jobs.

Expected commands may be exposed through:


python -m ecommerce.jobs.source_url_agent ...


Suggested commands:

powershell
python -m ecommerce.jobs.source_url_agent run `
  --input input/test-1.csv `
  --source all `
  --limit 20 `
  --dry-run


powershell
python -m ecommerce.jobs.source_url_agent from-catalog `
  --source all `
  --missing-only `
  --limit 20 `
  --dry-run


powershell
python -m ecommerce.jobs.source_url_agent run `
  --input input/test-1.csv `
  --source all `
  --apply-high-confidence `
  --limit 20


powershell
python -m ecommerce.jobs.source_url_agent apply-review `
  --review-file output/ecommerce/source-url-agent/runs/{run_id}/needs_review_source_urls_reviewed.csv `
  --dry-run


powershell
python -m ecommerce.jobs.source_url_agent analyze `
  --run-id {run_id}


Useful options:


--input
--source
--limit
--offset
--catalog-product-id
--model
--missing-only
--active-only
--dry-run
--apply-high-confidence
--review-file
--output-dir
--max-products-per-batch
--max-searches-per-product-source
--rate-limit-seconds
--headed
--no-browser-cache


## API Expectations

CLI comes first.

Do not add API endpoints before the CLI path is reliable unless explicitly requested.

If API endpoints are added later, they should call the same service-layer code as the CLI. Do not duplicate orchestration logic in route handlers.

Canonical Vendor Sources routes:


POST /api/vendor-sources/agent/runs
GET  /api/vendor-sources/agent/runs
GET  /api/vendor-sources/agent/runs/{run_id}
GET  /api/vendor-sources/agent/runs/{run_id}/artifacts
GET  /api/vendor-sources/candidates
GET  /api/vendor-sources/candidates/{candidate_id}
PATCH /api/vendor-sources/candidates/{candidate_id}/review


## Testing Rules

Use deterministic tests with fake HTML and local fixtures.

Do not require live websites in the default test suite.

Tests should cover:


CSV input parsing with leading-zero models
source registry loading
safe search query generation
candidate URL filtering
URL normalization
canonical URL extraction
HTML evidence extraction
JSON-LD evidence extraction
exact MPN/model scoring
brand/category compatibility scoring
title-only match forced to needs_review
multiple candidates forced to needs_review
not_found behavior
blocked/CAPTCHA/error behavior
dry-run persistence behavior
high-confidence apply behavior
manual review apply behavior
artifact writing
summary JSON generation


Live website tests must be marked:


external


and must not run by default.

## Browser and Network Code

Browser/network code must be isolated.

Rules:

* Keep Playwright usage in browser/source adapter modules.
* Add timeouts.
* Add rate limits.
* Add cache keys.
* Add clear error codes.
* Return structured errors instead of throwing raw browser exceptions up the stack.
* Close pages/contexts reliably.
* Avoid opening many pages at once.
* Prefer sequential or low-concurrency execution.

Do not bury browser calls inside scoring or persistence modules.

## Error Codes

Use stable, short error codes where possible:


blocked_or_captcha
timeout
navigation_failed
robots_disallowed
not_public_product_page
no_candidates
missing_mpn
ambiguous_candidates
weak_evidence
category_mismatch
brand_mismatch
url_validation_failed
db_not_configured
db_write_failed
artifact_write_failed


Keep human-readable notes separate from machine-readable codes.

## Logging

Log progress without leaking secrets.

Useful logs:


run started
source started
product-source started
candidate count
match status
confidence score
error code
artifact path
dry-run/apply mode
run summary


Do not log:


DB passwords
cookies
authorization headers
full environment variables
private file contents


## Self-Improvement Policy

This package may support generic improvement analysis and self-modifying behavior.

Allowed:

* summarize rejected/ambiguous/not_found patterns
* produce `rule_suggestions.json`
* identify repeated normalization failures
* suggest source-specific parser improvements
* add regression tests during implementation
* improve generic matching rules

Not allowed:

* auto-approving weak/title-only matches based on prior convenience
* silently changing thresholds without tests

## Source-Specific Notes

### BestPrice

Use Source URL Agent discovery and evidence scoring. The legacy marketplace
fetch/search implementation has been removed.

Rules:

* strict MPN evidence is preferred
* name similarity is only a tie-breaker
* title-only match is not enough
* return canonical product URLs
* preserve merchant ladder evidence when available, but URL discovery should not require price extraction

### Skroutz

Reuse existing Skroutz MPN-driven logic where possible.

Rules:

* strict MPN evidence is preferred
* multiple candidates are ambiguous
* return canonical product URLs
* title-only match is not enough

### Electronet

Electronet reference logic may exist in `../product-factory-api`.

Rules:

* inspect sibling code only as reference
* do not import Product Factory as a runtime dependency
* port only minimal generic logic
* test with fake Electronet-like HTML fixtures

### Generic Direct Vendors

For direct vendors, use generic public product page matching:

* product URL pattern
* canonical URL
* title/body evidence
* visible brand/model/MPN
* JSON-LD Product where present
* category compatibility

Do not assume all vendor pages expose the same structure.

## Code Quality

Keep the package boring and testable.

Rules:

* small modules
* typed dataclasses or Pydantic models for structured records
* pure functions for scoring
* no DB access in scoring
* no browser access in scoring
* no artifact writing in source adapters
* no source-specific hacks in generic modules
* clear separation between candidate discovery, evidence extraction, scoring, artifacts, and persistence

## Handoff Requirements

After changes in this package, report:


files changed
commands added
tests added
tests run
dry-run command used
artifact paths
DB writes performed, if any
known limitations
next recommended command


Do not claim the agent is ready for a full catalog run until:

* unit tests pass
* a 5-product dry-run completes
* artifacts are produced
* ambiguous cases are correctly separated
* no unexpected DB writes occur in dry-run
