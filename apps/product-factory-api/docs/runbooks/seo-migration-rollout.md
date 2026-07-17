# Product Factory SEO Migration Rollout

This runbook operates the Phase 4 migration tooling for existing Product
Factory products. The workflow is dry-run first. The only supported Phase 4
operator write entrypoints are the `apply` and `rollback` subcommands, and both
require production-only flags plus an exact run-specific confirmation string.
The repository also contains lower-level OpenCart tools; do not invoke them as
Phase 4 operator commands.

Run every command from the repository root with the root virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps
```

Never substitute `products/{model}.csv` or a Product Factory candidate CSV for
a current catalog export. Never test migration writes against production just
to determine whether configuration works.

## Discovery conclusions and system boundaries

- The published-state authority for this migration is a complete, current
  OpenCart catalog export supplied by the operator. Product Factory does not
  connect directly to the live OpenCart database for snapshotting.
- Published SEO keywords, canonical URLs, main images, and additional-image
  paths are read from that export. Generated files under `work/` and
  `products/` are candidate state, not proof of what is published.
- Phase 1-3 candidate state is loaded offline from a dedicated candidate
  directory. The loader reads candidate CSV rows and, when present, the
  corresponding normalized, product-identity, SEO-health, Product JSON-LD,
  and product-feed JSON artifacts.
- Existing OpenCart writes use the repository's Karapuz partial-CSV importer.
  Approved image copies use the separate migration image uploader. Normal
  Product Factory publish jobs and ecommerce catalog/price workflows are not
  invoked by snapshot or plan commands.
  The image uploader is an internal adapter: it rejects manifests that are not
  bound to the run, snapshot, approval hash, plan hash, target fingerprint, and
  durable one-shot apply claim. Adapter authorizations are issued only when
  their individual model reaches the write boundary, expire after 30 minutes,
  and are consumed separately by the image and partial-import adapters before
  either live action. An unstarted later model has no usable authorization.
- This repository cannot install web-server, CDN, reverse-proxy, or OpenCart
  redirect rules. A slug write is rejected until the responsible external
  system has applied and verified the exact 301 redirect and supplied a
  machine-readable confirmation.
- `status`, `active`, `price`, `quantity`, and `stock_status` are protected.
  The migration planner classifies changes to them as blocked, and the partial
  writer refuses those columns. Existing price/stock synchronization remains
  outside this workflow.
- Active and inactive state is observed but never changed. The canary proposal
  can include inactive coverage, but an inactive product is written only when
  an operator includes that exact model in the approval manifest.
- Existing image paths remain locked by default. An approved image migration
  copies and verifies a JPG before switching references, uploads the copy,
  verifies its public hash, retains the original, and performs no delete.
  Description `besco#.jpg` assets are never renamed.
- Phase 4 commands are operator-invoked. No scheduler, deployment script, or
  background job automatically snapshots, plans, applies, rolls back, expands
  a cohort, or changes SEO-health enforcement.
- A Phase 4 snapshot and rollback manifest supplement, but do not replace, the
  organization's normal OpenCart database and image-file backups. The Filters
  Manager backup directory is unrelated to catalog migration recovery.
- Migration output lives under `apps/product-factory-api/migration/` by
  default and is ignored by Git. There is no automatic retention or pruning
  job for these artifacts.

Do not assume that a successful local render means the catalog is unchanged,
that a crawler timeout means Googlebot is blocked, or that an unverified
redirect has been deployed.

## Operator variables

Use stable, non-secret identifiers. The source/export identity describes the
export job. The target identity is a fingerprint resolved from the actual
OpenCart store base, admin path, and exact Karapuz profile; they are separate
values.

```powershell
$OutputRoot = "apps/product-factory-api/migration"
$SnapshotId = "pf4-production-20260712-01"
$RunId = "phase4-ac-20260712-01"
$InitialFullExport = "D:\secured-exports\opencart-full-20260712T090000Z.csv"
$FreshFullExport = "D:\secured-exports\opencart-full-20260712T110000Z.csv"
$CandidateDir = "D:\review\phase1-3-ac-candidates"
$ApprovalFile = "D:\approvals\phase4-ac-20260712-01.approval.json"
$SourceIdentity = "opencart-full-export-job:20260712T090000Z"
$ImportProfile = "SEO migration partial update"
$ImageRoot = "D:\opencart-image-staging"
$RedirectConfirmation = "D:\approvals\phase4-ac-20260712-01.redirects.json"
```

Do not put a database URI, username, password, API key, session token, or
credential-bearing URL in `--source-identity` or `--target-identity`.

Resolve the target fingerprint locally before snapshotting. This reads the
existing OpenCart configuration but performs no HTTP request or write:

```powershell
$TargetIdentity = ( `
  .\.venv\Scripts\python.exe -m product_factory.seo_migration target-fingerprint `
    --opencart-import-profile "$ImportProfile" |
  ConvertFrom-Json
).target_identity
```

