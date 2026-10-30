import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { LOGIN_AGAIN_EVENT } from '../api';
import { BUTTON } from '../ui';

// A change was refused with "login_again": this browser's login is from before the manage cookie (or lost it). One
// more login sets it; everything else keeps working meanwhile
export default function LoginAgain() {
    const { t } = useTranslation();
    const [shown, setShown] = useState(false);
    useEffect(() => {
        const show = () => setShown(true);
        window.addEventListener(LOGIN_AGAIN_EVENT, show);
        return () => window.removeEventListener(LOGIN_AGAIN_EVENT, show);
    }, []);
    if (!shown) return null;
    return (
        <div role="alert" className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
            <p className="mr-auto">{t('errors.login_again')}</p>
            <Link to="/logout" className={BUTTON}>{t('loginAgain.button')}</Link>
        </div>
    );
}
