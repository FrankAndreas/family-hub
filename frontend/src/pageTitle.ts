import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

// The tab's title names the page ("Einstellungen · Familie"), so a screen reader and the list of tabs tell the pages
// apart; the start page is just "Familie". Follows the language shown
export function usePageTitle(page: string | null) {
    const { t } = useTranslation();
    const app = t('app.title');
    useEffect(() => {
        document.title = page ? `${page} · ${app}` : app;
    }, [page, app]);
}