Changing the configured store, admin path, or profile changes the fingerprint
and makes apply/rollback fail closed. The fingerprint does not prove that an
operator left server-side settings unchanged under the same profile label;
the dedicated reviewed profile and Step 2 mapping preflight remain mandatory.
An offline-only snapshot may omit `--target-identity`, which records
`unbound`; it remains usable for dry-run planning but can never be applied.

## Full catalog export contract

The snapshot and the fresh pre-apply comparison must use UTF-8 CSV exports
from the same target and the same export definition. A full export means all
products in that target, not only air conditioners, candidate models, active
products, or approved products. Each row must have one unique non-empty model.

Production apply requires `model` and these published fields to be available:

- `status`
- `name`
- `meta_title`
- `meta_description`
- `meta_keywords` or `meta_keyword`
- `seo_keyword`
- `canonical_url` or `product_url`
- `mpn`
- `main_image` or `image`
- `additional_images` or `additional_image`
- `category`
- dynamic `filter_group:*` columns for any reversible filter migration
- `manufacturer`
- `related_products` or `related_product`
- `price`
- `quantity`
- `stock_status`
- `last_modified` or `date_modified`

Include the remaining snapshot fields whenever the exporter provides them:
`product_id`, `active`, `description`, EAN/GTIN/UPC/JAN/ISBN fields,
`date_added`, and any additional supported aliases. `active` is independent of
`status`; the snapshot does not infer one from the other. Additional images
may be `:::`-separated or a JSON string array. Related products may be comma-
or `:::`-separated or a JSON string array.
Generic serialized `filters`/`filter_values` columns may be snapshotted for
review, but this phase refuses to apply them because their original import
header cannot be restored safely. Use exact `filter_group:*` columns whenever
filter changes may be approved.

The initial and fresh exports must have the same full product set, normalized
snapshot values, and canonical field inventory. Any change in the normalized
snapshot contract after the snapshot, including a supported field on an
unrelated product, changes the catalog hash and rejects apply. Export-only
columns outside that contract are not hashed and remain an operator comparison.
Do not override a hash rejection. Take a new full export, snapshot, plan, and
approval.
Because this repository has no direct database compare-and-set operation, the
operator must also place OpenCart administration, scheduled catalog writers,
and other product importers under a documented zero-mutation change freeze
from the fresh export through completion and review of the post-apply export
and monitor report. The target lock serializes Phase 4 processes only; it
cannot lock unrelated store administrators or syncs.

Retain the exact original export with the snapshot evidence. The snapshot
records source hash, normalized catalog hash, immutable content hash, row
count, timestamp, source environment, and non-secret source identity.

## Phase 1-3 candidate directory

Use a dedicated, frozen directory containing one candidate CSV row for each
six-digit model. Do not mix two candidate CSVs for the same model. Include
these model-named JSON artifacts when available:

```text
{model}.normalized.json
{model}.product_identity.json
{model}.product_structured_data.json
{model}.product_feed.json
{model}.seo_health.json
```

The loader is recursive and filesystem-only. Freeze the directory while a run
is under review; changing a candidate changes the deterministic candidate hash
and requires a new migration run.

## Snapshot

Create the immutable production snapshot. The command performs no production
write:

```powershell
.\.venv\Scripts\python.exe -m product_factory.seo_migration snapshot `
  --catalog-export "$InitialFullExport" `
  --environment production `
  --source-identity "$SourceIdentity" `
  --target-identity "$TargetIdentity" `
  --snapshot-id "$SnapshotId" `
  --output-root "$OutputRoot"
```

Review the reported row count and hashes, then inspect:

```text
{output_root}/snapshots/{snapshot_id}/snapshot.json
```

Snapshot directories are immutable and are not overwritten. If the command
reports that the ID already exists, use a new ID; do not edit the old file.

## Dry-run plan

Plan the air-conditioner scope. `plan` is dry-run even when `--dry-run` is
omitted; the flag below makes the operator intent explicit.

```powershell
.\.venv\Scripts\python.exe -m product_factory.seo_migration plan `
  --snapshot-id "$SnapshotId" `
  --candidate-dir "$CandidateDir" `
  --migration-run-id "$RunId" `
  --family air_conditioner `
  --canary-size 5 `
  --dry-run `
  --output-root "$OutputRoot"
```

To add an explicit model boundary, use one of these options:

```powershell
--models "123456,234567,345678"
--models-file "D:\review\approved-plan-scope.txt"
```

The models file contains one six-digit model per line; blank lines and lines
starting with `#` are ignored. A canary size must be from 5 through 10.

The command writes no OpenCart data and creates:

```text
{output_root}/{migration_run_id}/summary.json
{output_root}/{migration_run_id}/plan.json
{output_root}/{migration_run_id}/products.csv
{output_root}/{migration_run_id}/products.json
{output_root}/{migration_run_id}/blocked.json
{output_root}/{migration_run_id}/redirect_candidates.csv
{output_root}/{migration_run_id}/image_candidates.csv
{output_root}/{migration_run_id}/rollback_manifest.json
{output_root}/{migration_run_id}/seo_health_summary.json
{output_root}/{migration_run_id}/canary_proposal.json
```

