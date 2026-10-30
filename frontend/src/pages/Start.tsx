import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import api, { errorMessage } from '../api';
import { useAuth } from '../AuthContext';
import type { Tile } from '../types';
import { ERROR } from '../ui';

// The start page: a tile per app, opening the app itself (at home its home address, outside its outside one)
export default function Start() {
    const { t } = useTranslation();
    const { person } = useAuth();
    const [tiles, setTiles] = useState<Tile[] | null>(null);
    const [error, setError] = useState('');

    useEffect(() => {
        api.get<Tile[]>('/api/tiles').then(res => setTiles(res.data)).catch(err => setError(errorMessage(err)));
    }, []);

    return (
        <>
            <h1 className="mb-4 text-2xl font-semibold">{t('start.hello', { name: person?.name ?? '' })}</h1>
            {error && <p className={ERROR}>{error}</p>}
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
