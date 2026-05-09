import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const appRoot = join(scriptDir, "..");
const repoRoot = join(appRoot, "..", "..");
export const docsPath = join(appRoot, "docs", "api.md");
export const productFactoryOpenApiPath = join(repoRoot, "packages", "contracts", "openapi.product-factory.json");
const startMarker = "<!-- product-factory-api:generated:start -->";
const endMarker = "<!-- product-factory-api:generated:end -->";

function loadJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function getRefName(ref) {
  return typeof ref === "string" ? ref.split("/").at(-1) : undefined;
}

function requestSchemaName(operation) {
  const content = operation?.requestBody?.content ?? {};
  return getRefName(content["application/json"]?.schema?.$ref);
}

function responseSchemaName(operation) {
  const responses = operation?.responses ?? {};
  const success = responses["200"] ?? responses["201"] ?? responses["202"];
  const content = success?.content ?? {};
  return getRefName(content["application/json"]?.schema?.$ref);
}

function schemaType(schema) {
  if (!schema) {
    return "unknown";
  }

  if (schema.$ref) {
    return getRefName(schema.$ref) ?? "unknown";
  }

  if (schema.anyOf || schema.oneOf) {
    return [...new Set((schema.anyOf ?? schema.oneOf).map(schemaType))].join(" | ");
  }

  if (schema.type === "array") {
    return `${schemaType(schema.items)}[]`;
  }

  if (Array.isArray(schema.type)) {
    return schema.type.join(" | ");
  }

  if (schema.enum) {
    return schema.enum.map((value) => JSON.stringify(value)).join(" | ");
  }

  return schema.type === "integer" ? "number" : schema.type ?? "unknown";
}

function schemaBlock(name, schema) {
  const required = new Set(schema.required ?? []);
  const properties = Object.entries(schema.properties ?? {});
  const lines = [`### ${name}`, "", "```ts", "{"];
  for (const [propertyName, propertySchema] of properties) {
    const optional = required.has(propertyName) ? "" : "?";
    const defaultText = Object.prototype.hasOwnProperty.call(propertySchema, "default")
      ? ` // default: ${JSON.stringify(propertySchema.default)}`
      : "";
    lines.push(`  ${propertyName}${optional}: ${schemaType(propertySchema)};${defaultText}`);
  }
  lines.push("}", "```");
  return lines.join("\n");
}

function generateProductFactorySection(openapi) {
  const paths = openapi.paths ?? {};
  const schemas = openapi.components?.schemas ?? {};
  const methods = ["get", "post", "put", "patch", "delete"];
  const endpointRows = [];
  const requestSchemaNames = new Set();

  for (const [path, pathItem] of Object.entries(paths).sort(([left], [right]) => left.localeCompare(right))) {
    for (const method of methods) {
      const operation = pathItem?.[method];
      if (!operation) {
        continue;
      }

      const requestName = requestSchemaName(operation);
      if (requestName) {
        requestSchemaNames.add(requestName);
      }
      endpointRows.push(
        `| ${method.toUpperCase()} | \`${path}\` | ${requestName ? `\`${requestName}\`` : "-"} | ${responseSchemaName(operation) ? `\`${responseSchemaName(operation)}\`` : "-"} |`,
      );
    }
  }

  const requestBlocks = [...requestSchemaNames]
    .sort((left, right) => (left === "PrepareJobRequest" ? -1 : right === "PrepareJobRequest" ? 1 : left.localeCompare(right)))
    .map((name) => schemaBlock(name, schemas[name]))
    .join("\n\n");

  return [
    startMarker,
    "Generated from `packages/contracts/openapi.product-factory.json`.",
    "",
    "| Method | Browser path | Request body | Success response |",
    "| --- | --- | --- | --- |",
    ...endpointRows,
    "",
    "## Product Factory Request Schemas",
    "",
    requestBlocks,
    endMarker,
  ].join("\n");
}

function replaceGeneratedSection(current, generated) {
  const start = current.indexOf(startMarker);
  const end = current.indexOf(endMarker);
  if (start === -1 || end === -1 || end < start) {
    throw new Error(`Missing Product Factory generated docs markers in ${docsPath}.`);
  }

  return `${current.slice(0, start)}${generated}${current.slice(end + endMarker.length)}`;
}

export function generateApiDocsContent(current = readFileSync(docsPath, "utf8")) {
  return replaceGeneratedSection(current, generateProductFactorySection(loadJson(productFactoryOpenApiPath)));
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  writeFileSync(docsPath, generateApiDocsContent(), "utf8");
}