For an exceptional image-path migration, create a new reviewed plan with the
local published-image root so the planner hashes every current source into the
authoritative `plan.json`:

```powershell
--image-root "$ImageRoot"
```

Planning fails if a changed gallery source is missing or escapes
`catalog/01_main/{model}/`. A plan without these hashes remains valid for
content review, but its image-path candidates cannot be approved for apply.

Representative review excerpts follow. Values and hashes are illustrative;
never copy them into an approval or production run.

`summary.json`:

```json
{
  "schema_version": "1.0",
  "migration_run_id": "phase4-ac-20260712-01",
  "snapshot_id": "pf4-production-20260712-01",
  "mode": "dry_run",
  "plan_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "summary": {
    "product_count": 6,
    "classifications": {
      "blocked": 2,
      "review_required": 5,
      "safe_content_update": 8,
      "unavailable": 4,
      "unchanged": 71
    },
    "blocked_field_count": 2,
    "redirect_candidate_count": 1,
    "image_candidate_count": 6,
    "production_writes": 0,
    "dry_run": true,
    "enforcement_mode": "blockers_only",
    "strict_enabled_automatically": false
  }
}
```

One `products.json[0].fields[n]` entry:

```json
{
  "model": "123456",
  "field": "meta_title",
  "current_value": "Legacy title",
  "candidate_value": "Midea Example 12000 BTU Air Conditioner",
  "classification": "safe_content_update",
  "reason": "content_candidate_differs_and_is_approval_eligible",
  "evidence": [
    {
      "source": "catalog_snapshot",
      "field": "meta_title",
      "snapshot_id": "pf4-production-20260712-01",
      "value_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    },
    {
      "source": "phase1_3_candidate",
      "field": "meta_title",
      "artifacts": {},
      "value_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    }
  ],
  "seo_health_before": {"profile": "full", "score": 78, "coverage": 85},
  "seo_health_after": {"profile": "full", "score": 84, "coverage": 85},
  "approval_requirement": "approved_fields:meta_title"
}
```

Candidate CSV rows remain proposals, never write instructions:

```csv
old_path,new_path,status_code,model,approved,applied,verified,reason
/legacy-slug,/reviewed-slug,301,123456,false,false,false,repository_has_no_redirect_applicator; external confirmation required
```

```csv
model,position,role,current_path,candidate_path,source_file,source_hash,classification,approval_requirement,copy_before_switch,preserve_original,besco_preserved
123456,1,main,catalog/01_main/123456/123456-1.jpg,catalog/01_main/123456/midea-example-1.jpg,catalog/01_main/123456/123456-1.jpg,sha256:<reviewed-hash>,review_required,approved_image_path_change,true,true,true
```

Before apply, `rollback_manifest.json` must show `created_before_apply: true`,
`complete: true`, `price_stock_status_excluded: true`, and a valid immutable
operation hash. `seo_health_summary.json` must show `weights_total: 100`,
`enforcement_mode: blockers_only`, and `strict_enabled_automatically: false`.

Review `products.csv` or `products.json` field by field. Every row includes the
current value, candidate value, classification, reason, evidence hashes,
before/after SEO health, and approval requirement. Classifications mean:

- `unchanged`: no write is needed or allowed.
- `safe_content_update`: review and list the field in `approved_fields` before
  any write.
- `review_required`: elevated review and an explicit field or dedicated
  slug/image approval is required.
- `blocked`: Phase 4 must not write the proposed value.
- `unavailable`: current or candidate evidence is missing; do not infer it.

Do not hand-edit a plan artifact. Fix the export or Phase 1-3 candidate, choose
a new run ID, rerun plan, and review the new hashes.
`plan.json` is the hash-verified authority used by apply; the split JSON/CSV
files are review views and are never reconstructed into an executable plan.

## Approval manifest

The approval file must be UTF-8 JSON with exactly the schema below. Unknown or
missing keys, duplicate JSON keys, duplicate models, invalid timestamps,
unsupported fields, and mismatched snapshot/run IDs are rejected.

```json
{
  "schema_version": "1.0",
  "snapshot_id": "pf4-production-20260712-01",
  "migration_run_id": "phase4-ac-20260712-01",
  "approved_by": "operator@example.com",
  "approved_at": "2026-07-12T12:30:00+03:00",
  "products": [
    {
      "model": "123456",
      "approved_fields": [
        "name",
        "meta_title",
        "meta_description",
        "meta_keywords",
        "related_products"
      ],
      "approved_slug_change": false,
      "approved_image_path_change": false,
      "notes": "Reviewed against products.json and approved for the canary."
    }
  ]
}
```

The example is structural, not an authorization. Remove every field that is
not an actual reviewed `safe_content_update` or `review_required` entry for
that model. Valid `approved_fields` are `name`, `description`, `meta_title`,
`meta_description`, `meta_keywords`, `category`, `filter_values`,
`manufacturer`, `mpn`, and `related_products` when the plan classifies them as
writable. GTIN/EAN/UPC/JAN/ISBN values remain report-only under the MPN-only
contract. Image-alt, structured-data, and feed candidates are also
report-only because this repository has no confirmed production consumer for
direct writes; a slug migration stages coupled artifact copies as evidence.

