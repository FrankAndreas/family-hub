import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import api, { errorMessage } from '../api';
import { useAuth } from '../AuthContext';
import type { Person, TileFull } from '../types';
import { BUTTON, BUTTON_SECONDARY, CARD, ERROR, INPUT } from '../ui';

interface Form {
    id: number | null; name: string; icon: string; local_url: string; remote_url: string; app_key: string; people: number[];
    share_email: boolean; cf_audience: string;
    // As saved: the other parents who used the app (only they can untick themselves; while they are ticked its key stays),
    // and when each person last used it
    protected: number[]; last_used: Record<number, string>;
}

const empty: Form = {
    id: null, name: '', icon: '', local_url: '', remote_url: '', app_key: '', people: [], share_email: false, cf_audience: '',
    protected: [], last_used: {},
};

// Parents: the apps on the start page; without an outside address an app is shown at home only. An app that uses the
// family login has a key, and only the people ticked for it see and use it. The people come from the settings page,
// so someone just added in the people's section can be ticked here right away
export default function TilesSettings({ people }: { people: Person[] }) {
    const { t, i18n } = useTranslation();
    const { person: me } = useAuth();
    const [tiles, setTiles] = useState<TileFull[]>([]);
    const [form, setForm] = useState<Form | null>(null);
    const [error, setError] = useState('');

    const load = useCallback(() => {
        api.get<TileFull[]>('/api/tiles/manage').then(res => setTiles(res.data)).catch(err => setError(errorMessage(err)));
    }, []);
    useEffect(load, [load]);

    // As the backend: a parent can't take an app away from another parent who uses it (tiles_api.change_tile)
    const protectedParents = (tile: TileFull) => {
        const used = new Set(tile.usage.map(u => u.person_id));
        return people.filter(p => p.role === 'PARENT' && p.id !== me?.id && tile.people.includes(p.id) && used.has(p.id)).map(p => p.id);
    };
    const names = (ids: number[]) => people.filter(p => ids.includes(p.id)).map(p => p.name).join(', ');
    const keyLocked = form !== null && form.protected.length > 0;
    const date = (iso: string) => new Date(iso).toLocaleDateString(i18n.language, { dateStyle: 'medium' });

    const call = async (request: () => Promise<unknown>) => {
        try {
            await request();
            setError('');
            load();
        } catch (err) {
            setError(errorMessage(err));
        }
    };

    const save = (e: FormEvent) => {
        e.preventDefault();
        if (!form) return;
        const app_key = form.app_key.trim() || null;
        const body = {
            name: form.name, icon: form.icon, local_url: form.local_url.trim(), remote_url: form.remote_url.trim() || null,
            app_key, people: app_key ? form.people : [], share_email: Boolean(app_key) && form.share_email,
            cf_audience: (app_key && form.cf_audience.trim().toLowerCase()) || null,
        };
        void call(async () => {
            if (form.id === null) await api.post('/api/tiles', body);
            else await api.patch(`/api/tiles/${form.id}`, body);
            setForm(null);
        });
    };

    const move = (index: number, by: number) => {
        const ids = tiles.map(tile => tile.id);
        [ids[index], ids[index + by]] = [ids[index + by], ids[index]];
        void call(() => api.put('/api/tiles/order', ids));
    };

    const remove = (tile: TileFull) => {
        if (confirm(t('tiles.confirmDelete', { name: tile.name }))) void call(() => api.delete(`/api/tiles/${tile.id}`));
    };

    return (
        <section className={`${CARD} space-y-3`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold">{t('tiles.title')}</h2>
                {!form && <button type="button" className={BUTTON_SECONDARY} onClick={() => setForm(empty)}>{t('tiles.add')}</button>}
            </div>
            <p className="text-sm text-slate-400">{t('tiles.intro')}</p>
            {error && <p className={ERROR}>{error}</p>}
            {form && (
                <form onSubmit={save} className="grid gap-2 sm:grid-cols-2">
                    <label className="text-sm text-slate-400">{t('tiles.name')}
                        <input className={INPUT} value={form.name} required maxLength={50} onChange={e => setForm({ ...form, name: e.target.value })} />
                    </label>
                    <label className="text-sm text-slate-400">{t('tiles.icon')}
                        <input className={INPUT} value={form.icon} maxLength={16} onChange={e => setForm({ ...form, icon: e.target.value })} />
                    </label>
                    <label className="text-sm text-slate-400">{t('tiles.localUrl')}
                        <input className={INPUT} type="url" value={form.local_url} required placeholder={t('tiles.localExample')}
                            onChange={e => setForm({ ...form, local_url: e.target.value })} />
                    </label>
                    <label className="text-sm text-slate-400">{t('tiles.remoteUrl')}
                        <input className={INPUT} type="url" value={form.remote_url} placeholder={t('tiles.remoteEmpty')}
                            onChange={e => setForm({ ...form, remote_url: e.target.value })} />
                    </label>
                    <div className="text-sm text-slate-400">
                        <label>{t('tiles.appKey')}
                            <input className={`${INPUT} disabled:opacity-50`} value={form.app_key} maxLength={20} pattern="[a-z][a-z0-9\-]{1,19}"
                                placeholder={t('tiles.appKeyHint')} disabled={keyLocked} aria-describedby={keyLocked ? 'key-locked' : undefined}
                                onChange={e => setForm({ ...form, app_key: e.target.value })} />
                        </label>
                        {keyLocked && <p id="key-locked" className="mt-1 text-xs">{t('tiles.keyLocked', { names: names(form.protected) })}</p>}
                    </div>
                    {form.app_key.trim() && (
                        <fieldset className="text-sm text-slate-400 sm:col-span-2">
                            <legend>{t('tiles.who')}</legend>
                            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                                {people.filter(p => p.active).map(person => {
                                    const locked = form.protected.includes(person.id);
                                    const lastUsed = form.last_used[person.id];
                                    return (
                                        <span key={person.id} className="flex items-center gap-1">
                                            <label className={`flex items-center gap-1 text-slate-200 ${locked ? 'opacity-50' : ''}`}
                                                title={locked ? t('tiles.lockedParent', { name: person.name }) : undefined}>
                                                <input type="checkbox" checked={form.people.includes(person.id)} disabled={locked}
                                                    onChange={e => setForm({
                                                        ...form,
                                                        people: e.target.checked ? [...form.people, person.id] : form.people.filter(id => id !== person.id),
                                                    })} />
                                                {person.name}
                                            </label>
                                            {form.id !== null && form.people.includes(person.id) && (
                                                <span className="text-xs">
                                                    ({lastUsed ? t('tiles.lastUsed', { date: date(lastUsed) }) : t('tiles.neverUsed')})
                                                </span>
                                            )}
                                        </span>
                                    );
                                })}
                            </div>
                            <label className="mt-2 flex items-center gap-1 text-slate-200">
                                <input type="checkbox" checked={form.share_email}
                                    onChange={e => setForm({ ...form, share_email: e.target.checked })} />
                                {t('tiles.shareEmail')}
                            </label>
                            <label className="mt-2 block">{t('tiles.cfAudience')}
                                <input className={INPUT} value={form.cf_audience} maxLength={64} pattern="[0-9a-fA-F]{64}"
                                    placeholder={t('tiles.cfAudienceHint')} onChange={e => setForm({ ...form, cf_audience: e.target.value })} />
                            </label>
                        </fieldset>
                    )}
                    <div className="flex gap-2 sm:col-span-2">
                        <button type="submit" className={BUTTON}>{t('tiles.save')}</button>
                        <button type="button" className="px-3 text-slate-400 hover:text-white" onClick={() => setForm(null)}>{t('common.cancel')}</button>
                    </div>
                </form>
            )}
            <ul className="divide-y divide-white/5">
                {tiles.map((tile, index) => (
                    <li key={tile.id} className="flex flex-wrap items-center gap-2 py-2">
                        <span aria-hidden="true" className="text-xl">{tile.icon || '🔗'}</span>
                        <span className="min-w-0 break-words font-medium">{tile.name}</span>
                        <span className="text-sm text-slate-400">{tile.remote_url ? t('tiles.alsoOutside') : t('tiles.homeOnly')}</span>
                        {tile.app_key && <span className="text-sm text-slate-400">· {t('tiles.peopleCount', { count: tile.people.length })}</span>}
                        <span className="ml-auto flex gap-2 text-sm">
                            <button type="button" disabled={index === 0} className="text-slate-400 hover:text-white disabled:opacity-30"
                                aria-label={t('tiles.up', { name: tile.name })} onClick={() => move(index, -1)}>↑</button>
                            <button type="button" disabled={index === tiles.length - 1} className="text-slate-400 hover:text-white disabled:opacity-30"
                                aria-label={t('tiles.down', { name: tile.name })} onClick={() => move(index, 1)}>↓</button>
                            <button type="button" className="text-blue-300 hover:underline" aria-label={t('tiles.editOf', { name: tile.name })}
                                onClick={() => setForm({
                                    id: tile.id, name: tile.name, icon: tile.icon, local_url: tile.local_url, remote_url: tile.remote_url ?? '',
                                    app_key: tile.app_key ?? '', people: tile.people, share_email: tile.share_email,
                                    cf_audience: tile.cf_audience ?? '', protected: protectedParents(tile),
                                    last_used: Object.fromEntries(tile.usage.map(u => [u.person_id, u.last_used_at])),
                                })}>
                                {t('common.edit')}
                            </button>
                            <button type="button" className="text-red-300 hover:underline disabled:opacity-30 disabled:no-underline"
                                aria-label={t('tiles.deleteOf', { name: tile.name })} disabled={protectedParents(tile).length > 0}
                                title={protectedParents(tile).length > 0 ? t('tiles.deleteLocked', { names: names(protectedParents(tile)) }) : undefined}
                                onClick={() => remove(tile)}>{t('common.delete')}</button>
                        </span>
                    </li>
                ))}
            </ul>
        </section>
    );
}
