import { useEffect, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { BUTTON_SECONDARY, TOUCH } from '../ui';
import LoginAgain from './LoginAgain';
import { logoutAddress } from '../next';

// The page one is on stands out (NavLink also sets aria-current="page")
const navClass = ({ isActive }: { isActive: boolean }) =>
    `${TOUCH} ${isActive ? 'font-semibold text-white underline decoration-cyan-400 decoration-2 underline-offset-8' : 'text-slate-300 hover:text-white'}`;

// The frame of every page once logged in: the family's name, Start, Settings, and logging out
export default function Layout({ children }: { children: ReactNode }) {
    const { t } = useTranslation();
    const { person, logout } = useAuth();
    const main = useRef<HTMLElement>(null);
    const { pathname } = useLocation();
    const shown = useRef(pathname);
    // Moving to another page puts the focus on its heading: a screen reader reads where one is now, and Tab goes on
    // from there. Not on the first page shown (the login form or the browser keeps theirs)
    useEffect(() => {
        if (shown.current === pathname) return;
        shown.current = pathname;
        const heading = main.current?.querySelector('h1');
        if (!heading) return;
        heading.tabIndex = -1;
        heading.focus();
    }, [pathname]);
    return (
        <div className="mx-auto max-w-5xl px-4 py-4">
            <header className="mb-6 flex flex-wrap items-center gap-3">
                <Link to="/" className="mr-auto text-xl font-semibold text-slate-100"><span aria-hidden="true">🏠 </span>{t('app.title')}</Link>
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
            <main ref={main}>{children}</main>
        </div>
    );
}
