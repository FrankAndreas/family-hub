import axios from 'axios';
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import api from './api';
import { applyLanguage } from './i18n';
import { guestLanguage } from './language';
import type { Person } from './types';

interface Auth {
    person: Person | null;
    // Still asking the backend who is logged in
    loading: boolean;
    // The backend didn't answer (restarting, an update): not the same as logged out, so it keeps asking
    unreachable: boolean;
    reload: () => Promise<void>;
    logout: () => Promise<void>;
}

const AuthContext = createContext<Auth | null>(null);
const RETRY_MS = 5000;

// Who is logged in: the hub's cookie at home, Cloudflare Access outside; the backend knows, the page asks it
export function AuthProvider({ children }: { children: ReactNode }) {
    const [person, setPerson] = useState<Person | null>(null);
    const [loading, setLoading] = useState(true);
    const [unreachable, setUnreachable] = useState(false);
    // Raised to ask again while the backend can't be reached
    const [round, setRound] = useState(0);
    // Raised by every logout: an answer to "who is logged in" asked before it is stale (security review 2026-10-30;
    // the logout page asks and logs out at the same time)
    const generation = useRef(0);
    // A logout on its way: asking waits for it, so the answer comes from after it (React starts the logout page's
    // effect before this provider's first question)
    const loggingOut = useRef<Promise<unknown>>(Promise.resolve());
    // While the backend can't be reached: the next try, and whether the guest language was set meanwhile
    const retry = useRef<number | undefined>(undefined);
    const guessed = useRef(false);

    // Ask who is logged in; the state is set once the answer is there
    const ask = useCallback(async () => {
        await loggingOut.current;
        const asked = generation.current;
        return api.get<Person>('/api/me').then(
            res => {
                if (asked !== generation.current) return;
                setUnreachable(false);
                setPerson(res.data);
                applyLanguage(res.data.language);
                setLoading(false);
            },
            async err => {
                if (asked !== generation.current) return;
                // Only the backend's own 401 means logged out (operations review 2026-11-07): after a restart the login
                // still counts, and nobody should type their PIN again for it
                if (!(axios.isAxiosError(err) && err.response?.status === 401)) {
                    setUnreachable(true);
                    if (!guessed.current) {
                        guessed.current = true;
                        applyLanguage(await guestLanguage());
                    }
                    retry.current = window.setTimeout(() => setRound(r => r + 1), RETRY_MS);
                    return;
                }
                setUnreachable(false);
                setPerson(null);
                applyLanguage(await guestLanguage());
                setLoading(false);
            },
        );
    }, []);

    useEffect(() => {
        void ask();
        return () => window.clearTimeout(retry.current);
    }, [ask, round]);

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

    return <AuthContext.Provider value={{ person, loading, unreachable, reload, logout }}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- the hook belongs with its provider
export function useAuth(): Auth {
    const auth = useContext(AuthContext);
    if (!auth) throw new Error('useAuth outside AuthProvider');
    return auth;
}
