import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import api, { errorMessage } from '../api';
import type { TileFull } from '../types';
import { BUTTON, BUTTON_SECONDARY, CARD, ERROR, INPUT } from '../ui';

interface Form { id: number | null; name: string; icon: string; local_url: string; remote_url: string }

const empty: Form = { id: null, name: '', icon: '', local_url: '', remote_url: '' };

// Parents: the apps on the start page; without an outside address an app is shown at home only
export default function TilesSettings() {
    const { t } = useTranslation();
    const [tiles, setTiles] = useState<TileFull[]>([]);
    const [form, setForm] = useState<Form | null>(null);
    const [error, setError] = useState('');

    const load = useCallback(() => {
        api.get<TileFull[]>('/api/tiles/manage').then(res => setTiles(res.data)).catch(err => setError(errorMessage(err)));
    }, []);
    useEffect(load, [load]);

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
        const body = { name: form.name, icon: form.icon, local_url: form.local_url.trim(), remote_url: form.remote_url.trim() || null };
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
                        <span className="ml-auto flex gap-2 text-sm">
                            <button type="button" disabled={index === 0} className="text-slate-400 hover:text-white disabled:opacity-30"
                                aria-label={t('tiles.up', { name: tile.name })} onClick={() => move(index, -1)}>↑</button>
                            <button type="button" disabled={index === tiles.length - 1} className="text-slate-400 hover:text-white disabled:opacity-30"
                                aria-label={t('tiles.down', { name: tile.name })} onClick={() => move(index, 1)}>↓</button>
                            <button type="button" className="text-blue-300 hover:underline" aria-label={t('tiles.editOf', { name: tile.name })}
                                onClick={() => setForm({ id: tile.id, name: tile.name, icon: tile.icon, local_url: tile.local_url, remote_url: tile.remote_url ?? '' })}>
                                {t('common.edit')}
                            </button>
                            <button type="button" className="text-red-300 hover:underline" aria-label={t('tiles.deleteOf', { name: tile.name })}
                                onClick={() => remove(tile)}>{t('common.delete')}</button>
                        </span>
                    </li>
                ))}
            </ul>
        </section>
    );
}
