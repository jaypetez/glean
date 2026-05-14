export type ThemeChoice = "system" | "dark" | "light";
export type DensityChoice = "comfortable" | "compact";

const THEME_KEY = "glean.theme";
const DENSITY_KEY = "glean.density";

let mediaListenerAttached = false;

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  return window.localStorage;
}

function rootElement(): HTMLElement | null {
  if (typeof document === "undefined") return null;
  return document.documentElement;
}

function isThemeChoice(value: string | null): value is ThemeChoice {
  return value === "system" || value === "dark" || value === "light";
}

function isDensityChoice(value: string | null): value is DensityChoice {
  return value === "comfortable" || value === "compact";
}

function prefersLight(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-color-scheme: light)").matches;
}

export function resolveTheme(theme: ThemeChoice): "dark" | "light" {
  if (theme === "light") return "light";
  if (theme === "dark") return "dark";
  return prefersLight() ? "light" : "dark";
}

export function applyAppearance(theme: ThemeChoice, density: DensityChoice): void {
  const root = rootElement();
  if (!root) return;
  const resolved = resolveTheme(theme);
  root.classList.toggle("theme-light", resolved === "light");
  root.classList.toggle("theme-dark", resolved === "dark");
  root.classList.toggle("density-compact", density === "compact");
}

export function loadTheme(): ThemeChoice {
  const value = storage()?.getItem(THEME_KEY) ?? null;
  return isThemeChoice(value) ? value : "system";
}

export function loadDensity(): DensityChoice {
  const value = storage()?.getItem(DENSITY_KEY) ?? null;
  return isDensityChoice(value) ? value : "comfortable";
}

export function saveTheme(theme: ThemeChoice): void {
  storage()?.setItem(THEME_KEY, theme);
  applyAppearance(theme, loadDensity());
}

export function saveDensity(density: DensityChoice): void {
  storage()?.setItem(DENSITY_KEY, density);
  applyAppearance(loadTheme(), density);
}

function attachSystemThemeListener(): void {
  if (typeof window === "undefined" || mediaListenerAttached) return;
  window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => {
    if (loadTheme() === "system") applyAppearance("system", loadDensity());
  });
  mediaListenerAttached = true;
}

export function loadAppearance(): { theme: ThemeChoice; density: DensityChoice } {
  const theme = loadTheme();
  const density = loadDensity();
  applyAppearance(theme, density);
  attachSystemThemeListener();
  return { theme, density };
}
