import api from './api';
import { browserLanguage, type Language } from './i18n';

// The language before login: the browser's if it is German or English, else the app's default (DEFAULT_LANGUAGE),
// so a Swiss iPad set to French or Italian gets German like the rest of the app
export async function guestLanguage(): Promise<Language> {
    const own = browserLanguage();
    if (own) return own;
    try {
        return (await api.get<{ default_language: Language }>('/api/config')).data.default_language;
    } catch {
        return 'de';
    }
}
