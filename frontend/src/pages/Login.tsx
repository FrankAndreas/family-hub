import axios from 'axios';
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api, { errorMessage } from '../api';
import { useAuth } from '../AuthContext';
import PinInput from '../components/PinInput';
import { safeNext } from '../next';
import type { Tile } from '../types';
import { BUTTON, BUTTON_SECONDARY, CARD, ERROR, TOUCH } from '../ui';

interface Name { name: string; color: string | null }

// At home: pick your name, type your PIN. Outside, Cloudflare Access is the login: the hub has no PIN login there
export default function Login() {
    const { t } = useTranslation();
    const { reload } = useAuth();
    const navigate = useNavigate();
    const [params] = useSearchParams();
    const [names, setNames] = useState<Name[] | null>(null);
    // The PIN login is refused through Cloudflare: the person's e-mail isn't in the family list
    const [outside, setOutside] = useState(false);
    // The names couldn't be loaded (hub restarting, NAS out of reach): say so instead of "not in the family list"
    const [loadError, setLoadError] = useState('');
    const [chosen, setChosen] = useState<string | null>(null);
    const [pin, setPin] = useState('');
    const [error, setError] = useState('');
    // "Forgot PIN" only when the hub can send mails; then the same answer for everyone
    const [canReset, setCanReset] = useState(false);
    const [resetSent, setResetSent] = useState(false);

    const loadNames = useCallback(() => {
        api.get<Name[]>('/api/people/public')
            .then(res => setNames(res.data))
            .catch(err => {
                // Only the backend's own refusal means "outside" (auth.require_home)
                if (axios.isAxiosError(err) && err.response?.status === 403 && err.response.data?.detail === 'login_at_home_only') setOutside(true);
                else setLoadError(errorMessage(err));
            });
        api.get<{ mails: boolean }>('/api/config').then(res => setCanReset(res.data.mails)).catch(() => undefined);
    }, []);
    useEffect(loadNames, [loadNames]);

    const forgot = async () => {
        if (!chosen) return;
        setError('');
        try {
            await api.post('/api/pin-reset', { name: chosen });
            setResetSent(true);
        } catch (err) {
            setError(errorMessage(err));
        }
    };

    // One login at a time: the fourth digit sends it, and Enter or the button may follow right after
    const busy = useRef(false);
    const logIn = async (value: string) => {
        if (!chosen || busy.current) return;
        busy.current = true;
        setError('');
        try {
            await api.post('/api/login', { name: chosen, pin: value });
            await reload();
            // Back to the app that sent the person here, if it's one of the start page's
            const tiles = (await api.get<Tile[]>('/api/tiles')).data;
            const next = safeNext(params.get('next'), tiles.map(tile => tile.url));
            if (next) window.location.href = next;
            else navigate('/');
        } catch (err) {
            setPin('');
            setError(errorMessage(err));
            // Straight back to typing, also after a click on the button
            document.getElementById('pin')?.focus();
        } finally {
            busy.current = false;
        }
    };

    const submit = (e: FormEvent) => {
        e.preventDefault();
        void logIn(pin);
    };

    if (outside) {
        return (
            <div className="mx-auto max-w-md px-4 py-10">
                <div className={CARD}>
                    <h1 className="mb-2 text-xl font-semibold">{t('login.outsideTitle')}</h1>
                    <p className="text-slate-300">{t('login.outside')}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="mx-auto max-w-md px-4 py-10">
            <h1 className="mb-6 text-center text-2xl font-semibold">🏠 {t('login.title')}</h1>
            {loadError && (
                <div className="space-y-3 text-center">
                    <p role="alert" className={ERROR}>{loadError}</p>
                    <button type="button" className={BUTTON_SECONDARY} onClick={() => { setLoadError(''); loadNames(); }}>{t('login.retry')}</button>
                </div>
            )}
            {names === null && !loadError && <p role="status" className="text-center text-slate-400">{t('common.loading')}</p>}
            {!chosen ? (
                <div className="grid grid-cols-2 gap-3">
                    {(names ?? []).map(n => (
                        <button key={n.name} type="button" onClick={() => setChosen(n.name)}
                            className="glass-card flex items-center gap-3 p-4 text-left text-lg hover:bg-white/5">
                            <span aria-hidden="true" className="h-4 w-4 shrink-0 rounded-full" style={{ background: n.color ?? '#64748b' }} />
                            <span className="min-w-0 break-words">{n.name}</span>
                        </button>
                    ))}
                </div>
            ) : (
                <form onSubmit={submit} className={`${CARD} space-y-4`}>
                    <p className="text-lg">{chosen}</p>
                    <label htmlFor="pin" className="sr-only">{t('login.pin')}</label>
                    <PinInput id="pin" value={pin} autoFocus onChange={value => {
                        setPin(value);
                        // A PIN has 4 digits: the last one logs in, one tap less on the tablet
                        if (value.length === 4) void logIn(value);
                    }} />
                    {error && <p role="alert" className={ERROR}>{error}</p>}
                    {resetSent && <p role="status" className="text-slate-300">{t('login.resetSent')}</p>}
                    <div className="flex gap-2">
                        <button type="submit" className={`${BUTTON} flex-1`} disabled={pin.length !== 4}>{t('login.submit')}</button>
                        <button type="button" className="px-3 text-slate-400 hover:text-white" onClick={() => { setChosen(null); setPin(''); setError(''); setResetSent(false); }}>
                            {t('login.otherPerson')}
                        </button>
                    </div>
                    {canReset && !resetSent && (
                        <button type="button" className={`${TOUCH} text-sm text-blue-300 hover:underline`} onClick={() => void forgot()}>
                            {t('login.forgot')}
                        </button>
                    )}
                </form>
            )}
        </div>
    );
}
