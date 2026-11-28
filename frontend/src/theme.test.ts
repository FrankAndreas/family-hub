import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { applyTheme, DEFAULT_THEME, THEMES } from 'family-hub-theme';

// family-hub-theme's applyTheme: the page's data-theme and the remembered choice, in node with small stubs
function stubPage(storage: { setItem: (k: string, v: string) => void; getItem: (k: string) => string | null }) {
    const element = { dataset: {} as Record<string, string> };
    vi.stubGlobal('document', { documentElement: element });
    vi.stubGlobal('localStorage', storage);
    return element;
}

describe('applyTheme', () => {
    let saved: Record<string, string>;
    let html: { dataset: Record<string, string> };

    beforeEach(() => {
        saved = {};
        html = stubPage({ setItem: (k, v) => { saved[k] = v; }, getItem: k => saved[k] ?? null });
    });
    afterEach(() => vi.unstubAllGlobals());

    it('applies and remembers a known theme', () => {
        expect(THEMES).toContain('aurora');
        expect(applyTheme('aurora')).toBe('aurora');
        expect(html.dataset.theme).toBe('aurora');
        expect(saved['family-theme']).toBe('aurora');
    });

    it('falls back to the default for unknown or no theme', () => {
        expect(DEFAULT_THEME).toBe('aurora');
        expect(applyTheme('daely')).toBe('aurora');
        expect(applyTheme(null)).toBe('aurora');
        expect(applyTheme(undefined)).toBe('aurora');
        expect(html.dataset.theme).toBe('aurora');
    });

    it('still applies the theme when storage is blocked', () => {
        html = stubPage({ setItem: () => { throw new Error('blocked'); }, getItem: () => { throw new Error('blocked'); } });
        expect(applyTheme('aurora')).toBe('aurora');
        expect(html.dataset.theme).toBe('aurora');
    });
});
