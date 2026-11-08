import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import api from '../api';
import { useAuth } from '../AuthContext';
import PeopleSettings from '../components/PeopleSettings';
import PinInput from '../components/PinInput';
import { usePageTitle } from '../pageTitle';
import TilesSettings from '../components/TilesSettings';
import type { Person } from '../types';
import { BUTTON, BUTTON_DANGER, CARD, ERROR, INPUT } from '../ui';
import { useAction, useResource } from '../useApi';

// Parents: one list of people for both sections, so a person just added can be ticked for an app right away
function Manage() {
    const { data, error, reload } = useResource<Person[]>('/api/people');
    const people = data ?? [];
    return (<>
        <PeopleSettings people={people} loadError={error} reload={reload} />
        <TilesSettings people={people} />
    </>);
}

// Everyone: own PIN, language, logging out everywhere; parents also the people and the apps
export default function Settings() {
    const { t } = useTranslation();
    const { person, reload } = useAuth();
    usePageTitle(t('nav.settings'));
    const [oldPin, setOldPin] = useState('');
    const [newPin, setNewPin] = useState('');
    const [againPin, setAgainPin] = useState('');
    const [message, setMessage] = useState('');
    const pinChange = useAction();
    // Language and "log out everywhere"
    const other = useAction();

    // Typing again clears the last outcome ("PIN changed" or an error), so it never stays next to new input. No timer:
    // a message that goes away by itself may be gone before someone has read it
    const typed = (set: (pin: string) => void) => (pin: string) => {
        set(pin);
        setMessage('');
        pinChange.setError('');
    };

    const changePin = async (e: FormEvent) => {
        e.preventDefault();
        setMessage('');
        if (newPin !== againPin) {
            pinChange.setError(t('reset.mismatch'));
            return;
        }
        if (await pinChange.run(() => api.put('/api/me/pin', { old_pin: oldPin, pin: newPin }))) {
            setOldPin('');
            setNewPin('');
            setAgainPin('');
            setMessage(t('settings.pinChanged'));
        }
    };

    const setLanguage = (language: string) => other.run(async () => {
        await api.patch('/api/me', { language });
        await reload();
    });

    const logoutEverywhere = async () => {
        if (!confirm(t('settings.confirmEverywhere'))) return;
        await other.run(async () => {
            await api.post('/api/logout-everywhere');
            await reload();
        });
    };

    const atHome = person?.at_home ?? true;

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-semibold">{t('nav.settings')}</h1>
            {!atHome && <p className={`${CARD} text-slate-300`}>{t('settings.manageAtHome')}</p>}
            {atHome && <section className={`${CARD} space-y-3`}>
                <h2 className="text-lg font-semibold">{t('settings.myPin')}</h2>
                <form onSubmit={changePin} className="grid gap-2 sm:grid-cols-3">
                    <div className="text-sm text-slate-400">
                        <label htmlFor="old-pin">{t('settings.oldPin')}</label>
                        <PinInput id="old-pin" value={oldPin} onChange={typed(setOldPin)} />
                    </div>
                    <div className="text-sm text-slate-400">
                        <label htmlFor="new-pin">{t('settings.newPin')}</label>
                        <PinInput id="new-pin" value={newPin} onChange={typed(setNewPin)} autoComplete="new-password" />
                    </div>
                    <div className="text-sm text-slate-400">
                        <label htmlFor="again-pin">{t('settings.againPin')}</label>
                        <PinInput id="again-pin" value={againPin} onChange={typed(setAgainPin)} autoComplete="new-password" />
                    </div>
                    <button type="submit" className={`${BUTTON} justify-self-start sm:col-span-3`}
                        disabled={oldPin.length !== 4 || newPin.length !== 4 || againPin.length !== 4}>
                        {t('settings.changePin')}
                    </button>
                </form>
                {message && <p role="status" className="text-sm text-emerald-300">{message}</p>}
                {pinChange.error && <p role="alert" className={ERROR}>{pinChange.error}</p>}
            </section>}
            <section className={`${CARD} space-y-3`}>
                <div className="flex flex-wrap items-end gap-4">
                    <label className="text-sm text-slate-400">{t('settings.language')}
                        <select className={INPUT} value={person?.language ?? 'de'} onChange={e => void setLanguage(e.target.value)}>
                            <option value="de">{t('languages.de')}</option>
                            <option value="en">{t('languages.en')}</option>
                        </select>
                    </label>
                    <button type="button" className={BUTTON_DANGER} onClick={() => void logoutEverywhere()}>{t('settings.logoutEverywhere')}</button>
                </div>
                {other.error && <p role="alert" className={ERROR}>{other.error}</p>}
            </section>
            {atHome && person?.role === 'PARENT' && <Manage />}
        </div>
    );
}
