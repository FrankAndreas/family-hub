import 'i18next';
import type de from './locales/de';

// Typed keys: t('nav.plan') is checked against de.ts
declare module 'i18next' {
    interface CustomTypeOptions {
        resources: { translation: typeof de };
    }
}
