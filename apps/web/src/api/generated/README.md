# Generated API Types

Files in this directory are generated from mirrored OpenAPI contracts in
`packages/contracts`.

Refresh them from the repository root with:

```powershell
.\scripts\contracts\generate-web-types.ps1
```

Check that committed generated types are current with:

```powershell
.\scripts\contracts\check-web-types.ps1
```

Do not edit generated `.ts` files by hand. The existing manual clients in
`apps/web/src/api/client.ts` and `apps/web/src/api/commerceClient.ts` remain the
runtime clients for now.
