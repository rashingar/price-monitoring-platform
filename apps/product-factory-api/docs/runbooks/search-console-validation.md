# Manual Search Console Validation for SEO Migration

This is a manual-only companion to the Product Factory SEO migration runbook.
It does not use the Search Console API, service accounts, OAuth tokens, browser
automation, or stored Search Console credentials. Perform it only through an
operator's authorized Search Console session and the normal public storefront.

Search Console is delayed observational evidence, not the production writer
and not a substitute for OpenCart import reports, HTTP validation, redirect
ownership, or the Phase 4 audit log.

## Scope and evidence sheet

Create one review row for every approved canary model before opening Search
Console. Record the following outside Search Console:

- migration run ID and snapshot ID;
- six-digit model and active/inactive state;
- apply timestamp;
- old and expected final URL;
- whether the slug was intentionally changed;
- externally confirmed redirect ticket, when applicable;
- expected canonical URL;
- expected title, Meta Description, H1, main image, MPN, price, and
  availability;
- `apply_result.json` status and per-model import report;
- Phase 4 live-validation status and coverage;
- reviewer, review timestamp, and final disposition.

Store a sanitized completed checklist and screenshots or exports with the
migration evidence, for example under:

```text
migration/{migration_run_id}/manual/search-console/
```

Do not store session cookies, account identifiers that violate company policy,
authentication URLs, or screenshots containing unrelated property data.

## Preconditions

Before requesting indexing or interpreting Search Console:

1. Confirm the correct production property and URL variant. Do not validate a
   staging property or a different HTTP/HTTPS or host variant by mistake.
2. Confirm the OpenCart adapter and audit log report the model as applied.
3. Confirm the public page with the repository live validator or a normal
   browser: HTTP success, final URL, canonical, title, Meta Description, H1,
   description H2, images and order, Product JSON-LD, Offer price and
   availability, MPN/expected GTIN, and internal links.
4. For an intentional slug migration, obtain proof from the redirect owner
   that the old path returns one permanent 301 path to the approved new path.
   Do not infer this from the approval JSON alone.
5. Confirm there are no blocking SEO-health or monitoring findings and that a
   rollback manifest remains available.

If live page access is unavailable, keep repository checks as `not_run` and
coverage reduced. Search Console inspection may still provide separate Google
fetch evidence, but it does not retroactively convert the repository result to
pass.

## Baseline before a slug change

For the small approved slug-migration cohort, inspect each old URL before the
production change when practical. Record:

- whether Google knows or indexes the old URL;
- the user-declared canonical;
- the Google-selected canonical;
- last crawl time and page-fetch status;
- any Product or merchant enhancement status shown;
- a Performance report comparison window and the old URL's clicks,
  impressions, CTR, and average position.

For content-only migrations with a locked URL, record the same URL as both old
and expected final. Do not create a redirect task.

## URL Inspection after apply

For each approved final URL:

1. Enter the complete final URL in URL Inspection.
2. Record the indexed result separately from the live result. The initial
   report describes Google's indexed version and can lag behind production.
3. Record whether the URL is known/indexed, the last crawl time, page fetch,
   crawl permission, indexing permission, user-declared canonical, and
   Google-selected canonical.
4. Run **Test live URL**. Record the test time and whether the page can be
   fetched and indexed. A positive live result is not a guarantee of indexing.
5. When available, inspect the returned/crawled HTML and screenshot. Compare
   the canonical, title, Meta Description, visible H1/content, primary image,
   and Product JSON-LD with the approved values and the local live report.
6. Review Product/merchant enhancement information if Search Console detected
   it. Record every warning or error; absence of an enhancement report is not
   proof that structured data is unavailable or valid.
7. Request indexing only for the approved final canonical after the live page,
   canonical, redirect, and structured-data checks pass. Do not request
   indexing for an old redirected URL.

Use these dispositions:

- `pass`: the live URL is fetchable/indexable, declared canonical is correct,
  no blocking contradiction is present, and any expected enhancement evidence
  is acceptable.
- `pending_recrawl`: the live page passes but the indexed version is older.
- `warn`: the page is available but a non-blocking enhancement or metadata
  discrepancy needs review.
- `fail`: fetch/indexing is blocked unexpectedly, the canonical is wrong, a
  required redirect is absent, or Google sees materially inconsistent product
  data.
- `not_run`: the operator lacks access, the property is unavailable, or the
  check could not be performed. Preserve the coverage gap.

Do not use a Search Console fetch failure by itself to claim that Googlebot is
blocked. Record the reported crawl permission, page-fetch reason, indexing
permission, tested URL, time, and any site-wide incident, then compare with
normal public HTTP and server/CDN logs owned by the responsible team.

## Old URL and redirect validation

Only perform this section for an individually approved slug change.

1. Verify the old path outside Search Console with an ordinary unauthenticated
   request. Record each hop, status, and final URL. The approved requirement is
   a 301 from the exact old path to the exact new path, without a loop or an
   unrelated intermediate destination.
