import { vi } from "vitest";

export interface MockRequest {
  method: string;
  path: string;
  pathname: string;
  searchParams: URLSearchParams;
  body: unknown;
}

export interface MockJsonResponse {
  status?: number;
  body?: unknown;
  headers?: Record<string, string>;
}

export interface MockRoute {
  method?: string;
  path: string | RegExp | ((request: MockRequest) => boolean);
  requestExample?: unknown;
  response:
    | unknown
    | MockJsonResponse
    | ((request: MockRequest) => unknown | MockJsonResponse | Promise<unknown | MockJsonResponse>);
}

export interface InstalledMockFetch {
  requests: MockRequest[];
  restore: () => void;
}

function hasResponseShape(value: unknown): value is MockJsonResponse {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const record = value as Record<string, unknown>;
  return (
    typeof record.status === "number" ||
    "body" in record ||
    "headers" in record
  );
}

type FetchOptions = RequestInit | Request;

function normalizeMethod(init?: FetchOptions): string {
  return (init?.method ?? "GET").toUpperCase();
}

async function readBody(init?: FetchOptions): Promise<unknown> {
  if (init?.body === undefined || init.body === null) {
    return null;
  }

  if (typeof init.body !== "string") {
    return init.body;
  }

  try {
    return JSON.parse(init.body);
  } catch {
    return init.body;
  }
}

function normalizeUrl(input: RequestInfo | URL): URL {
  if (input instanceof Request) {
    return new URL(input.url, "http://localhost");
  }

  return new URL(String(input), "http://localhost");
}

function routeMatches(route: MockRoute, request: MockRequest): boolean {
  const expectedMethod = (route.method ?? "GET").toUpperCase();
  if (expectedMethod !== request.method) {
    return false;
  }

  if (typeof route.path === "function") {
    return route.path(request);
  }

  if (route.path instanceof RegExp) {
    return route.path.test(request.path);
  }

  const comparablePath = route.path.includes("?") ? request.path : request.pathname;
  return comparablePath === route.path;
}

function toResponse(value: unknown): Response {
  const shaped = hasResponseShape(value) ? value : { body: value };
  const status = shaped.status ?? 200;
  const headers = new Headers(shaped.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const body = shaped.body === undefined ? null : JSON.stringify(shaped.body);
  return new Response(body, {
    status,
    headers,
    statusText: status >= 400 ? "Mock Error" : "OK",
  });
}

export function jsonResponse(body: unknown, status = 200): MockJsonResponse {
  return { status, body };
}

export function installMockFetch(routes: MockRoute[]): InstalledMockFetch {
  const previousFetch = globalThis.fetch;
  const requests: MockRequest[] = [];

  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = normalizeUrl(input);
    const requestInit = input instanceof Request ? input : undefined;
    const method = normalizeMethod(init ?? requestInit);
    const request: MockRequest = {
      method,
      path: `${url.pathname}${url.search}`,
      pathname: url.pathname,
      searchParams: url.searchParams,
      body: await readBody(init ?? requestInit),
    };
    requests.push(request);

    const route = routes.find((candidate) => routeMatches(candidate, request));
    if (!route) {
      const expected = routes
        .map((candidate) => `${(candidate.method ?? "GET").toUpperCase()} ${String(candidate.path)}`)
        .join("\n");
      throw new Error(
        `Unexpected fetch request: ${request.method} ${request.path}\nKnown mocked routes:\n${expected}`,
      );
    }

    const value =
      typeof route.response === "function"
        ? await route.response(request)
        : route.response;
    return toResponse(value);
  });

  return {
    requests,
    restore: () => {
      globalThis.fetch = previousFetch;
    },
  };
}
