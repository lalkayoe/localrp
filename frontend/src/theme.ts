/**
 * Chat appearance themes. Each theme is a `data-theme` value that switches
 * which CSS custom-property block in styles/themes.css is active — nothing
 * else in the app needs to know about themes, since every component already
 * reads colors through the --bg-*/--accent*/--text-* variables (see
 * styles/theme.css). Adding a theme is just adding another block there plus
 * an entry to THEMES below for the picker UI.
 *
 * Persisted in two places on purpose:
 * - localStorage, applied synchronously in main.tsx before React even
 *   mounts, so there's no flash of the default theme on load.
 * - the backend's generic settings store (key "ui_theme"), so the choice
 *   follows you to another device/browser the same way every other setting
 *   does. SettingsPage reconciles the two on load (backend wins if they
 *   differ, since it's the source of truth once fetched).
 */

export interface ThemeDef {
  id: string;
  name: string;
  /** [background, accent, text] — just for rendering a little preview swatch, not applied directly. */
  swatch: [string, string, string];
}

export const THEMES: ThemeDef[] = [
  { id: "graphite", name: "Graphite (по умолчанию)", swatch: ["#101116", "#6c63ff", "#e8e7ec"] },
  { id: "void-black", name: "Void Black", swatch: ["#000000", "#9a9aa3", "#f2f2f4"] },
  { id: "neon-grid", name: "Neon Grid", swatch: ["#05060a", "#00e5ff", "#eafeff"] },
  { id: "crimson-noir", name: "Crimson Noir", swatch: ["#0c0507", "#ff3d5a", "#f5e6e8"] },
];

const STORAGE_KEY = "localrp_theme";
const DEFAULT_THEME = "graphite";

export function applyTheme(themeId: string): void {
  document.documentElement.setAttribute("data-theme", themeId);
}

export function getStoredTheme(): string {
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME;
}

export function storeTheme(themeId: string): void {
  localStorage.setItem(STORAGE_KEY, themeId);
}
