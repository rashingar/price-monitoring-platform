import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import {
  applyTheme,
  getInitialThemePreference,
  getSystemTheme,
  persistThemePreference,
  resolveThemePreference,
} from "./themeStorage";
import type { ResolvedTheme, ThemePreference } from "./themeTypes";

export function useThemePreference() {
  const [preference, setPreferenceState] = useState<ThemePreference>(() =>
    getInitialThemePreference(),
  );
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(() => getSystemTheme());
  const theme = preference === "system" ? systemTheme : resolveThemePreference(preference);

  useLayoutEffect(() => {
    applyTheme(preference, theme);
  }, [preference, theme]);

  useEffect(() => {
    if (preference !== "system") {
      return undefined;
    }

    const mediaQuery = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mediaQuery) {
      return undefined;
    }

    const updateSystemTheme = (event?: MediaQueryListEvent) => {
      setSystemTheme((event?.matches ?? mediaQuery.matches) ? "dark" : "light");
    };

    updateSystemTheme();
    mediaQuery.addEventListener("change", updateSystemTheme);
    return () => mediaQuery.removeEventListener("change", updateSystemTheme);
  }, [preference]);

  const setPreference = useCallback((nextPreference: ThemePreference) => {
    persistThemePreference(nextPreference);
    if (nextPreference === "system") {
      setSystemTheme(getSystemTheme());
    }
    setPreferenceState(nextPreference);
  }, []);

  return { preference, setPreference, theme };
}
