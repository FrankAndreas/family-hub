import { describe, expect, it } from 'vitest';
import { safeNext } from './next';

describe('safeNext', () => {
    const tiles = ['https://budget.local.example.ch', 'https://essen.local.example.ch/'];
    it('goes back to an app on the start page', () => {
        expect(safeNext('https://budget.local.example.ch/accounts?x=1', tiles)).toBe('https://budget.local.example.ch/accounts?x=1');
    });
    it('refuses anything else', () => {
        expect(safeNext('https://evil.example.com/', tiles)).toBeNull();
        expect(safeNext('https://budget.local.example.ch.evil.com/', tiles)).toBeNull();
        expect(safeNext('javascript:alert(1)', tiles)).toBeNull();
        expect(safeNext('/settings', tiles)).toBeNull();
        expect(safeNext(null, tiles)).toBeNull();
    });
});
