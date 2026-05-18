export type ThemeChoice = "light";
export type DensityChoice = "comfortable" | "compact";

const DENSITY_KEY = "glean.density";

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  return window.localStorage;
}

function rootElement(): HTMLElement | null {
  if (typeof document === "undefined") return null;
  return document.documentElement;
}

function isDensityChoice(value: string | null): value is DensityChoice {
  return value === "comfortable" || value === "compact";
}

export function resolveTheme(_theme: ThemeChoice): "light" {
  return "light";
}

export function applyAppearance(_theme: ThemeChoice, density: DensityChoice): void {
  const root = rootElement();
  if (!root) return;
  // Glean is light-mode only. We keep the dark-mode design tokens in app.css
  // for any future re-introduction, but the app always renders in light mode.
  root.classList.add("theme-light");
  root.classList.remove("theme-dark");
  root.classList.toggle("density-compact", density === "compact");
}

export function loadTheme(): ThemeChoice {
  return "light";
}

export function loadDensity(): DensityChoice {
  const value = storage()?.getItem(DENSITY_KEY) ?? null;
  return isDensityChoice(value) ? value : "comfortable";
}

export function saveTheme(_theme: ThemeChoice): void {
  // Theme is fixed to light; no-op. Kept for backwards compatibility with
  // callers that previously toggled themes.
  applyAppearance("light", loadDensity());
}

export function saveDensity(density: DensityChoice): void {
  storage()?.setItem(DENSITY_KEY, density);
  applyAppearance("light", density);
}

export function loadAppearance(): { theme: ThemeChoice; density: DensityChoice } {
  const density = loadDensity();
  applyAppearance("light", density);
  return { theme: "light", density };
}