2. Inspect the old URL in Search Console and record the indexed state. It may
   eventually be reported as redirected or otherwise not indexed; processing
   is not immediate.
3. Inspect the new URL and confirm its user-declared canonical is self-
   consistent and matches the approved target.
4. Watch for `Duplicate, Google chose different canonical than user` or a
   Google-selected canonical that points to another product. Treat that as a
   blocking investigation for cohort expansion.
5. Confirm internal links, feed links, structured-data URLs, and submitted
   sitemap references use the final URL. Search Console does not update those
   systems for this repository.

Keep the old URL and image files available according to the rollback and
retention policy. Do not remove the external redirect when observation first
looks healthy.

## Page indexing and sitemap review

After the live inspections:

1. Review the Page indexing report for the canary URL set and relevant issue
   categories. Record new redirect, canonical, blocked, `noindex`, fetch, or
   duplicate issues.
2. Confirm important final canonical URLs are eligible for indexing. Do not
   expect every discovered alternate or redirected URL to be indexed.
3. Review the submitted sitemap manually. Confirm the final canonical is
   present and the old slug is not newly submitted. Record the sitemap's last
   read and reported processing status when available.
4. If a sitemap or indexing issue is property-wide, stop attributing it to one
   migration model until the responsible team confirms the scope.

Google processing can take time. Mark an indexed-state mismatch
`pending_recrawl` when the live test and production evidence are correct; do
not repeatedly change slugs or canonicals to force an immediate indexed-state
change.

## Product and merchant evidence

For every canary product, compare Search Console evidence and the public page
with the approved Product Factory artifacts:

- Product name, canonical URL, primary image, SKU/internal model, and MPN;
- Offer price, currency, and availability;
- supported identifier mode. The current publishing contract is MPN-only, so
  missing GTIN is report-only unless a separately approved contract changes;
- structured-data Product and Offer consistency;
- feed link, image link, price, availability, brand, and MPN when merchant
  evidence is available.

A price or availability mismatch is a production-data incident for
investigation, not authorization for this SEO migration to update price or
stock. Leave those fields to their existing synchronization owners.

## Performance observation

Use the Search results Performance report manually after enough data is
available:

1. Save the selected date range and use a comparable previous period.
2. Filter by the final page URL and record clicks, impressions, CTR, and
   average position. Focus on trends rather than a single position value.
3. For a slug migration, check both old and new paths. Search Console commonly
   assigns performance data to the canonical URL, so do not add old and new
   rows blindly or interpret a missing old-path row as traffic loss.
4. Review material changes by query and page. Separate expected recrawl lag,
   seasonality, and catalog availability changes from migration regressions.
5. Record observation dates and disposition. Search Console data is delayed;
   absence of immediate impressions is not itself a rollback trigger.

Use the organization's agreed observation window. Phase 4 does not schedule
or automate this review.

## Stop and escalate conditions

Freeze cohort expansion when any of these occurs:

- wrong final URL or redirect destination;
- missing, temporary, looping, or unverified redirect;
- unexpected canonical or Google-selected canonical for another product;
- public page cannot be fetched or is unexpectedly blocked from indexing;
- title, Meta Description, H1, main image, MPN, price, or availability differs
  materially from the approved/live catalog state;
- Product/Offer structured data is unavailable or materially inconsistent;
- new duplicate-content or canonical issues increase for the cohort;
- Search Console evidence conflicts with HTTP, OpenCart, or audit evidence;
- rollback evidence is incomplete or unavailable.

Do not change production from Search Console. Return to the migration runbook,
obtain a fresh full catalog export, inspect monitoring and audit evidence, and
choose an explicitly approved forward fix or verified rollback.

## Completion record

The canary's manual Search Console step is complete only when the review sheet
contains, for every approved model:

- final URL inspection and live-test evidence or explicit `not_run` reason;
- user-declared and Google-selected canonical observations;
- page fetch, crawl, and indexing permission observations;
- redirect evidence for every changed slug;
- structured-data/enhancement observations;
- sitemap and Page indexing review disposition;
- baseline and follow-up Performance observation dates;
- reviewer, timestamp, findings, and expand/hold/rollback recommendation.

Search Console access or a clean live test does not authorize expansion. The
operator must also review the Phase 4 monitoring report, import reports,
SEO-health blockers, live-validation coverage, rollback availability, and
normal production observation.

## Official manual references

- [URL Inspection tool](https://support.google.com/webmasters/answer/9012289)
- [Inspect and troubleshoot a single page](https://support.google.com/webmasters/answer/12482179)
- [Check whether a URL or image is available to Google](https://support.google.com/webmasters/answer/12061956)
- [Page indexing report](https://support.google.com/webmasters/answer/7440203)
- [Search results Performance report tasks](https://support.google.com/webmasters/answer/17010961)
- [Performance dimensions and canonical aggregation](https://support.google.com/webmasters/answer/17011259)

These links support a manual operator workflow only. Do not add Search Console
API credentials or integration code without a separate, explicitly scoped
authorization.
