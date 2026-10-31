// Where to go after logging in: an app sends people to the hub with ?next=<its address>. Only an address of an app on
// the start page counts, and only under the hub's own domain (home.local.<domain> takes *.local.<domain>): a parent
// could add a tile for a site of their own and send the other parent there to "log in again" (security review
// 2026-10-30). On a machine name without dots (localhost) only that machine counts.
export function safeNext(next: string | null, tileUrls: string[], hubHost: string = window.location.hostname): string | null {
    if (!next) return null;
    let target: URL;
    try {
        target = new URL(next);
    } catch {
        return null;
    }
    const labels = hubHost.split('.');
    const family = labels.length >= 3 ? labels.slice(1).join('.') : null;
    const ours = target.hostname === hubHost || (family !== null && target.hostname.endsWith(`.${family}`));
    const known = tileUrls.some(url => {
        try {
            return new URL(url).origin === target.origin;
        } catch {
            return false;
        }
    });
    return ours && known ? target.href : null;
}

// After "Log out" (an app sends people to /logout?next=<its address>): the login, keeping the app to go back to
export function logoutTarget(next: string | null): string {
    return next ? `/?next=${encodeURIComponent(next)}` : '/';
}

// Where "Log out" goes: at home the hub ends its own login (its API); outside the login is Cloudflare Access's, which
// its logout address ends
export function logoutAddress(atHome: boolean): string | null {
    return atHome ? null : '/cdn-cgi/access/logout';
}

// What /logout?next=<app> does once it knows who is logged in: outside it ends the Cloudflare Access login (an app's
// "Log out" may send people here from outside too; security review 2026-10-31), at home the hub's own login
export function logoutStep(person: { at_home: boolean } | null, next: string | null): { leave: string } | { hub: string } {
    const outside = person ? logoutAddress(person.at_home) : null;
    return outside ? { leave: outside } : { hub: logoutTarget(next) };
}
