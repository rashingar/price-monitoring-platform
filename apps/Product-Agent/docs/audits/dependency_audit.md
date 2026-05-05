# Dependency Ownership Audit

Historical note:
- This audit records the M8 dependency-ownership state from before M10 consolidated to one canonical repo-root `requirements.txt`.
- References below to `scrapper/requirements.txt` describe the pre-M10 layout and are preserved as prior-state evidence, not as current install guidance.

## Evidence Used
- file inspection of `requirements.txt`
- file inspection of `scrapper/requirements.txt`
- repo-wide `rg` for `requirements.txt`, `scrapper/requirements.txt`, install commands, and dependency setup references
- live import scan for packages declared in either dependency file
- baseline validation from `python -m pytest -q` run from `scrapper/`

## Side-by-Side Comparison Summary

| File | Declared packages | Overlap | File-only entries | Evidence summary |
| --- | --- | --- | --- | --- |
| `requirements.txt` | `beautifulsoup4`, `lxml`, `requests`, `pillow`, `pillow-avif-plugin`, `pypdf` | `beautifulsoup4`, `lxml`, `pypdf` | `requests`, `pillow`, `pillow-avif-plugin` | Root file is unpinned and partially overlaps the scraper file. `pillow` and `pillow-avif-plugin` match live scraper imports; no live `requests` import was found in the current repo. |
| `scrapper/requirements.txt` | `httpx`, `beautifulsoup4`, `lxml`, `playwright`, `pytest`, `pypdf` | `beautifulsoup4`, `lxml`, `pypdf` | `httpx`, `playwright`, `pytest` | Scraper file is version-pinned and matches the active install instructions, but it does not include `pillow` or `pillow-avif-plugin`, which are imported by current scraper code. |

## Current Usage
- Current install instructions point to `scrapper/requirements.txt` only:
  - `scrapper/README.md` instructs `pip install -r requirements.txt` from inside `scrapper/`
  - no active repo-level install guide points to root `requirements.txt`
- Current control docs treat root `requirements.txt` as unresolved rather than authoritative:
  - `PLAN.md` kept `requirements.txt` in root only until this audit
  - `DOCUMENTATION.md` and `docs/audits/repo_cleanup_audit.md` both carried it as `uncertain` pending M8
  - `IMPLEMENT.md` already contains a guardrail not to change either dependency file before this audit result exists
- Live import evidence shows scraper/runtime usage spans both files' declared package sets:
  - `scrapper/electronet_single_import/fetcher.py` imports `httpx` and `playwright`
  - scraper parsing and enrichment modules import `beautifulsoup4`
  - scraper image code imports `PIL` and `pillow_avif`
  - no live `requests` import was found in the current repo

## Dependency Ownership Assessment
- `scrapper/requirements.txt` is the only dependency file current install instructions actively reference.
- `scrapper/requirements.txt` is not yet the only currently authoritative install file by evidence, because current scraper code imports Pillow-related packages that appear only in root `requirements.txt`.
- The two files overlap partially on `beautifulsoup4`, `lxml`, and `pypdf`.
- Root `requirements.txt` does not read as repo-tools-only. It appears partially duplicated, partially stale, and still potentially required in practice until ownership is resolved explicitly.

## Risks
- Current install guidance points to `scrapper/requirements.txt`, but live scraper imports imply that file does not yet describe the full runtime/test dependency set.
- Moving or deleting root `requirements.txt` now would be risky because its Pillow entries still map to current scraper imports.
- Merging the two files now would require an explicit dependency-resolution pass and approval; this audit does not establish enough to do that safely.
- `requests` may be stale, but the audit evidence is not strong enough to remove or relocate it during this milestone.

## Recommendation
Selected recommendation: `keep both for now`

Rationale:
- the scraper file is the only actively documented install target
- the root file still carries packages that map to live scraper imports and are absent from `scrapper/requirements.txt`
- ownership is mixed enough that moving, merging, or modernizing now would be implementation work rather than an audit-only conclusion

Deferred follow-up:
- in a later explicitly approved milestone, resolve Pillow ownership first, then decide whether root `requirements.txt` should stay, move to a repo-tools-specific location, or be merged after explicit approval
- defer any broader dependency modernization beyond that narrow ownership fix
