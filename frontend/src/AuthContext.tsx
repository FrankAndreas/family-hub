import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
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

    // Ask who is logged in; the state is set once the answer is there
    const ask = useCallback(() => api.get<Person>('/api/me').then(
        res => {
            setPerson(res.data);
            applyLanguage(res.data.language);
        },
        async () => {
            setPerson(null);
            applyLanguage(await guestLanguage());
        },
    ).finally(() => setLoading(false)), []);

    useEffect(() => {
        void ask();
    }, [ask]);

    const reload = useCallback(async () => {
        await ask();
    }, [ask]);

    const logout = useCallback(async () => {
        await api.post('/api/logout');
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
