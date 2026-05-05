import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

function installNetworkGuard() {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = input instanceof Request ? input.url : String(input);
    throw new Error(`Unexpected live network request in test: ${url}`);
  });
}

beforeEach(() => {
  installNetworkGuard();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  installNetworkGuard();
});
