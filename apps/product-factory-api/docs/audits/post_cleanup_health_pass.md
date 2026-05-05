# Post-Cleanup Health Pass

Historical note:
- This report records the M9 repo-health snapshot from before the later M10, M11, and M12 normalization milestones.
- References below to `scrapper/requirements.txt` and other superseded paths describe the repo state at that time and are preserved as historical evidence.

## Current Repo-Health Summary
- Milestones M1 through M8 were completed without changing the known pytest baseline.
- Active repo guidance now reflects the post-M6 layout: shared support assets live under `resources/`, active docs live under `docs/`, legacy references live under `archive/`, and runtime artifacts remain under `work/`.
- The approved documentation and archive moves from M4 and M5 are reflected in active guidance.
- The main remaining issues are deferred cleanup items rather than contradictions in the current runtime layout.

## Confirmed Remaining Issues
- Dependency ownership is still mixed:
  - `scrapper/requirements.txt` is the only currently documented install target
  - root `requirements.txt` still appears relevant because Pillow-related imports map only to that file
- Redundant placeholder files remain in non-empty documentation directories:
  - `docs/audits/.gitkeep`
  - `docs/checkpoints/.gitkeep`
  - `docs/runbooks/.gitkeep`
  - `docs/specs/.gitkeep`
- Some runtime path assumptions were intentionally deferred and still exist:
  - `scrapper/electronet_single_import/workflow.py` still anchors `work/` and `products/` via `REPO_ROOT`
  - several tests still use hardcoded absolute repo paths
- Historical references to pre-M4/M5/M6 paths remain in prior audit/spec/log files and archived legacy files. Current evidence shows these are historical records rather than active guidance, but they can still confuse future cleanup work if read without context.

## Safe Follow-Up Items
- Run a narrow follow-up milestone to resolve dependency ownership, starting with the Pillow and `pillow-avif-plugin` gap between root `requirements.txt` and `scrapper/requirements.txt`.
- Remove the four redundant `.gitkeep` files from non-empty `docs/` subdirectories after explicit approval.
- Normalize the hardcoded absolute repo paths in scraper tests to repo-relative discovery after explicit approval.
- Add small historical-context notes where useful if future contributors keep confusing audit/spec snapshots with current layout guidance.

## Risky Postponed Items
- Merging, renaming, or relocating dependency files remains risky until ownership is resolved explicitly.
- Refactoring `workflow.py` output-root assumptions is still outside the cleanup scope and should not be bundled with documentation or dependency follow-up.
- Rewriting historical audits, specs, or archive files wholesale would risk erasing useful prior-state evidence.

## Final Recommended Next Action
- Open one explicitly scoped follow-up milestone for dependency ownership resolution only, starting with the live Pillow-related mismatch between root `requirements.txt` and `scrapper/requirements.txt`.
