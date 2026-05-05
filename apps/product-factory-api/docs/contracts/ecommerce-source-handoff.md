# Price-Fetcher Source Handoff

Product Factory emits a source URL evidence artifact after a successful prepare source acquisition:

```text
work/{model}/integrations/ecommerce_source_handoff.json
```

This artifact is a file-based integration contract. Product Factory owns fetching supported product URLs, parsing the source page, normalizing source evidence, and writing the JSON handoff. The ecommerce-api service is the importer and database owner: it decides when to read the artifact, how to validate it, and how to persist source URL evidence in its own storage.

Product Factory does not connect to the ecommerce-api database, import ecommerce-api code, call ecommerce-api APIs, or change the OpenCart CSV schema for this handoff.

## Contract

The current `schema_version` is `1.0`. The success payload contains:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-05-05T10:20:30+00:00",
  "model": "233541",
  "input_url": "https://www.electronet.gr/...",
  "source": "electronet",
  "provider_id": "electronet",
  "requested_url": "https://www.electronet.gr/...",
  "final_url": "https://www.electronet.gr/...",
  "canonical_url": "https://www.electronet.gr/...",
  "source_name": "electronet",
  "source_domain": "www.electronet.gr",
  "product": {
    "name": "",
    "brand": "",
    "manufacturer": "",
    "mpn": "",
    "product_code": "",
    "page_type": "product",
    "price": null,
    "currency": null,
    "availability": "",
    "stock_status": ""
  },
  "evidence": {
    "title": "",
    "mpn": "",
    "model": "233541",
    "brand": "",
    "price": null,
    "category": "",
    "provenance": {},
    "field_diagnostics": {}
  },
  "fetch": {
    "method": "",
    "status_code": null,
    "content_type": "",
    "fallback_used": false
  },
  "warnings": [],
  "missing_fields": [],
  "critical_missing": [],
  "artifact_refs": {
    "source_json": "work/233541/scrape/233541.source.json",
    "report_json": "work/233541/scrape/233541.report.json"
  }
}
```

If prepare fails after source acquisition has produced useful fetch and parsed product evidence, Product Factory writes the same payload shape with additional `status` and `error` fields. Failures before safe source acquisition do not create a handoff.

The JSON is written as UTF-8 without BOM through the repo JSON writer and is intended to be stable enough for ecommerce-api contract tests.
