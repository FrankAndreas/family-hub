// family-hub-theme: which theme the page shows. Kept in step with theme-init.js (which runs before the page renders).
export const THEMES = Object.freeze(['aurora']);
export const DEFAULT_THEME = 'aurora';
const KEY = 'family-theme';

// The person's theme on the page (data-theme on <html>), remembered for the next page load; an unknown theme or none
// (logged out) gives the default. Storage that is blocked only means the next load starts with the default.
export function applyTheme(name) {
  const theme = THEMES.includes(name) ? name : DEFAULT_THEME;
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // Private mode or blocked storage
  }
  return theme;
}
