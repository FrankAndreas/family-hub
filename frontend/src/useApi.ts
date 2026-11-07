import { useCallback, useEffect, useState } from 'react';
import api, { errorMessage } from './api';

// What a GET from the backend gives a component: the data (null until the first answer), the error to show, and a way
// to load it again after a change. Data already shown stays while it loads again, so lists don't flicker
export function useResource<T>(url: string) {
    const [data, setData] = useState<T | null>(null);
    const [error, setError] = useState('');
    const [round, setRound] = useState(0);

    useEffect(() => {
        // An answer that comes after the next request started (or after the page closed) is dropped
        let current = true;
        api.get<T>(url).then(
            res => { if (current) { setData(res.data); setError(''); } },
            err => { if (current) setError(errorMessage(err)); },
        );
        return () => { current = false; };
    }, [url, round]);

    const reload = useCallback(() => setRound(r => r + 1), []);
    return { data, error, reload };
}

// A change sent to the backend: its error (cleared by the next one that works) and what follows a success, e.g.
// loading the list again. `run` says whether it worked
export function useAction(after?: () => void) {
    const [error, setError] = useState('');

    const run = useCallback(async (request: () => Promise<unknown>) => {
        try {
            await request();
            setError('');
            after?.();
            return true;
        } catch (err) {
            setError(errorMessage(err));
            return false;
        }
    }, [after]);

    return { run, error, setError };
}
