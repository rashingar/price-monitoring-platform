import { useThemePreference } from "./useThemePreference";
import { THEME_PREFERENCES, type ThemePreference } from "./themeTypes";

const themeLabels: Record<ThemePreference, string> = {
  system: "System",
  light: "Light",
  dark: "Dark",
};

export function ThemeToggle() {
  const { preference, setPreference } = useThemePreference();

  const moveSelection = (
    currentTarget: HTMLButtonElement,
    currentOption: ThemePreference,
    direction: -1 | 1,
  ) => {
    const currentIndex = THEME_PREFERENCES.indexOf(currentOption);
    const nextIndex =
      (currentIndex + direction + THEME_PREFERENCES.length) % THEME_PREFERENCES.length;
    setPreference(THEME_PREFERENCES[nextIndex]);
    const options = Array.from(
      currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("[role='radio']") ?? [],
    );
    options[nextIndex]?.focus();
  };

  return (
    <div className="theme-toggle" role="radiogroup" aria-label="Theme preference">
      {THEME_PREFERENCES.map((option) => (
        <button
          key={option}
          type="button"
          className={option === preference ? "theme-toggle-option active" : "theme-toggle-option"}
          role="radio"
          aria-checked={option === preference}
          tabIndex={option === preference ? 0 : -1}
          onClick={() => setPreference(option)}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
              event.preventDefault();
              moveSelection(event.currentTarget, option, -1);
            }
            if (event.key === "ArrowRight" || event.key === "ArrowDown") {
              event.preventDefault();
              moveSelection(event.currentTarget, option, 1);
            }
          }}
        >
          {themeLabels[option]}
        </button>
      ))}
    </div>
  );
}
