import { existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const scriptDir = dirname(fileURLToPath(import.meta.url));
export const appRoot = join(scriptDir, "..");

export const generatedSpecs = [
  {
    name: "Product Factory",
    source: "../../packages/contracts/openapi.product-factory.json",
    output: "src/api/generated/productFactory.ts",
    checkOutput: "node_modules/.tmp/api-types-check/productFactory.ts",
  },
  {
    name: "Ecommerce",
    source: "../../packages/contracts/openapi.ecommerce.json",
    output: "src/api/generated/ecommerce.ts",
    checkOutput: "node_modules/.tmp/api-types-check/ecommerce.ts",
  },
];

export function ensureGeneratorAvailable() {
  const cliPath = join(appRoot, "node_modules", "openapi-typescript", "bin", "cli.js");
  if (!existsSync(cliPath)) {
    throw new Error(
      [
        "Missing openapi-typescript dependency in apps/web/node_modules.",
        "Run from the repository root:",
        "Push-Location apps\\web",
        "npm ci",
        "Pop-Location",
      ].join("\n"),
    );
  }

  return cliPath;
}

export function cleanCheckOutput() {
  rmSync(join(appRoot, "node_modules", ".tmp", "api-types-check"), {
    force: true,
    recursive: true,
  });
}

export function generateApiTypes(specs, outputKey) {
  const cliPath = ensureGeneratorAvailable();

  for (const spec of specs) {
    const sourcePath = join(appRoot, spec.source);
    if (!existsSync(sourcePath)) {
      throw new Error(`Missing ${spec.name} OpenAPI contract: ${spec.source}`);
    }

    const outputPath = spec[outputKey];
    mkdirSync(join(appRoot, dirname(outputPath)), { recursive: true });

    const result = spawnSync(
      process.execPath,
      [cliPath, spec.source, "--output", outputPath, "--alphabetize"],
      {
        cwd: appRoot,
        stdio: "inherit",
        shell: false,
      },
    );

    if (result.error) {
      throw result.error;
    }

    if (result.status !== 0) {
      throw new Error(`${spec.name} API type generation failed with exit code ${result.status}.`);
    }
  }
}