Never place `seo_keyword`, `canonical_url`, or
`gallery_image_candidate` in `approved_fields`. Use only the dedicated Boolean
flags. Never approve `status`, `active`, `price`, `quantity`, or
`stock_status`.

The approval manifest is the canary product selection. Membership in
`canary_proposal.json` alone does not approve anything.

## Redirect confirmation

Existing slugs remain unchanged when `approved_slug_change` is `false`. When
it is `true`, coordinate with the actual redirect owner before apply. The
external system must install and verify the exact 301 rule. Only that operator
may set `applied` and `verified` to `true`.

The structural shape accepted by apply is shown below. The one-row namespace
is deliberately abbreviated and is not valid production completeness evidence.

```json
{
  "schema_version": "1.0",
  "environment": "production",
  "target_identity": "opencart-target:sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "migration_run_id": "phase4-ac-20260712-01",
  "snapshot_id": "pf4-production-20260712-01",
  "plan_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "responsible_system": "opencart-redirect-owner",
  "confirmed_by": "redirect-operator@example.com",
  "confirmed_at": "2026-07-12T12:45:00+03:00",
  "redirects": [
    {
      "old_path": "/old-slug",
      "new_path": "/new-slug",
      "status_code": 301,
      "model": "123456",
      "approved": true,
      "applied": true,
      "verified": true
    }
  ],
  "removed_redirects": [],
  "seo_url_namespace": {
    "schema_version": "1.0",
    "source_identity": "opencart-global-seo-url-export:20260712T121500Z",
    "target_identity": "opencart-target:sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "migration_run_id": "phase4-ac-20260712-01",
    "snapshot_id": "pf4-production-20260712-01",
    "plan_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "captured_at": "2026-07-12T12:40:00+03:00",
    "complete": true,
    "row_count": 1,
    "content_hash": "sha256:097095d507029e7a84cb3acc2e1537cfc3baaacd98740ac629d16d99fbb66da1",
    "paths": ["/old-slug"]
  }
}
```

The wrapper and namespace evidence are bound to the same run, snapshot, plan
hash, and resolved target fingerprint as the snapshot and publisher. Evidence
must be no more than 24 hours old, must not predate either the reviewed plan or
the approval, and the
namespace capture must not be newer than its confirmation. Each redirect entry
has an exact shape; unknown or missing keys are rejected. The old/new paths and
model must match `redirect_candidates.csv`. Retain the external change ticket
and verification evidence alongside this JSON. The repository consumes this
confirmation but does not apply or independently own the redirect. If the
redirect cannot be applied and verified, keep the slug locked.

The namespace block must be a complete, hash-verified export of the global
OpenCart SEO URL namespace, including product, category, manufacturer, and
information routes. Product-only uniqueness is insufficient. The proposed new
path must be absent. Namespace uniqueness and its content hash use conservative
routing normalization (UTF-8 percent decoding, Unicode normalization,
case-folding, duplicate-slash collapse, and trailing-slash removal), so route
aliases such as `/Foo`, `/foo/`, and percent-encoded equivalents cannot bypass
the collision check. `paths`, `row_count`, and `content_hash` must come from the
complete target export; never copy the abbreviated example. An incomplete or
older-than-24-hours namespace blocks the slug migration.

Once valid confirmation establishes that a forward redirect is already live,
apply immediately writes `redirect_cleanup_required.json` before later health,
artifact, image, or importer preflights. If apply then fails before its catalog
claim/write boundary, do not delete or edit that evidence. Obtain verified
reverse/removal confirmation and run the normal rollback command; cleanup-only
rollback is supported even when `apply.claim.json` was never created.

For rollback of a slug migration, install and verify the reverse redirect in
the external system first, then provide a separate confirmation file showing
the new path as `old_path` and the restored path as `new_path`.
That rollback confirmation must also list the original forward rule in
`removed_redirects` with `removed` and `verified` true; otherwise both rules
could form a redirect loop. Its fresh global namespace must prove the restored
path is available. Reverse confirmation and namespace evidence must be no more
than 24 hours old and must not predate the apply claim; for cleanup-only
rollback with no claim, they must not predate the reviewed plan.

## Image-copy safety

Keep `approved_image_path_change` false for normal existing-product rollout.
Descriptive names in `image_candidates.csv` are review candidates, not rename
instructions.

For an exceptional approved image change:

1. Confirm every current path, proposed path, position, role, and source file
   in `image_candidates.csv`. Generate the plan with `plan --image-root` and
   review the published source's computed SHA-256 in `source_hash`; apply
   rejects an absent, malformed, or changed source hash. Never hand-edit and
   rehash `plan.json`.
