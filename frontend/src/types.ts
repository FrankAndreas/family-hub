export type Role = 'PARENT' | 'CHILD';

export interface Person {
    id: number;
    name: string;
    email: string | null;
    role: Role;
    active: boolean;
    color: string | null;
    language: 'de' | 'en';
    language_chosen: boolean;
    // Managing people, PINs and apps happens at home only
    at_home: boolean;
}

// On the start page: the address for where one is (home or outside)
export interface Tile { id: number; name: string; icon: string; url: string; home_only: boolean }

// For parents editing: both addresses
export interface TileFull { id: number; name: string; icon: string; local_url: string; remote_url: string | null; position: number }
