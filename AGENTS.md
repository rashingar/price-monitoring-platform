# Repository Codex Instructions

This repository contains multiple apps. For Product Factory work, always read and follow:

- `apps/product-factory-api/AGENTS.md`
- `apps/product-factory-api/RULES.md`

Those files are authoritative for runtime commands, validation, generated artifact ownership, and completion reporting.

## Product Factory Chat Input Helper

When the user pastes one or more blocks in this shape, treat it as an operator request to run the full Product Factory workflow:

```text
---
model:
url:
photos:
sections:
skroutz_status:
boxnow:
price:
```

The leading `---` is a record separator. A message may contain one block or multiple blocks. Process each product block independently, in the order provided, and do not run prepare/render concurrently for the same model.

Field meanings:

- `model`: required 6-digit OpenCart/Product Factory model code.
- `url`: required product source URL supported by the Product Factory source-detection layer.
- `photos`: requested number of product photos; default `1` when omitted.
- `sections`: requested number of presentation sections; default `0` when omitted.
- `skroutz_status`: OpenCart/Skroutz status flag passed to Product Factory; default `0` when omitted.
- `boxnow`: Box Now availability flag passed to Product Factory; default `0` when omitted.
- `price`: product price passed to Product Factory; default `0` when omitted.

For Product Factory generation jobs, the operator-provided `url` is the canonical source URL for that model. Recognize it directly as the source URL, validate it with the Product Factory source-detection layer, and pass it unchanged to `product_factory.workflow prepare --url`.

Do not interpret these blocks as ecommerce source URL imports, price-monitoring observations, catalog CSV rows, or review notes. They are Product Factory generation jobs.

For every valid block, run the Product Factory flow from the repository root exactly as defined in `apps/product-factory-api/AGENTS.md` and `apps/product-factory-api/RULES.md`:

1. Validate the model and source URL support.
2. Run `product_factory.workflow prepare` with the provided fields.
3. Inspect generated scrape and LLM prompt artifacts.
4. Write only the LLM-owned output files.
5. Run `product_factory.workflow render`.
6. Run the separate OpenCart publish phase when render produces `products/{model}.csv`.
7. Report results using the fixed Product Factory completion template.

If `model` is missing or not exactly 6 digits, fail with:

```text
Generation failed, provide 6-digit model
```

## Source URL Agent / Find Source Namespace

Source URL Agent, shown in the UI as Find Source, owns product source URL discovery, candidate runs, candidate review, and source URL candidate promotion. Its canonical backend namespace is `/api/source-url-agent/...`; through the web proxy, frontend calls must resolve as `/commerce-api/source-url-agent/...`.

Vendor Sources owns vendor/source health, source URL capture, diagnostics, and capture run history. Do not place Source URL Agent routes under `/api/vendor-sources/...`, and do not reintroduce DB-backed candidate review layout preferences unless explicitly requested. Candidate review layout stays frontend-local.
