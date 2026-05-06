import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import {
  appRoot,
  cleanCheckOutput,
  generateApiTypes,
  generatedSpecs,
} from "./api-type-generation.mjs";

try {
  cleanCheckOutput();
  generateApiTypes(generatedSpecs, "checkOutput");

  const stale = generatedSpecs.filter((spec) => {
    const expectedPath = join(appRoot, spec.output);
    const actualPath = join(appRoot, spec.checkOutput);

    if (!existsSync(expectedPath)) {
      return true;
    }

    return readFileSync(expectedPath, "utf8") !== readFileSync(actualPath, "utf8");
  });

  cleanCheckOutput();

  if (stale.length > 0) {
    console.error(
      [
        "Generated API types are stale.",
        "Run from the repository root:",
        ".\\scripts\\contracts\\generate-web-types.ps1",
        "",
        "Stale files:",
        ...stale.map((spec) => `- ${spec.output}`),
      ].join("\n"),
    );
    process.exit(1);
  }

  console.log("Generated API types are up to date.");
} catch (error) {
  cleanCheckOutput();
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
}
