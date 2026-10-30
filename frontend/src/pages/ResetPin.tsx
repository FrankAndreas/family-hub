import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import api, { errorMessage } from '../api';
import PinInput from '../components/PinInput';
import { BUTTON, CARD, ERROR } from '../ui';

// The link from the "Forgot PIN" mail (or the NAS command): a new PIN, then the login
export default function ResetPin() {
    const { t } = useTranslation();
    // After "#": the token never reaches a server or its access log (security review 2026-10-30)
    const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '');
    const [pin, setPin] = useState('');
    const [again, setAgain] = useState('');
    const [done, setDone] = useState(false);
    const [error, setError] = useState('');

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        if (pin !== again) {
            setError(t('reset.mismatch'));
            return;
        }
        try {
            await api.post('/api/pin-reset/confirm', { token, pin });
            setDone(true);
        } catch (err) {
            setError(errorMessage(err));
        }
    };

    return (
        <div className="mx-auto max-w-md px-4 py-10">
            <div className={`${CARD} space-y-4`}>
                <h1 className="text-xl font-semibold">{t('reset.title')}</h1>
                {done ? (
                    <>
                        <p role="status">{t('reset.done')}</p>
                        {/* A full load: the new PIN ended every login, this browser's too */}
                        <a href="/" className={`${BUTTON} inline-block`}>{t('reset.toLogin')}</a>
                    </>
                ) : (
                    <form onSubmit={submit} className="space-y-3">
                        <label htmlFor="reset-pin" className="block text-sm text-slate-400">{t('reset.newPin')}</label>
                        <PinInput id="reset-pin" value={pin} onChange={setPin} autoComplete="new-password" autoFocus />
                        <label htmlFor="reset-again" className="block text-sm text-slate-400">{t('reset.again')}</label>
                        <PinInput id="reset-again" value={again} onChange={setAgain} autoComplete="new-password" />
                        {error && <p className={ERROR}>{error}</p>}
                        <button type="submit" className={BUTTON} disabled={pin.length !== 4 || again.length !== 4}>{t('reset.submit')}</button>
                    </form>
                )}
            </div>
        </div>
    );
}
