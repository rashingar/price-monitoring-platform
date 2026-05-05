# Monorepo Migration Runbook

This runbook sequences the migration from legacy app folders into the target
Price Monitoring Platform monorepo layout.

## Phase 0: Architecture Docs

- Add target architecture documentation.
- Add architecture decision records.
- Add this migration runbook.
- Add or update the root README.
- Do not move folders.
- Do not rename files from copied apps.
- Do not refactor code.
- Do not create app code.

## Phase 1: Mechanical Folder Migration

Status: completed in the current layout.

Target moves:

- `Product-Agent` -> `apps/product-factory-api`
- `ecommerce-api` -> `apps/ecommerce-api`
- `product-agent-ui` -> `apps/web`
- `apps/product-factory-api/scraper` -> `apps/product-factory-api/src`

Rules:

- Ecommerce API uses the internal `src/ecommerce` package.
- Do not rename the `pipeline` package yet.
- Do not change API routes during the mechanical migration.
- Do not change browser `/api` and `/commerce-api` routes during the first
  migration.
- Keep runtime behavior stable.
- Keep folder moves mechanical and reviewable.

## Phase 2: Root Scripts and README

Status: completed in the current layout.

- Add root scripts that delegate to app-local commands.
- Keep backend runtimes separate.
- Add root development and test command documentation.
- Document app-local environment setup.
- Avoid hiding app boundaries behind root scripts.

## Phase 3: Contract Snapshot Mirroring

Status: completed in the current layout when both mirrored snapshots exist in
`packages/contracts`.

- Create `packages/contracts` if it is not already present.
- Mirror Product Factory OpenAPI snapshots.
- Mirror Ecommerce OpenAPI snapshots.
- Add contract fixture locations and update docs.
- Do not introduce generated clients in this phase unless a separate decision
  approves it.

## Phase 4: Path/Doc Cleanup

Status: completed for active setup docs, root scripts, and path references in
the current layout.

- Update documentation references from legacy paths to target paths.
- Fix scripts that still point at old folder names.
- Keep compatibility aliases only where needed and document their removal path.
- Keep app boundaries explicit when updating internal Python packages.

## Phase 5: Stabilization

- Use a single root virtual environment at `.venv/` for Python root scripts.
  On Windows, root scripts call `.venv\Scripts\python.exe`.
- Create the root virtual environment from the repository root with:

  ```powershell
  python --version
  python -m venv .venv
  .\.venv\Scripts\python.exe --version
  ```

  Python 3.11 or newer is required. The `python` command must resolve to Python
  3.11+; if it is missing or too old, install a supported Python version and
  reopen PowerShell.

- Install dependencies into the root `.venv` manually from the app-specific
  dependency files needed for the current task. Product Factory dependencies
  still install from `apps/product-factory-api/requirements.txt` and can then be
  installed editable with `pip install -e apps/product-factory-api --no-deps`.
  Do not merge Python dependency files or introduce a new monorepo lockfile
  during stabilization.
- Product Factory now has minimal setuptools package metadata as Python project
  `product-factory`; the internal package remains `pipeline` under
  `apps/product-factory-api/src`.
- Ecommerce API uses the internal package `ecommerce` under
  `apps/ecommerce-api/src`.
- Root scripts should fail clearly when the root `.venv` is missing and should
  not silently install dependencies.
- Web scripts should fail clearly when `apps/web/node_modules` is missing and
  should direct the developer to run `npm ci`.
- Keep generated `products/`, `work/`, `output/`, `runs/`, and `logs/` outputs
  ignored. Raw scraped marketplace, vendor, or provider HTML captures must stay
  out of Git; sanitized examples belong under `docs/examples` or
  `tests/fixtures`.
- Run app-local tests with verbose output.
- Run root checks with verbose output once root scripts exist.
- Verify backend API startup independently.
- Verify web development startup against both backend API routes.
- Verify contract snapshots and fixtures.
- Record known gaps before refactors start.
- Use [Ecommerce PostgreSQL Local Setup](ecommerce-postgresql-local.md) for
  local database backup, rename, and fresh setup steps.

## Phase 6: Intentional Refactors

- Ecommerce API package rename is complete; do not add compatibility aliases
  for older package names.
- Decide whether `product-factory-api` needs durable DB-backed job state.
- Decide whether Product Factory DB state belongs in a separate schema or
  separate database.
- Introduce generated API clients only after contract mirroring is stable.
- Introduce durable workers/jobs only after ownership and operational model are
  documented.
- Consider gateway or browser route redesign only as an intentional follow-up.
