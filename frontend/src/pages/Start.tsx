import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { safeNext } from '../next';
import type { Tile } from '../types';
import { ERROR } from '../ui';
import { useResource } from '../useApi';

// The start page: a tile per app, opening the app itself (at home its home address, outside its outside one).
// With ?next=<app> (an app sent the person here: to log in, or to renew a login in its last week) straight back to
// that app, if it's one of the start page's. Loading this page already renewed the login (GET /api/me)
export default function Start() {
    const { t } = useTranslation();
    const { person } = useAuth();
    const { data: tiles, error } = useResource<Tile[]>('/api/tiles');
    const [params, setParams] = useSearchParams();
    const next = params.get('next');

    useEffect(() => {
        if (!next || !tiles) return;
        const target = safeNext(next, tiles.map(tile => tile.url));
        if (target) window.location.replace(target);
        else setParams({}, { replace: true });
    }, [next, tiles, setParams]);

    // On the way back to the app: no flash of the start page (an unknown ?next= is dropped, and the page shows)
    if (next && !error) return <p role="status" className="text-slate-400">{t('common.loading')}</p>;

    return (
        <>
            <h1 className="mb-4 text-2xl font-semibold">{t('start.hello', { name: person?.name ?? '' })}</h1>
            {error && <p role="alert" className={ERROR}>{error}</p>}
            {tiles === null && !error && <p role="status" className="text-slate-400">{t('common.loading')}</p>}
            {tiles && tiles.length === 0 && <p className="text-slate-400">{t('start.none')}</p>}
            <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                {(tiles ?? []).map(tile => (
                    <li key={tile.id}>
                        <a href={tile.url} className="glass-card flex h-full flex-col items-center gap-2 p-5 text-center hover:bg-white/5">
                            <span aria-hidden="true" className="text-4xl">{tile.icon || '🔗'}</span>
                            <span className="break-words text-lg font-medium">{tile.name}</span>
                        </a>
                    </li>
                ))}
            </ul>
        </>
    );
}
