import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import de from './locales/de';
import en from './locales/en';

export type Language = 'de' | 'en';

// Before login (and after logout) the browser decides, if it speaks German or English (see guestLanguage in
// language.ts for the others); after login the person's own setting
export function browserLanguage(): Language | null {
    const lang = navigator.language.toLowerCase();
    if (lang.startsWith('de')) return 'de';
    if (lang.startsWith('en')) return 'en';
    return null;
}

i18n.use(initReactI18next).init({
    resources: { de: { translation: de }, en: { translation: en } },
    lng: browserLanguage() ?? 'de',
    fallbackLng: 'de',
    interpolation: { escapeValue: false },
});
document.documentElement.lang = i18n.language;

export function applyLanguage(lang: Language) {
    if (i18n.language !== lang) i18n.changeLanguage(lang);
    document.documentElement.lang = lang;
}

export default i18n;
