import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import api, { errorMessage } from '../api';
import { BUTTON, CARD, ERROR } from '../ui';

// The link mailed to a new e-mail address: opening it makes the address count (security review 2026-10-30)
export default function ConfirmEmail() {
    const { t } = useTranslation();
    // After "#": the token never reaches a server or its access log
    const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '');
    const [state, setState] = useState<'busy' | 'done' | 'failed'>('busy');
    const [error, setError] = useState('');
    // The link works once: send it once, even when React runs the effect twice (development)
    const sent = useRef(false);

    useEffect(() => {
        if (sent.current) return;
        sent.current = true;
        api.post('/api/email-confirm', { token })
            .then(() => setState('done'))
            .catch(err => { setError(errorMessage(err)); setState('failed'); });
    }, [token]);

    return (
        <div className="mx-auto max-w-md px-4 py-10">
            <div className={`${CARD} space-y-4`}>
                <h1 className="text-xl font-semibold">{t('confirmEmail.title')}</h1>
                {state === 'done' && <p role="status">{t('confirmEmail.done')}</p>}
                {state === 'failed' && <p className={ERROR}>{error}</p>}
                {state !== 'busy' && <a href="/" className={`${BUTTON} inline-block`}>{t('confirmEmail.toStart')}</a>}
            </div>
        </div>
    );
}
