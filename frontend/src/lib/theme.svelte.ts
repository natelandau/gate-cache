export type Theme = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_KEY = "gate-cache-theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";
const NEXT: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
const NAME: Record<Theme, string> = { system: "System", light: "Light", dark: "Dark" };

export function parseTheme(raw: string | null): Theme {
  return raw === "light" || raw === "dark" || raw === "system" ? raw : "system";
}

export function nextTheme(theme: Theme): Theme {
  return NEXT[theme];
}

export function resolveTheme(theme: Theme, prefersDark: boolean): ResolvedTheme {
  if (theme === "system") return prefersDark ? "dark" : "light";
  return theme;
}

export function themeLabel(theme: Theme): string {
  return `Theme: ${NAME[theme]}. Switch to ${nextTheme(theme)}.`;
}

function readStored(): Theme {
  try {
    return parseTheme(localStorage.getItem(THEME_KEY));
  } catch {
    return "system";
  }
}

function writeStored(theme: Theme): void {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage can be blocked; the choice then lasts for this page load only.
  }
}

let media: MediaQueryList | undefined;

function apply(): void {
  media ??= matchMedia(DARK_QUERY);
  state.resolved = resolveTheme(state.theme, media.matches);
  document.documentElement.dataset.theme = state.resolved;
}

// Only System mode listens, so an explicit choice ignores OS changes.
function syncListener(): void {
  media ??= matchMedia(DARK_QUERY);
  media.removeEventListener("change", apply);
  if (state.theme === "system") media.addEventListener("change", apply);
}

const state = $state<{ theme: Theme; resolved: ResolvedTheme }>({
  theme: "system",
  resolved: "light",
});

/** The user's choice and the theme it resolves to. */
export const theme = {
  get value(): Theme {
    return state.theme;
  },
  get resolved(): ResolvedTheme {
    return state.resolved;
  },
};

/** Read the stored choice and apply it. Call once at startup. */
export function initTheme(): void {
  state.theme = readStored();
  syncListener();
  apply();
}

export function cycleTheme(): void {
  state.theme = nextTheme(state.theme);
  writeStored(state.theme);
  syncListener();
  apply();
}
