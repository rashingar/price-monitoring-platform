import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";


const commerceTypesSource = readFileSync(
  resolve(process.cwd(), "src/api/commerceTypes.ts"),
  "utf8",
);

describe("generated API contract drift guardrails", () => {
  it("keeps Commerce request types generated-schema-derived instead of handwritten", () => {
    const handwrittenRequestInterfaces = Array.from(
      commerceTypesSource.matchAll(/export\s+interface\s+([A-Za-z0-9_]*Request)\s*\{/g),
      (match) => match[1],
    );
    const handwrittenRequestObjectTypes = Array.from(
      commerceTypesSource.matchAll(/export\s+type\s+([A-Za-z0-9_]*Request)\s*=\s*\{/g),
      (match) => match[1],
    );

    expect([...handwrittenRequestInterfaces, ...handwrittenRequestObjectTypes]).toEqual([]);
  });

  it("keeps high-risk Commerce request aliases pointed at generated schemas", () => {
    const generatedRequestAliases = [
      ["SourceUrlImportRequest", "SourceUrlImportRequest"],
      ["ProductFactoryHandoffImportRequest", "ProductFactoryHandoffImportRequest"],
      ["SourceUrlAgentRunRequest", "SourceUrlAgentRunRequest"],
      ["VendorSourceCaptureRunRequest", "VendorSourceCaptureRunApiRequest"],
      ["SkroutzNetworkDiagnosticRequest", "SkroutzNetworkDiagnosticApiRequest"],
      ["StockSyncRunRequest", "StockSyncRunRequest"],
    ];

    for (const [aliasName, schemaName] of generatedRequestAliases) {
      const directSchemaAlias = new RegExp(
        `export\\s+type\\s+${aliasName}\\s*=\\s*EcommerceSchema<"${schemaName}">\\s*;`,
        "m",
      );
      const contractAlias = new RegExp(
        `export\\s+type\\s+${aliasName}\\s*=\\s*EcommerceContract${aliasName}\\s*;`,
        "m",
      );

      expect(
        directSchemaAlias.test(commerceTypesSource) || contractAlias.test(commerceTypesSource),
        `${aliasName} should remain generated-schema-derived`,
      ).toBe(true);
    }
  });
});
