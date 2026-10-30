import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import api, { errorMessage } from '../api';
import { useAuth } from '../AuthContext';
import type { Person, Role } from '../types';
import { BUTTON, BUTTON_SECONDARY, CARD, ERROR, INPUT } from '../ui';
import PinInput from './PinInput';

interface Form {
    id: number | null; name: string; email: string; role: Role; color: string; active: boolean; pin: string;
    // Editing oneself: the address as it was, and the own PIN needed to change it
    oldEmail: string; currentPin: string;
}

const empty: Form = { id: null, name: '', email: '', role: 'CHILD', color: '#64748b', active: true, pin: '', oldEmail: '', currentPin: '' };

// Parents: the family's people, in one place for every app (name, e-mail for Cloudflare, role, colour, PIN)
export default function PeopleSettings() {
    const { t } = useTranslation();
    const { person: me } = useAuth();
    const [people, setPeople] = useState<Person[]>([]);
    const [form, setForm] = useState<Form | null>(null);
    const [error, setError] = useState('');

    const load = useCallback(() => {
        api.get<Person[]>('/api/people').then(res => setPeople(res.data)).catch(err => setError(errorMessage(err)));
    }, []);
    useEffect(load, [load]);

    const save = async (e: FormEvent) => {
        e.preventDefault();
        if (!form) return;
        const body = { name: form.name, email: form.email.trim() || null, role: form.role, color: form.color };
        try {
            if (form.id === null) {
                await api.post('/api/people', { ...body, pin: form.pin });
            } else {
                // The PIN first: a child made a parent in this same save is then another parent, whose PIN no one else sets
                if (form.pin) await api.put(`/api/people/${form.id}/pin`, { pin: form.pin });
                const own = form.id === me?.id && body.email !== (form.oldEmail || null);
                await api.patch(`/api/people/${form.id}`, { ...body, active: form.active, ...(own ? { current_pin: form.currentPin } : {}) });
            }
            setForm(null);
            setError('');
            load();
        } catch (err) {
            setError(errorMessage(err));
        }
    };

    const edit = (p: Person) =>
        setForm({ id: p.id, name: p.name, email: p.email ?? '', role: p.role, color: p.color ?? '#64748b', active: p.active, pin: '', oldEmail: p.email ?? '', currentPin: '' });
    const editingSelf = form !== null && form.id !== null && form.id === me?.id;
    const emailChanged = editingSelf && form.email.trim() !== form.oldEmail;
    // Other parents are read-only: each parent changes only themselves and the children

    return (
        <section className={`${CARD} space-y-3`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold">{t('people.title')}</h2>
                {!form && <button type="button" className={BUTTON_SECONDARY} onClick={() => setForm(empty)}>{t('people.add')}</button>}
            </div>
            <p className="text-sm text-slate-400">{t('people.intro')}</p>
            {error && <p className={ERROR}>{error}</p>}
            {form && (
                <form onSubmit={save} className="grid gap-2 sm:grid-cols-2">
                    <label className="text-sm text-slate-400">{t('people.name')}
                        <input className={INPUT} value={form.name} required maxLength={50} onChange={e => setForm({ ...form, name: e.target.value })} />
                    </label>
                    <label className="text-sm text-slate-400">{t('people.email')}
                        <input className={INPUT} type="email" value={form.email} maxLength={254} onChange={e => setForm({ ...form, email: e.target.value })} />
                    </label>
                    <label className="text-sm text-slate-400">{t('people.role')}
                        <select className={INPUT} value={form.role} onChange={e => setForm({ ...form, role: e.target.value as Role })}>
                            <option value="PARENT">{t('people.roles.PARENT')}</option>
                            <option value="CHILD">{t('people.roles.CHILD')}</option>
                        </select>
                    </label>
                    <label className="text-sm text-slate-400">{t('people.color')}
                        <input className={`${INPUT} h-10`} type="color" value={form.color} onChange={e => setForm({ ...form, color: e.target.value })} />
                    </label>
                    {emailChanged && (
                        <div className="text-sm text-slate-400">
                            <label htmlFor="person-current-pin">{t('people.currentPinForEmail')}</label>
                            <PinInput id="person-current-pin" value={form.currentPin} onChange={currentPin => setForm({ ...form, currentPin })} autoComplete="current-password" />
                        </div>
                    )}
                    {!editingSelf && <div className="text-sm text-slate-400">
                        <label htmlFor="person-pin">{form.id === null ? t('people.pin') : t('people.newPinOptional')}</label>
                        <PinInput id="person-pin" value={form.pin} onChange={pin => setForm({ ...form, pin })} autoComplete="new-password" />
                    </div>}
                    {form.id !== null && (
                        <label className="flex items-center gap-2 self-end text-sm text-slate-300">
                            <input type="checkbox" checked={form.active} onChange={e => setForm({ ...form, active: e.target.checked })} />
                            {t('people.active')}
                        </label>
                    )}
                    <div className="flex gap-2 sm:col-span-2">
                        <button type="submit" className={BUTTON} disabled={form.id === null && form.pin.length !== 4}>{t('people.save')}</button>
                        <button type="button" className="px-3 text-slate-400 hover:text-white" onClick={() => setForm(null)}>{t('common.cancel')}</button>
                    </div>
                </form>
            )}
            <ul className="divide-y divide-white/5">
                {people.map(p => (
                    <li key={p.id} className="flex flex-wrap items-center gap-2 py-2">
                        <span aria-hidden="true" className="h-3 w-3 rounded-full" style={{ background: p.color ?? '#64748b' }} />
                        <span className={`min-w-0 break-words font-medium ${p.active ? '' : 'text-slate-500 line-through'}`}>{p.name}</span>
                        <span className="text-sm text-slate-400">{t(`people.roles.${p.role}`)}</span>
                        {p.email && <span className="min-w-0 break-all text-sm text-slate-500">{p.email}</span>}
                        {(p.role !== 'PARENT' || p.id === me?.id) && (
                            <button type="button" className="ml-auto text-sm text-blue-300 hover:underline" onClick={() => edit(p)}
                                aria-label={t('people.editOf', { name: p.name })}>{t('common.edit')}</button>
                        )}
                    </li>
                ))}
            </ul>
        </section>
    );
}