2. Confirm the path is exactly `catalog/01_main/{model}/{filename}.jpg`.
3. Confirm neither old nor new path is a `besco#.jpg` description asset.
4. Supply `--image-root` pointing to the local root above `catalog/`.
5. Supply `--live-validate` and confirm the public page and image URLs are
   ordinarily reachable without bypassing access controls. Image-path apply
   cannot proceed with live validation unavailable.
6. Apply copies or converts to JPG, verifies the local target hash, confirms
   the source still exists, uploads only the copy, and verifies its public
   hash before switching catalog references.
7. Verify all OpenCart and description HTML references and gallery order.
8. Keep the original local and remote image. Initial migration and rollback do
   not delete copied targets.

If a target already exists with different content, a source is missing, a path
escapes the model directory, a JPG is invalid, or any description reference is
left behind, apply fails closed.

## Canary workflow

1. Review `canary_proposal.json`. Confirm the proposed 5-10 models cover the
   intended mix of series/no-series, legacy/descriptive images, and
   with/without GTIN where available. Missing GTIN is report-only under the
   current MPN-only publishing contract.
2. Decide the cohort explicitly. Include inactive products only when the
   operator intentionally accepts that model. Put only those models and fields
   in the approval manifest.
3. When a compatible non-production OpenCart target is available, rehearse the
   partial import and rendered output there using the organization's approved
   non-production procedure. The Phase 4 `apply` command intentionally rejects
   every environment other than the exact string `production`; do not bypass
   that gate or pretend a production run is staging. If no compatible target
   exists, record the rehearsal as unavailable and complete offline import and
   artifact review instead.
4. Obtain a fresh full production export immediately before production apply.
   It must hash to the snapshot catalog hash. If it does not, stop and create a
   new snapshot, run, and approval. Start the documented catalog change freeze
   before this export and allow no unrelated catalog mutation until the
   post-apply export and monitor report are complete and reviewed.
5. Confirm the OpenCart import profile is explicitly intended for partial
   updates and does not clear unspecified fields. The Step 1/2 UI must expose
   create, delete, and disable/deactivate controls and the preflight must
   positively attest all three as safe. Each live result must report one line
   processed, zero products/categories created, zero products deleted or
   disabled, one expected product updated, and no protected or unexpected
   mappings. Ambiguous/missing controls or counters fail closed. Confirm normal
   database and image backups are complete. Category and manufacturer
   candidates must exactly match a value already present in the snapshot;
   every filter candidate must already exist under the same exact
   `filter_group:*` header. New taxonomy entity/value creation is forbidden in
   this migration.
6. Run the production canary with `--canary`. Add `--live-validate` only when
   ordinary public HTTP access is expected for a content-only run; it is
   mandatory for an approved image-path run. Add image or redirect options only
   for models with the corresponding Boolean approval.

Content-only canary command:

```powershell
.\.venv\Scripts\python.exe -m product_factory.seo_migration apply `
  --apply `
  --environment production `
  --snapshot-id "$SnapshotId" `
  --migration-run-id "$RunId" `
  --approval-file "$ApprovalFile" `
  --catalog-export "$FreshFullExport" `
  --confirm-production-write "APPLY $RunId" `
  --target-identity "$TargetIdentity" `
  --publisher opencart `
  --opencart-import-profile "$ImportProfile" `
  --canary `
  --live-validate `
  --output-root "$OutputRoot"
```

When the reviewed canary contains approved image and slug changes, add:

```powershell
--image-root "$ImageRoot" `
--redirect-confirmation-file "$RedirectConfirmation"
```

Apply validates the immutable snapshot and plan hashes, exact production
environment, exact `APPLY {migration_run_id}` confirmation, snapshot-bound
target fingerprint against the resolved import profile, fresh full-catalog
hash, approval schema and scope, canary proposal, approval-effective SEO
health, redirect confirmation, image safety, and a complete pre-apply rollback
manifest. It generates a one-row partial CSV per model, verifies protected
columns are absent, and confirms every Step 2 mapping in dry-run before any
image or catalog write. The run claim is permanent, while each model's adapter
authorization is issued only when that model reaches the write boundary,
expires after 30 minutes, and is durably consumed before the live adapter
action.

Apply stops on the first import, image, audit, or blocking live-validation
failure. A prior product may already have been updated; inspect
`apply_result.json` and `audit.jsonl` before doing anything else.
Immediately before the first write, apply creates a permanent one-shot
`apply.claim.json`. The same run cannot be applied again, including after a
partial failure; use verified rollback or create a new snapshot/run/approval.

Karapuz confirmation proves the bounded adapter action and its counters; it is
not a fresh observed catalog diff. Immediately after the canary, export the
complete catalog again and run `monitor` before releasing the change freeze or
expanding. Confirm every approved value and confirm no collateral product,
status, price, quantity, stock, slug, or image-path drift. Stop and reconcile or
roll back on any mismatch. Monitoring compares the normalized supported
catalog fields; the operator must separately compare export-only/unsupported
columns.

After the canary observation gates pass, take a new full export, create a new
snapshot and run, review a new plan, and obtain a new approval for the intended
remaining air-conditioner cohort. The expansion command is the same explicit
production apply without `--canary`:

