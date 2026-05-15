import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "../../components/layout/AppShell";
import {
  getInitialThemePreference,
  initializeTheme,
  persistThemePreference,
} from "../../features/theme/themeStorage";
import { THEME_STORAGE_KEY, type ThemePreference } from "../../features/theme/themeTypes";
import { useThemePreference } from "../../features/theme/useThemePreference";

function installMatchMedia(initialMatches: boolean) {
  let matches = initialMatches;
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  const mediaQuery = {
    media: "(prefers-color-scheme: dark)",
    get matches() {
      return matches;
    },
    onchange: null,
    addEventListener: vi.fn((eventName: string, listener: (event: MediaQueryListEvent) => void) => {
      if (eventName === "change") {
        listeners.add(listener);
      }
    }),
    removeEventListener: vi.fn((eventName: string, listener: (event: MediaQueryListEvent) => void) => {
      if (eventName === "change") {
        listeners.delete(listener);
      }
    }),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  } as MediaQueryList;

  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn(() => mediaQuery),
  });

  return {
    mediaQuery,
    setMatches(nextMatches: boolean) {
      matches = nextMatches;
      listeners.forEach((listener) =>
        listener({ matches: nextMatches, media: mediaQuery.media } as MediaQueryListEvent),
      );
    },
  };
}

function renderShell() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<div>Dashboard content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("theme preference", () => {
  beforeEach(() => {
    installMatchMedia(false);
  });

  it("defaults to system when localStorage is empty without writing the default", () => {
    initializeTheme();

    expect(getInitialThemePreference()).toBe("system");
    expect(document.documentElement.dataset.themePreference).toBe("system");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it("falls back to system for invalid localStorage values", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "auto");

    initializeTheme();

    expect(getInitialThemePreference()).toBe("system");
    expect(document.documentElement.dataset.themePreference).toBe("system");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("auto");
  });

  it.each<ThemePreference>(["light", "dark", "system"])(
    "persists %s after explicit selection",
    (preference) => {
      persistThemePreference(preference);

      expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe(preference);
    },
  );

  it("updates document attributes when Light and Dark are selected", async () => {
    const { result } = renderHook(() => useThemePreference());

    act(() => result.current.setPreference("dark"));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    expect(document.documentElement.dataset.themePreference).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    act(() => result.current.setPreference("light"));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
    expect(document.documentElement.dataset.themePreference).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("responds to matchMedia changes while using System", async () => {
    const matchMedia = installMatchMedia(false);
    const { result } = renderHook(() => useThemePreference());

    expect(result.current.preference).toBe("system");
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));

    act(() => matchMedia.setMatches(true));

    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    expect(document.documentElement.dataset.themePreference).toBe("system");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });
});

describe("theme toggle", () => {
  beforeEach(() => {
    installMatchMedia(true);
  });

  it("renders System, Light, and Dark in the AppShell topbar", () => {
    renderShell();

    const toggle = screen.getByRole("radiogroup", { name: "Theme preference" });
    expect(within(toggle).getByRole("radio", { name: "System" })).toBeInTheDocument();
    expect(within(toggle).getByRole("radio", { name: "Light" })).toBeInTheDocument();
    expect(within(toggle).getByRole("radio", { name: "Dark" })).toBeInTheDocument();
  });

  it("applies selected Light, Dark, and System modes from the segmented control", async () => {
    renderShell();

    const toggle = screen.getByRole("radiogroup", { name: "Theme preference" });
    fireEvent.click(within(toggle).getByRole("radio", { name: "Dark" }));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    expect(document.documentElement.dataset.themePreference).toBe("dark");

    fireEvent.click(within(toggle).getByRole("radio", { name: "Light" }));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
    expect(document.documentElement.dataset.themePreference).toBe("light");

    fireEvent.click(within(toggle).getByRole("radio", { name: "System" }));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    expect(document.documentElement.dataset.themePreference).toBe("system");
  });
});
