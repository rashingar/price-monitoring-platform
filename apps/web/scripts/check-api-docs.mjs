import { readFileSync } from "node:fs";
import { docsPath, generateApiDocsContent } from "./generate-api-docs.mjs";

const before = readFileSync(docsPath, "utf8");
const expected = generateApiDocsContent(before);
const after = readFileSync(docsPath, "utf8");
if (expected !== after) {
  process.stderr.write(
    [
      "Generated Product Factory API docs are stale.",
      "Run from the repository root:",
      "Push-Location apps\\web",
      "npm run generate:api-docs",
      "Pop-Location",
      "",
    ].join("\n"),
  );
  process.exit(1);
}

process.stdout.write("Generated Product Factory API docs are up to date.\n");