```powershell
.\.venv\Scripts\python.exe -m product_factory.seo_migration apply `
  --apply `
  --environment production `
  --snapshot-id "$SnapshotId" `
  --migration-run-id "$RunId" `
  --approval-file "$ApprovalFile" `
  --catalog-export "$FreshFullExport" `
  --confirm-production-write "APPLY $RunId" `
  --target-identity "$TargetIdentity" `
  --publisher opencart `
  --opencart-import-profile "$ImportProfile" `
  --live-validate `
  --output-root "$OutputRoot"
```

For this command, every variable must refer to the new post-canary
snapshot/run. Omitting `--canary` does not approve products or fields; the new
machine-readable approval remains the exact write boundary.

## Live validation

Run an isolated live check without a production write:

```powershell
.\.venv\Scripts\python.exe -m product_factory.seo_migration validate-live `
  --snapshot-id "$SnapshotId" `
  --model 123456 `
  --target-url "https://www.example.test/product-path" `
  --migration-run-id "$RunId" `
  --approval-file "$ApprovalFile" `
  --timeout-seconds 10 `
  --output-root "$OutputRoot"
```

If `--target-url` is omitted, the validator uses the snapshot's product or
canonical URL. It checks HTTP success, final and canonical URLs, title, Meta
Description, visible H1 and description H2, main image, gallery order,
description-image references, Product JSON-LD, Offer price and availability,
MPN/expected GTIN, and internal links.
Reviewed Phase 2 `internal_links` are merged only when description, category,
or related-product changes were actually approved/applied; the reviewed
`description_heading` is merged only for an approved/applied description.
Unapproved candidate state is never treated as published expectation. If
neither approval-effective plan evidence nor a published description H2 is
available, those individual checks stay `not_run` and remain manual rather
than passing an arbitrary page element.

The validator uses bounded ordinary HTTP GETs, validates and follows redirects
manually, rejects private/local/reserved network destinations at every hop,
and does not send credentials, cookies, authentication workarounds, browser
automation, or anti-bot bypass material. If no URL is configured or access is
unavailable, every check is `not_run`, coverage is reduced, and the report
contains a manual checklist. `not_run` is not a pass. A failed fetch alone is
not evidence that Googlebot is blocked.

With `--migration-run-id`, the standalone result is stored at:

```text
{output_root}/{migration_run_id}/live_validation/{model}.json
```

Use `--live-validate` on `apply` when live results must be embedded in
`apply_result.json`. With a run ID, `validate-live` uses the sealed
`apply.approval.json` automatically when present; `--approval-file` can supply
the exact applied approval explicitly. It then evaluates the expected applied
state for models whose apply state is not unattempted or rolled back.
Monitoring prefers a newer standalone `{run}/live_validation/{model}.json`
over the embedded apply result, so a deliberate post-apply recheck supersedes
the earlier evidence.

## Post-rollout monitoring

After the canary, obtain another complete production export and run:

```powershell
$PostApplyFullExport = "D:\secured-exports\opencart-full-20260712T130000Z.csv"

.\.venv\Scripts\python.exe -m product_factory.seo_migration monitor `
  --migration-run-id "$RunId" `
  --snapshot-id "$SnapshotId" `
  --current-catalog-export "$PostApplyFullExport" `
  --approval-file "$ApprovalFile" `
  --output-root "$OutputRoot"
```

The command writes a timestamped report under
`{run}/monitoring/`. It reports blocking SEO-health failures, score
regressions, unexpected slug changes, image-path regressions, missing
identifiers, price/schema mismatches, unavailable structured-data artifacts,
duplicate-content increases, failed or not-run live checks, and rollback
availability. Missing GTIN remains a non-blocking report under the current
MPN-only contract; missing MPN is a failure.
`monitor` does not resolve a target fingerprint from the export itself. The
operator must prove that the post-apply export came from the same target and
export definition recorded by the snapshot/apply evidence, and must manually
compare fields outside the normalized monitoring set such as export-only IDs
or timestamps.

Exit code 3 means either `blocking_findings` is nonzero or at least one product
report has failed, including a failed non-blocking finding. Freeze expansion,
investigate the individual findings, and decide whether to repair or roll back.
Monitoring never rolls back automatically.

Complete the separate manual Search Console procedure in
`search-console-validation.md` before expanding the cohort.

## Rollback

Rollback is a production write. First obtain a new full export representing
the current state after the apply or partial failure. Rollback verifies that
each value still equals the expected applied value before overwriting it. If
another operator or sync changed a field, rollback refuses to overwrite it.
An explicit rollback also supports a hard-crash state where
`apply_result.json` still says `running`: reviewed operations are reconstructed
from the sealed plan/approval, exact claimed patches, and durable write-start
and rollback audit events rather than mutable manifest flags.

