import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import api from './api';
import { applyLanguage } from './i18n';
import { guestLanguage } from './language';
import type { Person } from './types';

interface Auth {
    person: Person | null;
    // Still asking the backend who is logged in
    loading: boolean;
    reload: () => Promise<void>;
    logout: () => Promise<void>;
}

const AuthContext = createContext<Auth | null>(null);

// Who is logged in: the hub's cookie at home, Cloudflare Access outside; the backend knows, the page asks it
export function AuthProvider({ children }: { children: ReactNode }) {
    const [person, setPerson] = useState<Person | null>(null);
    const [loading, setLoading] = useState(true);
    // Raised by every logout: an answer to "who is logged in" asked before it is stale (security review 2026-10-30;
    // the logout page asks and logs out at the same time)
    const generation = useRef(0);
    // A logout on its way: asking waits for it, so the answer comes from after it (React starts the logout page's
    // effect before this provider's first question)
    const loggingOut = useRef<Promise<unknown>>(Promise.resolve());

    // Ask who is logged in; the state is set once the answer is there
    const ask = useCallback(async () => {
        await loggingOut.current;
        const asked = generation.current;
        return api.get<Person>('/api/me').then(
            res => {
                if (asked !== generation.current) return;
                setPerson(res.data);
                applyLanguage(res.data.language);
            },
            async () => {
                if (asked !== generation.current) return;
                setPerson(null);
                applyLanguage(await guestLanguage());
            },
        ).finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        void ask();
    }, [ask]);

    const reload = useCallback(async () => {
        await ask();
    }, [ask]);

    const logout = useCallback(async () => {
        generation.current += 1;
        const done = api.post('/api/logout');
        loggingOut.current = done.catch(() => undefined);
        await done;
        setPerson(null);
    }, []);

    return <AuthContext.Provider value={{ person, loading, reload, logout }}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- the hook belongs with its provider
export function useAuth(): Auth {
    const auth = useContext(AuthContext);
    if (!auth) throw new Error('useAuth outside AuthProvider');
    return auth;
}
