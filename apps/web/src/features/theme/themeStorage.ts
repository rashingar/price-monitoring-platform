import {
  THEME_PREFERENCES,
  THEME_STORAGE_KEY,
  type ResolvedTheme,
  type ThemePreference,
} from "./themeTypes";

function isThemePreference(value: string | null): value is ThemePreference {
  return value !== null && THEME_PREFERENCES.includes(value as ThemePreference);
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function getStoredThemePreference(): ThemePreference | null {
  const localStorage = storage();
  if (!localStorage) {
    return null;
  }
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(value) ? value : null;
  } catch {
    return null;
  }
}

export function getInitialThemePreference(): ThemePreference {
  return getStoredThemePreference() ?? "system";
}

export function persistThemePreference(preference: ThemePreference): void {
  try {
    storage()?.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Keep the active in-memory theme even when browser storage is unavailable.
  }
}

export function getSystemTheme(): ResolvedTheme {
  return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
}

export function resolveThemePreference(preference: ThemePreference): ResolvedTheme {
  return preference === "system" ? getSystemTheme() : preference;
}

export function applyTheme(preference: ThemePreference, theme: ResolvedTheme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.themePreference = preference;
}

export function initializeTheme(): void {
  const preference = getInitialThemePreference();
  applyTheme(preference, resolveThemePreference(preference));
}
