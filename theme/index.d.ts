export declare const THEMES: readonly string[];
export declare const DEFAULT_THEME: string;
/** Sets data-theme on <html> (unknown or no theme: the default) and remembers it; returns the theme applied. */
export declare function applyTheme(name?: string | null): string;
