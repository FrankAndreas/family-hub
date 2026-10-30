import { describe, expect, it } from 'vitest';
import { logoutTarget, safeNext } from './next';

describe('safeNext', () => {
    const tiles = ['https://budget.local.example.ch', 'https://essen.local.example.ch/'];
    it('goes back to an app on the start page', () => {
        expect(safeNext('https://budget.local.example.ch/accounts?x=1', tiles, 'home.local.example.ch')).toBe('https://budget.local.example.ch/accounts?x=1');
    });
    it('refuses anything else', () => {
        const hub = 'home.local.example.ch';
        expect(safeNext('https://evil.example.com/', tiles, hub)).toBeNull();
        expect(safeNext('https://budget.local.example.ch.evil.com/', tiles, hub)).toBeNull();
        expect(safeNext('javascript:alert(1)', tiles, hub)).toBeNull();
        expect(safeNext('/settings', tiles, hub)).toBeNull();
        expect(safeNext(null, tiles, hub)).toBeNull();
    });
});

// Security review 2026-10-30: a parent could add a tile for a site of their own and send the other parent there
describe('safeNext, only the family\'s own addresses', () => {
    const hub = 'home.local.example.ch';
    const tiles = ['https://budget.local.example.ch', 'https://phish.example.com', 'http://localhost:3110'];
    it('takes an app under the hub\'s own domain', () => {
        expect(safeNext('https://budget.local.example.ch/', tiles, hub)).toBe('https://budget.local.example.ch/');
    });
    it('refuses a tile elsewhere', () => {
        expect(safeNext('https://phish.example.com/', tiles, hub)).toBeNull();
    });
    it('takes the same machine in development', () => {
        expect(safeNext('http://localhost:3110/settings', tiles, 'localhost')).toBe('http://localhost:3110/settings');
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
