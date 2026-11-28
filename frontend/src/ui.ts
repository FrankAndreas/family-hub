// Shared Tailwind classes, so forms and cards look the same everywhere (the theme's roles, family-hub-theme)
// line-strong: a field's outline reaches 3:1 on the cards (WCAG for controls); colours by role (family-hub-theme)
export const FIELD =
    'rounded-control border border-line-strong bg-field p-2 text-ink focus:border-accent focus:outline-none';
export const INPUT = `${FIELD} w-full`;
export const BUTTON = 'btn-primary';
export const BUTTON_SECONDARY =
    'rounded-control border border-line px-4 py-2 text-ink hover:bg-hover disabled:opacity-50';
export const BUTTON_DANGER =
    'rounded-control border border-danger/40 px-4 py-2 text-danger hover:bg-danger/15 disabled:opacity-50';
export const CARD = 'glass-card p-5';
export const ERROR = 'rounded-control border border-danger/30 bg-danger/15 p-3 text-sm text-danger';
// Small text buttons in lists (↑ ↓ Edit Delete): a finger-sized target on touch screens, unchanged with a mouse
export const TOUCH = 'inline-flex items-center justify-center pointer-coarse:min-h-11 pointer-coarse:min-w-11';
