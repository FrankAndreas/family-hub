import { type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { BUTTON_SECONDARY } from '../ui';

// The frame of every page once logged in: the family's name, Start, Settings, and logging out
export default function Layout({ children }: { children: ReactNode }) {
    const { t } = useTranslation();
    const { person, logout } = useAuth();
    return (
        <div className="mx-auto max-w-5xl px-4 py-4">
            <header className="mb-6 flex flex-wrap items-center gap-3">
                <Link to="/" className="mr-auto text-xl font-semibold text-slate-100">🏠 {t('app.title')}</Link>
                <nav className="flex flex-wrap items-center gap-3 text-sm">
                    <Link to="/" className="text-slate-300 hover:text-white">{t('nav.start')}</Link>
                    <Link to="/settings" className="text-slate-300 hover:text-white">{t('nav.settings')}</Link>
                    {person && (
                        <button type="button" className={BUTTON_SECONDARY} onClick={() => void logout()}>
                            {t('nav.logout')}
                        </button>
                    )}
                </nav>
            </header>
            <main>{children}</main>
        </div>
    );
}
