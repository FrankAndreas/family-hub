import type { Language } from './i18n';

export type { Language };
export type Role = 'PARENT' | 'CHILD';

export interface Person {
    id: number;
    name: string;
    email: string | null;
    // Entered, waiting until the link mailed to it is opened; only then it counts
    email_pending: string | null;
    role: Role;
    active: boolean;
    color: string | null;
    language: Language;
    language_chosen: boolean;
    // Managing people, PINs and apps happens at home only
    at_home: boolean;
    // In the parents' list: whether the parent asking may change this person (not another parent)
    can_edit: boolean;
}

// On the start page: the address for where one is (home or outside)
export interface Tile { id: number; name: string; icon: string; url: string; home_only: boolean }

// For parents editing: both addresses
export interface TileFull {
    id: number; name: string; icon: string; local_url: string; remote_url: string | null; position: number;
    // Apps that use the family login: their key, and the ids of the people who may use them
    app_key: string | null; people: number[];
    // The app may see its people's confirmed e-mail addresses
    share_email: boolean;
    // The AUD tag of the app's Cloudflare Access application: its Cloudflare logins count only for it
    cf_audience: string | null;
    // Who used the app under its current key, and when (UTC, ISO)
    usage: { person_id: number; first_used_at: string; last_used_at: string }[];
    // The other parents who used it: only they can untick themselves; meanwhile its key stays and it can't be deleted
    locked_people: number[];
}