```powershell
$CurrentFullExport = "D:\secured-exports\opencart-full-20260712T133000Z.csv"

.\.venv\Scripts\python.exe -m product_factory.seo_migration rollback `
  --rollback "$RunId" `
  --environment production `
  --current-catalog-export "$CurrentFullExport" `
  --confirm-production-write "ROLLBACK $RunId" `
  --target-identity "$TargetIdentity" `
  --publisher opencart `
  --opencart-import-profile "$ImportProfile" `
  --output-root "$OutputRoot"
```

If the apply changed a slug, add the externally applied and verified reverse
redirect confirmation:

```powershell
--redirect-confirmation-file "D:\approvals\phase4-ac-20260712-01.reverse-redirects.json"
```

Rollback restores only operations recorded as applied: approved catalog
content, metadata, SEO keyword/canonical values, MPN, image
references, related products, and approved categories/filters. It excludes
price, quantity, stock status, and activation. Original images remain; copied
targets are not deleted. Coupled migration-generated structured-data/feed
bundles are verified against the expected applied state and restored from the
rollback manifest; they are not proof of a downstream publication, so
reconcile any separately published consumer manually.

Review `rollback_result.json`, the updated `rollback_manifest.json`, import
reports, and `audit.jsonl`. Then export the catalog again, rerun monitoring and
live checks, and validate any reverse redirect in its responsible system.
Rollback uses an exclusive active lock and checkpoints each completed model in
both the rollback manifest and result. A failed multi-product rollback can be
resumed for only the still-applied operations after a fresh current export.
During an explicit rollback only, a same-run/same-host apply lock whose recorded
process is provably dead is atomically archived under `recovery/stale-locks/`
and replaced. Live, malformed, other-run, or other-host locks remain blocked;
never delete them merely to make a command proceed.

## Failure recovery

- **Snapshot fails:** fix the UTF-8 full export or metadata and use a new
  snapshot ID. Do not weaken validation or edit a stored snapshot.
- **Plan has blocked/unavailable fields:** leave them unwritten. Correct the
  source export or candidate artifacts and create a new run.
- **Approval fails validation:** generate a new exact-schema approval. Never
  edit plan hashes or copy approval IDs from another run.
- **Fresh export is stale:** no write has occurred. Stop, take a new snapshot,
  re-plan, and obtain new approval. There is no force option.
- **Apply fails before adapter confirmation:** inspect `audit.jsonl`,
  `apply_result.json`, reports, and rollback manifest to establish whether any
  model was confirmed. Do not infer zero writes only from the CLI exit code.
- **Apply fails after one or more confirmed imports:** stop the cohort. Do not
  rerun apply blindly. Export current state and use the verified rollback path
  or create a new plan for an intentional forward repair.
- **Live validation fails after import:** the model may already be written and
  later models were not attempted. Preserve evidence, diagnose the page, and
  choose rollback or a newly approved repair.
- **Live validation is `not_run`:** record the coverage gap and execute the
  manual page and Search Console checklists. Do not relabel it as pass.
- **Image upload/copy fails:** retain both the source and any verified copy.
  Do not delete or manually switch references. Determine the confirmed import
  state from reports before rollback.
- **Redirect confirmation fails:** keep or restore the published slug. Resolve
  the external redirect with its owner; this repository cannot repair it.
- **Apply fails after a forward redirect was confirmed:** inspect
  `redirect_cleanup_required.json`. Even without `apply.claim.json`, obtain the
  reverse/removal confirmation and run the normal rollback command to verify
  cleanup; do not hand-edit the cleanup or rollback artifacts.
- **Monitor exits 3:** freeze expansion. Monitoring does not authorize or
  trigger rollback.
- **Rollback current-state verification fails:** do not overwrite the newer
  state. Reconcile each mismatch with the responsible operator and create an
  explicitly reviewed recovery action.

## Artifact, audit, and backup retention

Before apply, copy the following evidence to the organization's access-
controlled, immutable backup location without secrets:

- initial full export and its external export/job identity;
- snapshot directory and complete migration run directory;
- frozen Phase 1-3 candidate directory;
- exact approval file and its reviewer record;
- external redirect confirmation and change ticket, when applicable;
- standard OpenCart database backup and image-file backup identifiers.

After apply or rollback, retain `audit.jsonl`, `apply_result.json`,
`rollback_manifest.json`, `rollback_result.json` when present, per-model patch
and import/image reports, artifact bundles, standalone/live results,
monitoring reports, and every post-write full export.

The repository neither commits nor prunes `migration/`. Define an operational
retention period before production use and never remove the only rollback
manifest, original images, exact approval, redirect evidence, or source
exports while rollback or URL recovery may be needed. Keep credentials in the
existing OpenCart configuration mechanism, never in migration artifacts.

## Complete rollout sequence

1. Merge and deploy the migration tooling without running apply.
2. Generate and archive a full catalog snapshot.
3. Run a dry-run plan for air conditioners.
4. Review all blocked and review-required changes.
5. Review the proposed canary and approve an explicit product/field list.
6. Apply the canary to a compatible non-production environment when available,
   using its separately approved procedure; otherwise record the step as
   unavailable because this CLI does not write to non-production.
