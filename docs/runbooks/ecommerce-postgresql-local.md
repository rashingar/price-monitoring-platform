# Ecommerce PostgreSQL Local Setup

This runbook is for a Windows developer or operator setting up the local
PostgreSQL database used by Ecommerce API.

Run these commands from PowerShell with native PostgreSQL tools on `PATH`.
Database backups and dump files must not be committed.

## Connection Setting

Ecommerce API reads:

```powershell
$env:ECOMMERCE_DATABASE_URL = "postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce"
```

Older Ecommerce API environment variable names from before this rename are no
longer supported. The old local database/user defaults are no longer used.

## Path A: Back Up Existing Local Data First

Use this path if existing local Ecommerce API data matters.

Create a compressed custom-format backup:

```powershell
pg_dump -U postgres -h 127.0.0.1 -p 5432 -Fc -f ecommerce-before-rename.backup <previous_database_name>
```

Plain SQL/text dump alternative:

```powershell
pg_dump -U postgres -h 127.0.0.1 -p 5432 -f ecommerce-before-rename.sql <previous_database_name>
```

Store backups outside ignored/generated folders if you need to keep them.
Never commit `.backup`, `.dump`, `.sql`, or other database dump files that
contain local data.

## Path B: Rename An Existing Local Database/User

Use this path when you have existing local Ecommerce API data worth keeping.

Warnings:

- Stop the Ecommerce API before renaming.
- Close active database sessions.
- Back up first if the data matters.
- Run from a `postgres` admin PowerShell or `psql` session.
- Renaming can fail if active connections exist.
- Terminate local sessions carefully; this interrupts active database users.

Open an admin `psql` session:

```powershell
psql -U postgres -h 127.0.0.1 -p 5432 -d postgres
```

Optional local-session cleanup before renaming:

```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '<previous_database_name>'
  AND pid <> pg_backend_pid();
```

Rename the previous local database and role to the current defaults:

```sql
ALTER DATABASE <previous_database_name> RENAME TO ecommerce;
ALTER ROLE <previous_role_name> RENAME TO ecommerce;
ALTER ROLE ecommerce WITH PASSWORD 'ecommerce';
```

Then set the current PowerShell variable:

```powershell
$env:ECOMMERCE_DATABASE_URL = "postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce"
```

## Path C: Fresh Local Setup

Use this path when there is no existing local data to preserve.

Open an admin `psql` session:

```powershell
psql -U postgres -h 127.0.0.1 -p 5432 -d postgres
```

Create the current local role and database:

```sql
CREATE USER ecommerce WITH PASSWORD 'ecommerce';
CREATE DATABASE ecommerce OWNER ecommerce;
GRANT ALL PRIVILEGES ON DATABASE ecommerce TO ecommerce;
```

Set the current PowerShell variable:

```powershell
$env:ECOMMERCE_DATABASE_URL = "postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce"
```

Apply migrations from the app folder:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.check_db_setup
Pop-Location
```
