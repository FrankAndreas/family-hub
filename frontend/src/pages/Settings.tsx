import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import api, { errorMessage } from '../api';
import { useAuth } from '../AuthContext';
import PeopleSettings from '../components/PeopleSettings';
import PinInput from '../components/PinInput';
import TilesSettings from '../components/TilesSettings';
import { BUTTON, BUTTON_DANGER, CARD, ERROR, INPUT } from '../ui';

// Everyone: own PIN, language, logging out everywhere; parents also the people and the apps
export default function Settings() {
    const { t } = useTranslation();
    const { person, reload } = useAuth();
    const [oldPin, setOldPin] = useState('');
    const [newPin, setNewPin] = useState('');
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');

    const changePin = async (e: FormEvent) => {
        e.preventDefault();
        try {
            await api.put('/api/me/pin', { old_pin: oldPin, pin: newPin });
            setOldPin('');
            setNewPin('');
            setError('');
            setMessage(t('settings.pinChanged'));
        } catch (err) {
            setMessage('');
            setError(errorMessage(err));
        }
    };

    const setLanguage = async (language: string) => {
        await api.patch('/api/me', { language });
        await reload();
    };

    const logoutEverywhere = async () => {
        if (!confirm(t('settings.confirmEverywhere'))) return;
        await api.post('/api/logout-everywhere');
        await reload();
    };

    const atHome = person?.at_home ?? true;

    return (
        <div className="space-y-6">
            {!atHome && <p className={`${CARD} text-slate-300`}>{t('settings.manageAtHome')}</p>}
            {atHome && <section className={`${CARD} space-y-3`}>
                <h2 className="text-lg font-semibold">{t('settings.myPin')}</h2>
                <form onSubmit={changePin} className="grid gap-2 sm:grid-cols-3">
                    <div className="text-sm text-slate-400">
                        <label htmlFor="old-pin">{t('settings.oldPin')}</label>
                        <PinInput id="old-pin" value={oldPin} onChange={setOldPin} />
                    </div>
                    <div className="text-sm text-slate-400">
                        <label htmlFor="new-pin">{t('settings.newPin')}</label>
                        <PinInput id="new-pin" value={newPin} onChange={setNewPin} autoComplete="new-password" />
                    </div>
                    <button type="submit" className={`${BUTTON} self-end`} disabled={oldPin.length !== 4 || newPin.length !== 4}>
                        {t('settings.changePin')}
                    </button>
                </form>
                {message && <p className="text-sm text-emerald-300">{message}</p>}
                {error && <p className={ERROR}>{error}</p>}
            </section>}
            <section className={`${CARD} flex flex-wrap items-end gap-4`}>
                <label className="text-sm text-slate-400">{t('settings.language')}
                    <select className={INPUT} value={person?.language ?? 'de'} onChange={e => void setLanguage(e.target.value)}>
                        <option value="de">{t('languages.de')}</option>
                        <option value="en">{t('languages.en')}</option>
                    </select>
                </label>
                <button type="button" className={BUTTON_DANGER} onClick={() => void logoutEverywhere()}>{t('settings.logoutEverywhere')}</button>
            </section>
            {atHome && person?.role === 'PARENT' && (<>
                <PeopleSettings />
                <TilesSettings />
            </>)}
        </div>
    );
}