7. Validate partial-import artifacts and rendered output.
8. Apply the production canary only with the exact flags, fresh full export,
   machine-readable approval, normal backups, and any external redirect/image
   prerequisites.
9. Observe, monitor, run live checks, and complete manual Search Console
   validation.
10. Expand to remaining air conditioners only with a new post-canary full
    snapshot, new run, new review, and new approval.
11. Add other category profiles in separate future runs.
12. Keep existing slugs and images locked unless each migration is
    intentionally approved and externally supportable.
13. Enable strict SEO-health enforcement only after full backfill and a
    separate explicit operator decision.

Do not reuse the pre-canary snapshot to expand after the canary; the canary
itself changes the catalog hash and makes that snapshot stale.

## `blockers_only` to `strict`

The 100-point `full` SEO-health profile is initially enforced as
`blockers_only`. Phase totals are 45 points for Phase 1, 20 for Phase 2, 20 for
Phase 3, and 15 for Phase 4. Failed deterministic subchecks remain listed as
evidence.

The exact grouped contract is:

```text
PHASE 1 — 45
identity.completeness: 8
identity.series_and_models: 6
identity.capabilities_consistent: 4
meta_title.quality: 8
meta_description.quality: 8
seo_keyword.valid_and_stable: 8
contract.deterministic_ownership: 3

PHASE 2 — 20
images.gallery_filename_policy: 5
images.path_sequence_and_format: 4
images.alt_quality: 4
content.heading_structure: 2
internal_linking.related_and_category: 3
content.catalog_uniqueness: 2

PHASE 3 — 20
identifiers.validity_and_provenance: 5
structured_data.product_completeness: 5
structured_data.offer_consistency: 5
merchant.validation: 5

PHASE 4 — 15
rollout.migration_safety: 5
rollout.redirect_and_canonical_coverage: 4
rollout.production_validation: 3
rollout.monitoring_and_rollback: 3
```

`pass` earns full weight, `warn` earns half, and `fail` earns zero.
`not_applicable` is excluded from the denominator but counted as evaluated;
`not_run` is excluded from the denominator and lowers coverage. Scores use
`ROUND_HALF_UP`, and every failed deterministic subcheck remains in evidence.
A representative `seo_health_summary.json` is:

```json
{
  "schema_version": "1.0",
  "profile": "full",
  "weights_total": 100,
  "enforcement_mode": "blockers_only",
  "strict_enabled_automatically": false,
  "product_count": 1,
  "blocking_failures": 0,
  "score_regressions": 0,
  "products": [
    {
      "model": "123456",
      "before_score": 78,
      "after_score": 84,
      "score_delta": 6,
      "before_coverage": 85,
      "after_coverage": 85,
      "blocking_failures": 0,
      "enforcement_mode": "blockers_only"
    }
  ]
}
```

The migration CLI never enables `strict`. A separate operator-controlled
settings change may select `strict` only after all of these are documented:

1. Catalog backfill is complete for the intended scope.
2. Every product's full-profile score is at least 80.
3. Coverage is exactly 100 percent; no `not_run` checks remain.
4. Blocking failures are zero.
5. The operator explicitly approves and performs the settings change through
   normal configuration change control.

If any gate later regresses, stop expansion and review enforcement; do not
silently toggle modes. `resources/settings/product_factory_settings.json`
remains `blockers_only` until the separate approved change is made.

## Remaining manual production steps

- Produce the initial and every fresh full OpenCart export with the required
  fields and a stable non-secret source identity.
- Freeze and archive the exact Phase 1-3 candidate artifacts.
- Verify normal database and image backups outside this repository.
- Establish the catalog change freeze for OpenCart administrators, scheduled
  stock/price writers, and other importers across each fresh-export/apply/post-
  export window; the Phase 4 lock cannot stop those external writers.
- Review every proposed field, canary model, inactive product, slug, image,
  identifier, category, and filter change.
- Create and retain the signed-off machine-readable approval.
- Configure and validate the Karapuz partial-import profile in a compatible
  non-production environment when available.
- Have the responsible external system apply and verify any forward or reverse
  redirects; this repository cannot do it.
- Confirm image roots, source files, remote originals, storage capacity, and
  OpenCart file-manager permissions for any exceptional image copy.
- Run and review production canary commands; no scheduler performs them.
- Produce the immediate post-apply full export and use monitoring to verify the
  exact approved diff plus zero collateral status, price, stock, slug, image,
  or other-product drift before ending the freeze.
- Inspect OpenCart pages, import reports, audit records, monitoring findings,
  and the manual Search Console evidence.
- Reconcile locally staged structured-data/feed bundles with every actual
  downstream consumer. This repository has no confirmed production publisher
  for those consumers and never reports local staging as downstream apply.
- Decide whether to expand, repair, or roll back. No command expands or rolls
  back automatically.
- Archive all evidence under the organization's retention and access policy.
- Approve strict enforcement separately only after every manual gate passes.

Do not record that production was updated unless `apply_result.json`, the
OpenCart adapter report, and the audit log all confirm the write.
