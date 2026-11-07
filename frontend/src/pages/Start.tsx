import { useTranslation } from 'react-i18next';
import { useAuth } from '../AuthContext';
import type { Tile } from '../types';
import { ERROR } from '../ui';
import { useResource } from '../useApi';

// The start page: a tile per app, opening the app itself (at home its home address, outside its outside one)
export default function Start() {
    const { t } = useTranslation();
    const { person } = useAuth();
    const { data: tiles, error } = useResource<Tile[]>('/api/tiles');

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
