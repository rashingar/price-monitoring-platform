# Codex Workflow

Use this runbook for routine Codex changes in the monorepo.

## Before Editing

1. Inspect `git status --short`.
2. Keep the change scoped to the user request.
3. Avoid runtime behavior changes for docs-only tasks.
4. Do not modify unrelated user changes.

## During The Change

- Prefer existing app patterns and root scripts.
- Keep Product Factory, Ecommerce API, and web boundaries explicit.
- Do not rename routes, packages, app folders, or public contracts unless the
  task explicitly asks for that scope.
- Do not edit generated web API types by hand.
- After API changes, regenerate the owning OpenAPI snapshot, refresh
  `packages/contracts` when the app-local snapshot changes, then run:

  ```powershell
  .\scripts\contracts\generate-web-types.ps1
  .\scripts\contracts\check.ps1
  .\scripts\contracts\check-web-types.ps1
  ```

## Required Checks

Run hygiene before committing:

```powershell
.\scripts\check\hygiene.ps1
```

Run fast tests when dependencies are installed:

```powershell
.\scripts\test\fast.ps1
```

Use verbose output for tests and checks so a long-running command can be
distinguished from a hang.

If `apps/web/node_modules` is present, also run:

```powershell
.\scripts\contracts\check-web-types.ps1
```

Always run:

```powershell
.\scripts\contracts\check.ps1
git diff --check
git status --short
```

## Commit Safety

Do not commit:

- `.env`, `.secrets`, credentials, tokens, or private keys.
- `.venv`, `node_modules`, `__pycache__`, `.pytest_cache`.
- `work`, `output`, `runs`, `logs`, `products`.
- DB files, dumps, backups, SQLite files, or local database exports.
- Raw provider HTML captures.
- Unrequested generated artifacts.

Use `.\scripts\check\hygiene.ps1 -Staged` before committing when the change
touches many files.

## Commit Messages

Use conventional short prefixes:

- `docs: ...` for documentation-only work.
- `test: ...` for test-only changes.
- `fix: ...` for bug fixes.
- `refactor: ...` for behavior-preserving code structure changes.
- `chore: ...` for tooling or maintenance.

Keep the subject imperative and specific.
