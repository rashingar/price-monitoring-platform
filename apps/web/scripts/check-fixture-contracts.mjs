import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const uiRoot = path.resolve(scriptDir, "..");
const parentRoot = path.resolve(uiRoot, "..");

const SNAPSHOTS = {
  commerce: path.join(parentRoot, "ecommerce-api", "docs", "contracts", "openapi.ecommerce.json"),
  productAgent: path.join(
    parentRoot,
    "product-factory-api",
    "docs",
    "contracts",
    "openapi.product-agent.json",
  ),
};

const errors = [];
const warnings = [];

function fail(message) {
  errors.push(message);
}

function warn(message) {
  warnings.push(message);
}

function readJson(filePath) {
  if (!fs.existsSync(filePath)) {
    fail(`Missing OpenAPI snapshot: ${path.relative(parentRoot, filePath)}`);
    return null;
  }

  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function hasOwn(value, key) {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function compileTemplate(template) {
  const source = template
    .split("/")
    .map((segment) => {
      if (segment.length === 0) {
        return "";
      }
      return /^\{[^/{}]+\}$/.test(segment) ? "[^/]+" : escapeRegex(segment);
    })
    .join("/");
  return new RegExp(`^${source}$`);
}

function normalizeFixturePath(backend, fixturePath) {
  const pathOnly = fixturePath.split("?")[0];
  if (backend === "commerce") {
    return pathOnly.replace(/^\/commerce-api(?=\/|$)/, "/api");
  }
  return pathOnly;
}

function operationFor(openapi, method, actualPath) {
  const wantedMethod = method.toLowerCase();
  const paths = openapi.paths ?? {};
  const exact = paths[actualPath]?.[wantedMethod];
  if (exact) {
    return { path: actualPath, operation: exact };
  }

  const matches = Object.entries(paths)
    .filter(([, methods]) => methods?.[wantedMethod])
    .filter(([template]) => compileTemplate(template).test(actualPath))
    .sort((a, b) => b[0].length - a[0].length);

  if (matches.length === 0) {
    return null;
  }

  return { path: matches[0][0], operation: matches[0][1][wantedMethod] };
}

function successResponse(operation) {
  const responses = operation?.responses ?? {};
  if (responses["200"]) {
    return { status: "200", response: responses["200"] };
  }

  const status = Object.keys(responses)
    .filter((key) => /^2\d\d$/.test(key))
    .sort()[0];
  return status ? { status, response: responses[status] } : null;
}

function resolveSchema(openapi, schema) {
  if (!schema?.$ref) {
    return schema;
  }

  const prefix = "#/components/schemas/";
  if (!schema.$ref.startsWith(prefix)) {
    return schema;
  }

  return openapi.components?.schemas?.[schema.$ref.slice(prefix.length)] ?? schema;
}

function responseSchema(openapi, operation) {
  const success = successResponse(operation);
  return success?.response?.content?.["application/json"]?.schema
    ? resolveSchema(openapi, success.response.content["application/json"].schema)
    : null;
}

function requestSchema(openapi, operation) {
  const schema = operation?.requestBody?.content?.["application/json"]?.schema;
  return schema ? resolveSchema(openapi, schema) : null;
}

function routeKey(route) {
  return `${route.method.toUpperCase()} ${route.path}`;
}

function getFixtureResponse(route) {
  if (typeof route.response === "function") {
    return route.response({ searchParams: new URLSearchParams() });
  }
  return route.response;
}

function getFixtureRequestExample(route) {
  return route.requestExample;
}

async function loadTsFixture(filePath, exportName) {
  let ts;
  try {
    ts = await import("typescript");
  } catch {
    fail("Missing npm dependency: typescript. Run npm ci in apps/web.");
    return [];
  }

  const source = fs.readFileSync(filePath, "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
      verbatimModuleSyntax: false,
    },
    fileName: filePath,
  }).outputText;

  const mod = await import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`);
  return Array.isArray(mod[exportName]) ? mod[exportName] : [];
}

function assertFields(label, payload, fields) {
  if (!isRecord(payload)) {
    fail(`${label}: fixture response is not an object.`);
    return;
  }

  fields.forEach((field) => {
    if (!hasOwn(payload, field)) {
      fail(`${label}: fixture response is missing required field "${field}".`);
    }
  });
}

function assertArrayItems(label, payload, arrayPath, fields) {
  if (!isRecord(payload)) {
    fail(`${label}: fixture response is not an object.`);
    return;
  }

  const value = payload[arrayPath];
  if (!Array.isArray(value)) {
    fail(`${label}: fixture response field "${arrayPath}" must be an array.`);
    return;
  }

  value.forEach((item, index) => {
    if (!isRecord(item)) {
      fail(`${label}: ${arrayPath}[${index}] is not an object.`);
      return;
    }

    fields.forEach((field) => {
      if (!hasOwn(item, field)) {
        fail(`${label}: ${arrayPath}[${index}] is missing required field "${field}".`);
      }
    });
  });
}

function assertSchemaProperties(label, schema, fields) {
  if (!isRecord(schema?.properties)) {
    fail(`${label}: backend OpenAPI request schema has no properties.`);
    return;
  }

  fields.forEach((field) => {
    if (!hasOwn(schema.properties, field)) {
      fail(`${label}: backend OpenAPI request schema is missing field "${field}".`);
    }
  });
}

const productAgentCritical = [
  { method: "GET", path: "/api/health", fields: ["status"] },
  {
    method: "GET",
    path: "/api/jobs",
    fields: ["jobs"],
    arrays: [{ path: "jobs", fields: ["job_id", "job_type", "status", "model"] }],
  },
  { method: "GET", path: "/api/jobs/{job_id}", fields: ["job_id", "job_type", "status", "model"] },
  { method: "GET", path: "/api/jobs/{job_id}/logs", fields: ["job_id", "lines"] },
  {
    method: "GET",
    path: "/api/jobs/{job_id}/artifacts",
    fields: ["job_id", "artifacts"],
    arrays: [{ path: "artifacts", fields: ["name", "path"] }],
  },
  { method: "GET", path: "/api/settings", fields: ["schema_version", "authoring"] },
  {
    method: "GET",
    path: "/api/filters/status",
    fields: [
      "filter_map_base_path",
      "filter_map_manual_overrides_path",
      "filter_map_path",
      "revision",
      "sync_report_path",
      "valid_statuses",
    ],
  },
  {
    method: "GET",
    path: "/api/filters/categories",
    fields: ["categories"],
    arrays: [{ path: "categories", fields: ["category_id", "path", "group_count", "source"] }],
  },
  {
    method: "GET",
    path: "/api/filters/categories/{category_id}",
    fields: ["category_id", "path", "revision", "groups"],
    arrays: [{ path: "groups", fields: ["group_id", "name", "required", "status", "source", "values"] }],
  },
  {
    method: "PUT",
    path: "/api/filters/categories/{category_id}/groups",
    fields: ["category_id", "path", "revision", "groups"],
    requestFields: ["expected_revision", "name"],
  },
  {
    method: "PATCH",
    path: "/api/filters/categories/{category_id}/groups/{group_id}",
    fields: ["category_id", "path", "revision", "groups"],
    requestFields: ["expected_revision"],
  },
  {
    method: "PUT",
    path: "/api/filters/categories/{category_id}/groups/{group_id}/values",
    fields: ["category_id", "path", "revision", "groups"],
    requestFields: ["expected_revision", "value"],
  },
  {
    method: "PATCH",
    path: "/api/filters/categories/{category_id}/groups/{group_id}/values/{value_id}",
    fields: ["category_id", "path", "revision", "groups"],
    requestFields: ["expected_revision"],
  },
  {
    method: "POST",
    path: "/api/filters/sync",
    fields: ["status", "revision", "filter_map_path", "sync_report_path"],
  },
  {
    method: "GET",
    path: "/api/filters/sync-report",
    fields: ["mode", "warnings", "overridden_groups", "overridden_values"],
  },
  {
    method: "GET",
    path: "/api/filter-review/{model}",
    fields: ["model", "category_id", "groups", "approved", "render_blocked", "review_artifact_path"],
  },
  {
    method: "GET",
    path: "/api/authoring/{model}",
    fields: ["model", "llm_dir", "intro_text", "seo_meta", "ready_for_render"],
  },
];

const commerceCritical = [
  { method: "GET", path: "/api/health", fields: ["status"] },
  {
    method: "GET",
    path: "/api/catalog/summary",
    fields: [
      "total_products",
      "active_products",
      "atomic_products",
      "bestprice_products",
      "skroutz_products",
      "manufacturer_count",
    ],
  },
  {
    method: "GET",
    path: "/api/catalog/brands",
    fields: ["items"],
    arrays: [{ path: "items", fields: ["manufacturer", "count"] }],
  },
  {
    method: "GET",
    path: "/api/catalog/category-hierarchy",
    fields: ["items"],
    arrays: [{ path: "items", fields: ["family", "count", "categories"] }],
  },
  {
    method: "GET",
    path: "/api/catalog/products",
    fields: ["items", "page", "page_size", "total", "filtered_total"],
    arrays: [
      {
        path: "items",
        fields: [
          "model",
          "mpn",
          "name",
          "manufacturer",
          "price",
          "raw_category",
          "family",
          "category_name",
          "sub_category",
          "ignored",
          "automation_eligible",
        ],
      },
    ],
  },
  {
    method: "GET",
    path: "/api/catalog/products/{catalog_product_id}/source-urls",
    fields: ["items"],
    arrays: [{ path: "items", fields: ["id", "catalog_product_id", "url", "status", "url_type"] }],
  },
  {
    method: "POST",
    path: "/api/catalog/products/{catalog_product_id}/source-urls",
    fields: ["id", "catalog_product_id", "url", "status", "url_type"],
    requestFields: ["url"],
  },
  {
    method: "PATCH",
    path: "/api/catalog/source-urls/{source_url_id}",
    fields: ["id", "catalog_product_id", "url", "status", "url_type"],
    requestFields: ["status"],
  },
  {
    method: "POST",
    path: "/api/catalog/source-urls/{source_url_id}/validate",
    fields: ["item", "validation"],
  },
  {
    method: "GET",
    path: "/api/price-monitoring/db/status",
    fields: [
      "configured",
      "reachable",
      "error",
      "price_monitoring_requires_database",
      "ready_for_price_monitoring",
      "blocking_reasons",
      "non_db_workflows_available",
      "required_for",
    ],
  },
  { method: "GET", path: "/api/price-monitoring/runs", fields: ["items"] },
  { method: "GET", path: "/api/price-monitoring/runs/{run_id}", fields: ["run_id", "source", "created_at", "db"] },
  {
    method: "GET",
    path: "/api/price-monitoring/runs/{run_id}/fetch",
    fields: [
      "run_id",
      "execution_id",
      "status",
      "source",
      "input_csv_path",
      "enriched_csv_path",
      "fetch_result_path",
      "artifacts",
      "stale",
      "queue_position",
    ],
  },
  { method: "GET", path: "/api/price-monitoring/runs/{run_id}/fetch/executions", fields: ["run_id", "items", "count"] },
  { method: "GET", path: "/api/price-monitoring/runs/{run_id}/fetch/logs", fields: ["run_id", "execution_id", "lines"] },
  {
    method: "GET",
    path: "/api/price-monitoring/runs/{run_id}/review",
    fields: ["run_id", "items", "summary"],
    arrays: [{ path: "items", fields: ["model", "selected_action", "warnings"] }],
  },
  { method: "GET", path: "/api/price-monitoring/alerts/rules", fields: ["items", "count", "limit", "offset"] },
  { method: "GET", path: "/api/price-monitoring/alerts/events", fields: ["items", "count", "limit", "offset"] },
  {
    method: "GET",
    path: "/api/artifacts/price-monitoring/runs/{run_id}",
    fields: ["run_id", "items"],
    arrays: [
      {
        path: "items",
        fields: ["name", "path", "download_url", "read_url", "is_allowed", "can_read", "can_download", "warning"],
      },
    ],
  },
];

const commercePendingOpenApiRoutes = new Set([
  "GET /api/catalog/source-urls/summary",
  "GET /api/vendor-sources/source-urls/summary",
  "POST /api/catalog/source-urls/import/preview",
  "POST /api/catalog/source-urls/import/apply",
]);

function compareRoutes({ backend, openapi, routes, critical }) {
  const seen = new Set();

  routes.forEach((route) => {
    const method = String(route.method ?? "").toUpperCase();
    const normalizedPath = normalizeFixturePath(backend, String(route.path ?? ""));
    const match = operationFor(openapi, method, normalizedPath);
    if (!match) {
      if (backend === "commerce" && commercePendingOpenApiRoutes.has(`${method} ${normalizedPath}`)) {
        warn(`${backend}: fixture route ${routeKey(route)} is pending in the backend OpenAPI snapshot.`);
        return;
      }
      fail(`${backend}: fixture route ${routeKey(route)} does not map to any backend OpenAPI route.`);
      return;
    }
    seen.add(`${method} ${match.path}`);
  });

  critical.forEach((check) => {
    const method = check.method.toUpperCase();
    const label = `${backend}: ${method} ${check.path}`;
    const operationMatch = operationFor(openapi, method, check.path);
    if (!operationMatch) {
      fail(`${label}: critical endpoint is missing from backend OpenAPI.`);
      return;
    }

    const success = successResponse(operationMatch.operation);
    if (!success) {
      fail(`${label}: backend OpenAPI has no documented 200 or 2xx success response.`);
    }

    const matchingRoutes = routes.filter((route) => {
      if (String(route.method ?? "").toUpperCase() !== method) {
        return false;
      }
      return compileTemplate(check.path).test(normalizeFixturePath(backend, String(route.path ?? "")));
    });

    if (matchingRoutes.length === 0) {
      fail(`${label}: no UI fixture route covers this critical endpoint.`);
      return;
    }

    const schema = responseSchema(openapi, operationMatch.operation);
    if (schema?.required) {
      matchingRoutes.forEach((route) => {
        assertFields(`${label} (${route.path})`, getFixtureResponse(route), schema.required);
      });
    } else {
      warn(`${label}: no useful OpenAPI JSON response schema; using fixture field checks only.`);
    }

    if (check.requestFields) {
      const schema = requestSchema(openapi, operationMatch.operation);
      assertSchemaProperties(label, schema, check.requestFields);
      matchingRoutes.forEach((route) => {
        const requestExample = getFixtureRequestExample(route);
        if (!requestExample) {
          fail(`${label} (${route.path}): fixture route is missing requestExample.`);
          return;
        }
        assertFields(`${label} (${route.path}) requestExample`, requestExample, check.requestFields);
      });
    }

    if (backend === "commerce" && check.path === "/api/health" && schema?.properties?.service) {
      check.fields = Array.from(new Set([...check.fields, "service"]));
    }

    matchingRoutes.forEach((route) => {
      const payload = getFixtureResponse(route);
      assertFields(`${label} (${route.path})`, payload, check.fields);
      (check.arrays ?? []).forEach((arrayCheck) => {
        assertArrayItems(`${label} (${route.path})`, payload, arrayCheck.path, arrayCheck.fields);
      });
    });
  });

  return seen;
}

function assertCommerceDbRequiredErrorFixtures(routes) {
  routes.forEach((route) => {
    const label = `commerce DB-required fixture ${routeKey(route)}`;
    const response = getFixtureResponse(route);
    if (!isRecord(response)) {
      fail(`${label}: response is not an object.`);
      return;
    }

    if (response.status !== 503) {
      fail(`${label}: response status must be 503.`);
    }

    if (!isRecord(response.body)) {
      fail(`${label}: response body is not an object.`);
      return;
    }

    assertFields(label, response.body, [
      "detail",
      "status",
      "ready_for_price_monitoring",
      "blocking_reasons",
      "non_db_workflows_available",
    ]);

    if (response.body.ready_for_price_monitoring !== false) {
      fail(`${label}: ready_for_price_monitoring must be false.`);
    }

    if (!isRecord(response.body.status)) {
      fail(`${label}: body.status must contain the DB status object.`);
      return;
    }

    assertFields(`${label} body.status`, response.body.status, [
      "configured",
      "reachable",
      "price_monitoring_requires_database",
      "ready_for_price_monitoring",
      "blocking_reasons",
      "non_db_workflows_available",
    ]);
  });
}

function assertCatalogDbImportRequiredErrorFixtures(routes) {
  const expectedCatalogPaths = new Set([
    "/commerce-api/catalog/products",
    "/commerce-api/catalog/summary",
    "/commerce-api/catalog/brands",
    "/commerce-api/catalog/category-hierarchy",
    "/commerce-api/catalog/products/1/source-urls",
    "/commerce-api/catalog/source-urls/summary",
    "/commerce-api/catalog/source-urls/import/preview",
    "/commerce-api/catalog/source-urls/import/apply",
  ]);
  const coveredPaths = new Set();

  routes.forEach((route) => {
    const label = `commerce Catalog DB/import-required fixture ${routeKey(route)}`;
    const pathValue = String(route.path ?? "");
    coveredPaths.add(pathValue);
    const response = getFixtureResponse(route);
    if (!isRecord(response)) {
      fail(`${label}: response is not an object.`);
      return;
    }

    if (response.status !== 503) {
      fail(`${label}: response status must be 503.`);
    }

    if (!isRecord(response.body)) {
      fail(`${label}: response body is not an object.`);
      return;
    }

    assertFields(label, response.body, [
      "detail",
      "required_for",
      "ready_for_catalog",
      "blocking_reasons",
      "non_catalog_workflows_available",
      "setup_hints",
    ]);

    if (response.body.ready_for_catalog !== false) {
      fail(`${label}: ready_for_catalog must be false.`);
    }

    if (!Array.isArray(response.body.required_for) || !response.body.required_for.includes("catalog")) {
      fail(`${label}: required_for must include catalog.`);
    }
  });

  expectedCatalogPaths.forEach((pathValue) => {
    if (!coveredPaths.has(pathValue)) {
      fail(`commerce Catalog DB/import-required fixtures missing ${pathValue}.`);
    }
  });
}

const commerceOpenapi = readJson(SNAPSHOTS.commerce);
const productAgentOpenapi = readJson(SNAPSHOTS.productAgent);

if (commerceOpenapi && productAgentOpenapi) {
  const productAgentRoutes = await loadTsFixture(
    path.join(uiRoot, "src", "test", "fixtures", "productAgentApi.ts"),
    "productAgentFixtureRoutes",
  );
  const commerceRoutes = await loadTsFixture(
    path.join(uiRoot, "src", "test", "fixtures", "commerceApi.ts"),
    "commerceFixtureRoutes",
  );
  const commerceDbRequiredRoutes = await loadTsFixture(
    path.join(uiRoot, "src", "test", "fixtures", "commerceApi.ts"),
    "commerceDbRequiredFixtureRoutes",
  );
  const catalogDbImportRequiredRoutes = await loadTsFixture(
    path.join(uiRoot, "src", "test", "fixtures", "commerceApi.ts"),
    "catalogDbImportRequiredFixtureRoutes",
  );

  compareRoutes({
    backend: "productAgent",
    openapi: productAgentOpenapi,
    routes: productAgentRoutes,
    critical: productAgentCritical,
  });
  compareRoutes({
    backend: "commerce",
    openapi: commerceOpenapi,
    routes: commerceRoutes,
    critical: commerceCritical,
  });
  compareRoutes({
    backend: "commerce",
    openapi: commerceOpenapi,
    routes: commerceDbRequiredRoutes,
    critical: [],
  });
  compareRoutes({
    backend: "commerce",
    openapi: commerceOpenapi,
    routes: catalogDbImportRequiredRoutes,
    critical: [],
  });
  assertCommerceDbRequiredErrorFixtures(commerceDbRequiredRoutes);
  assertCatalogDbImportRequiredErrorFixtures(catalogDbImportRequiredRoutes);
}

warnings.forEach((message) => console.warn(`WARN: ${message}`));

if (errors.length > 0) {
  console.error("Fixture contract comparison failed:");
  errors.forEach((message) => console.error(`  - ${message}`));
  process.exit(1);
}

console.log("Fixture contract comparison passed.");
console.log(`Checked ${productAgentCritical.length} Product Factory critical routes.`);
console.log(`Checked ${commerceCritical.length} commerce critical routes.`);
