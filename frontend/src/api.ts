import axios from 'axios';
import i18n from './i18n';

// Same origin: Vite (dev) or nginx (Docker) forwards /api to the backend, and the login is the page's own cookie
const api = axios.create({ withCredentials: true });

// The backend sends a code (errors.<code> in the locales), alone or with the values the text needs
export function errorMessage(error: unknown): string {
    if (axios.isAxiosError(error)) {
        let detail = error.response?.data?.detail;
        // Validation errors (422) come as a list
        if (Array.isArray(detail)) detail = 'invalid';
        const { code, ...params } = typeof detail === 'string' ? { code: detail } : (detail ?? {});
        if (typeof code === 'string' && i18n.exists(`errors.${code}`)) return i18n.t(`errors.${code}`, params);
        if (!error.response) return i18n.t('errors.network');
    }
    return i18n.t('errors.generic');
}

export default api;
