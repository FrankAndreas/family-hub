import i18next from 'i18next';
import { describe, expect, it } from 'vitest';
import de from './locales/de';
import en from './locales/en';

// The lock's minutes come from the backend; api.errorMessage passes them as the count, which picks the text
describe('lock message', () => {
    const i18n = i18next.createInstance();
    void i18n.init({ resources: { de: { translation: de }, en: { translation: en } }, lng: 'en', interpolation: { escapeValue: false } });

    it('says "a minute" for one, the number for more, in both languages', () => {
        const say = (lng: string, minutes: number) => i18n.t('errors.locked', { lng, minutes, count: minutes });
        expect(i18n.exists('errors.locked', { count: 1 })).toBe(true);
        expect(say('en', 1)).toBe('Too many wrong PINs. Try again in a minute.');
        expect(say('en', 15)).toBe('Too many wrong PINs. Try again in 15 minutes.');
        expect(say('de', 1)).toBe('Zu viele falsche PINs. Versuche es in einer Minute wieder.');
        expect(say('de', 30)).toBe('Zu viele falsche PINs. Versuche es in 30 Minuten wieder.');
    });
});
