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

## Default Testing Policy

Codex prompts default to small, targeted checks that are relevant to the files
changed in the current task. Keep the total automated check runtime under 2
minutes. Do not run broad suites by default.

Always run:

- `git diff --check`
- `git status --short`

Also run focused grep/search checks for changed naming, routing, or doc areas.
For example, if a route, package name, script name, or runbook policy changes,
search for the old and new names in the owning docs and app folders.

Root `.\scripts\test\fast.ps1` is Codex-safe aggregate fast verification. Prefer
app-specific scripts for single-app patches because they are faster and
narrower; root fast is appropriate when a prompt touches multiple apps, shared
contracts, or repo-wide test infrastructure.

Do not run these broader commands unless the operator explicitly asks or the
task explicitly requires that exact scope:

- `.\scripts\test\web.ps1`

Use targeted checks instead:

- Run `.\scripts\test\codex-product-factory.ps1` when a prompt touches only
  Product Factory backend files and needs the app default fast profile.
- Run `.\scripts\test\codex-ecommerce.ps1` when a prompt touches only Ecommerce
  API backend files and needs the app default fast profile.
- Run `.\scripts\contracts\check.ps1` only when API contracts, routes, or
  schemas changed.
- Run `.\scripts\contracts\check-web-types.ps1` only when contracts or
  generated web API types changed and `apps\web\node_modules` is available.
- Run a single focused pytest file or test node only when the changed files
  clearly map to it.
- Run a single focused Vitest file only when web changes clearly map to it.

If broader verification would be useful but exceeds the default Codex policy,
do not run it automatically. Report it under `Manual verification needed` with
the exact command for the operator to run. If no broader verification is needed,
write `Manual verification needed: None` in the final report.

Use verbose output for any focused tests and checks so a long-running command
can be distinguished from a hang.

## Examples

Docs-only change:

```powershell
git diff --check
git status --short
```

No app tests are required.

Ecommerce route change:

```powershell
git diff --check
.\.venv\Scripts\python.exe -m pytest apps\ecommerce-api\tests\path\to\relevant_test.py -vv -ra
git status --short
```

Run `.\scripts\contracts\check.ps1` only if OpenAPI changed. If broader
Ecommerce coverage is needed, report this manual command instead of running it:

```powershell
.\scripts\test\ecommerce-api.ps1
```

Web navigation change:

```powershell
git diff --check
Push-Location apps\web
npm run test -- src\test\smoke\relevant-smoke.test.tsx --run
Pop-Location
git status --short
```

Run the relevant smoke or contract test file only. Do not run all web tests
unless explicitly requested.

Contract or generated type change:

```powershell
.\scripts\contracts\check.ps1
.\scripts\contracts\check-web-types.ps1
git diff --check
git status --short
```

Run `check-web-types.ps1` only when `apps\web\node_modules` is available. Do not
run broad app suites by default.

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

## Push Expectations

Commit and push only when the operator asks for it. Before committing, review
`git status --short`, make sure only intended files are staged, and confirm
forbidden files are not included. After committing, push the current branch with
the repository's normal upstream. If the branch has no upstream, set one only
when that matches the operator request.
