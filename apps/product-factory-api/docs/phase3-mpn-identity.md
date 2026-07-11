# Phase 3: MPN-first product identity

Product Factory uses the six-digit OpenCart/ERP model as its internal product
key. The manufacturer MPN is the only external product identifier in the
catalog contract. Other identifier families are intentionally outside Product
Factory output and publishing; their absence is neither a warning nor a gate.

Phase 3 is opt-in through `identity_phase3.enabled` in
`resources/settings/product_factory_settings.json`. It applies enforcement to
`identity_phase3.families`, initially `air_conditioner`. Other families retain
their existing deterministic names, CSV values, slug behavior, and validation
path while the candidate artifacts remain advisory.

## Identity selection

The resolver prefers an existing trusted product MPN, then explicit exact
source evidence (official/manufacturer, Electronet, then supported trusted
retailers), and finally a conservative exact-title extraction. Title-only
values are inferred, not verified. Display normalization retains meaningful
case, hyphens, slashes, periods, and leading zeroes; a separate comparison form
is used only for equality checks.

For split air conditioners, a verified sellable set such as
`EF-12RD1H/MX1-12RD1H` remains the MPN and `set_model`. Its components remain
ordered in `component_models`, and `primary_model` may use the indoor model for
compact title budgets. If a complete-set candidate conflicts with a component
candidate, the identity is `conflicting`, the evidence remains visible, and
automatic publish is blocked for active air-conditioner enforcement.

An audited override can be placed at
`identity_phase3.mpn_overrides.<six-digit-model>` with `value`, `scope`, and
`reason`. It is recorded as `manual_override`, never as manufacturer evidence.
Overrides must still pass syntax, internal-model, and scope checks.

## Candidate artifacts

An enabled render writes these non-storefront candidates under
`work/<model>/candidate/`:

- `<model>.product_identity.json` contains selection, provenance, candidates,
  components, and conflicts.
- `<model>.product_structured_data.json` is schema.org-compatible Product data
  with internal `sku`, brand, final public image URLs, and MPN only when
  verified.
- `<model>.product_feed.json` is an internal feed candidate with
  `identifier_mode: "mpn_only"`; it is not an external upload.

The existing OpenCart CSV/API contract is unchanged: its current `mpn` field
is retained and no columns are added. Candidate artifacts are checked against
the CSV and included in SEO health. Active air-conditioner failures include
conflicts, internal-model substitution, mismatched MPN output, invalid
candidate JSON, and unsupported identifier fields.
