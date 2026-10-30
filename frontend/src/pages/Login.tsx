import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api, { errorMessage } from '../api';
import { useAuth } from '../AuthContext';
import PinInput from '../components/PinInput';
import { safeNext } from '../next';
import type { Tile } from '../types';
import { BUTTON, CARD, ERROR } from '../ui';

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
    const [chosen, setChosen] = useState<string | null>(null);
    const [pin, setPin] = useState('');
    const [error, setError] = useState('');
    // "Forgot PIN" only when the hub can send mails; then the same answer for everyone
    const [canReset, setCanReset] = useState(false);
    const [resetSent, setResetSent] = useState(false);

    useEffect(() => {
        api.get<Name[]>('/api/people/public')
            .then(res => setNames(res.data))
            .catch(() => setOutside(true));
        api.get<{ pin_reset: boolean }>('/api/config').then(res => setCanReset(res.data.pin_reset)).catch(() => undefined);
    }, []);

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

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        if (!chosen) return;
        setError('');
        try {
            await api.post('/api/login', { name: chosen, pin });
            await reload();
            // Back to the app that sent the person here, if it's one of the start page's
            const tiles = (await api.get<Tile[]>('/api/tiles')).data;
            const next = safeNext(params.get('next'), tiles.map(tile => tile.url));
            if (next) window.location.href = next;
            else navigate('/');
        } catch (err) {
            setPin('');
            setError(errorMessage(err));
        }
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
                    <PinInput id="pin" value={pin} onChange={setPin} autoFocus />
                    {error && <p className={ERROR}>{error}</p>}
                    {resetSent && <p role="status" className="text-slate-300">{t('login.resetSent')}</p>}
                    <div className="flex gap-2">
                        <button type="submit" className={`${BUTTON} flex-1`} disabled={pin.length !== 4}>{t('login.submit')}</button>
                        <button type="button" className="px-3 text-slate-400 hover:text-white" onClick={() => { setChosen(null); setPin(''); setError(''); setResetSent(false); }}>
                            {t('login.otherPerson')}
                        </button>
                    </div>
                    {canReset && !resetSent && (
                        <button type="button" className="text-sm text-blue-300 hover:underline" onClick={() => void forgot()}>
                            {t('login.forgot')}
                        </button>
                    )}
                </form>
            )}
        </div>
    );
}
