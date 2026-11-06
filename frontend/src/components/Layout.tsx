import { type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, NavLink } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { BUTTON_SECONDARY } from '../ui';
import LoginAgain from './LoginAgain';
import { logoutAddress } from '../next';

// The page one is on stands out (NavLink also sets aria-current="page")
const navClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? 'font-semibold text-white underline decoration-cyan-400 decoration-2 underline-offset-8' : 'text-slate-300 hover:text-white';

// The frame of every page once logged in: the family's name, Start, Settings, and logging out
export default function Layout({ children }: { children: ReactNode }) {
    const { t } = useTranslation();
    const { person, logout } = useAuth();
    return (
        <div className="mx-auto max-w-5xl px-4 py-4">
            <header className="mb-6 flex flex-wrap items-center gap-3">
                <Link to="/" className="mr-auto text-xl font-semibold text-slate-100">🏠 {t('app.title')}</Link>
                <nav className="flex flex-wrap items-center gap-3 text-sm">
                    <NavLink to="/" end className={navClass}>{t('nav.start')}</NavLink>
                    <NavLink to="/settings" className={navClass}>{t('nav.settings')}</NavLink>
                    {person && (
                        <button type="button" className={BUTTON_SECONDARY} onClick={() => {
                            const outside = logoutAddress(person.at_home);
                            if (outside) window.location.href = outside;
                            else void logout();
                        }}>
                            {t('nav.logout')}
                        </button>
                    )}
                </nav>
            </header>
            <LoginAgain />
            <main>{children}</main>
        </div>
    );
}
