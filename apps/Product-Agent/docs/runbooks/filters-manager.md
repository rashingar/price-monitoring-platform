# Filters Manager Recovery

Filters Manager manual edits are stored in `resources/mappings/filter_map.manual_overrides.json`. The effective runtime map is regenerated into `resources/mappings/filter_map.json` from `filter_map.base.json` plus the manual overrides.

## Backups

Backups live in:

```text
resources/mappings/backups/filter_overrides/
```

A backup is created before each successful manual override write attempt. Backup files are named so they sort by creation time:

```text
filter_map.manual_overrides.YYYYMMDD-HHMMSS.<revision>.json
```

The service retains the latest 20 backups and removes older backup files after a new backup is created. Backup content is the previous manual override JSON file only; it does not include machine-specific absolute paths.

If no previous manual override file exists, the service writes a small `.marker.json` file in the backup directory with relative metadata instead of creating a restorable backup.

## Atomic Writes

Manual overrides, the generated effective filter map, and the sync report are written through a temporary file in the same directory, flushed, and moved into place with `os.replace`. A failed write should not leave a partially written JSON target.

## Corrupt JSON

If `filter_map.manual_overrides.json` is invalid JSON, Filters Manager returns a controlled error:

```text
Manual filter override JSON is invalid. Restore from backup or fix the file.
```

The service does not silently overwrite a corrupt manual override file and does not regenerate `filter_map.json` from corrupt overrides.

## Restore Latest Backup

Use the API restore endpoint with an empty request body to restore the latest valid backup:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/filters/backups/restore -ContentType "application/json" -Body "{}"
```

The restore path validates the backup JSON, backs up the current manual override file if it exists, restores atomically, regenerates the effective filter map, and updates `filter_map.sync_report.json` with rollback metadata.

## Restore Named Backup

List available backups:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/api/filters/backups
```

Restore a specific file by name:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/filters/backups/restore -ContentType "application/json" -Body '{"backup_name":"filter_map.manual_overrides.20260502-120000.sha256-abc123.json"}'
```

Backup names are validated as plain filenames inside the backup directory. Path traversal is rejected.

## Manual Edits

Do not manually edit `filter_map.manual_overrides.json` while the API is running unless recovery requires it. If manual repair is necessary, stop the API, keep a copy of the corrupt file, fix JSON syntax with UTF-8 encoding, then restart and run `/api/filters/sync`.
