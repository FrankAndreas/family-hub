import { describe, expect, it } from 'vitest';
import { logoutTarget, safeNext } from './next';

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

describe('logoutTarget', () => {
    it('keeps the app to go back to after the next login', () => {
        expect(logoutTarget('https://budget.local.example.ch/')).toBe('/?next=https%3A%2F%2Fbudget.local.example.ch%2F');
    });
    it('goes to the login without one', () => {
        expect(logoutTarget(null)).toBe('/');
        expect(logoutTarget('')).toBe('/');
    });
});
