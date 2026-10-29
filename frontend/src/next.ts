// Where to go after logging in: an app sends people to the hub with ?next=<its address>. Only an address of an app on
// the start page counts, so the login can't be used to send anyone elsewhere.
export function safeNext(next: string | null, tileUrls: string[]): string | null {
    if (!next) return null;
    let target: URL;
    try {
        target = new URL(next);
    } catch {
        return null;
    }
    const known = tileUrls.some(url => {
        try {
            return new URL(url).origin === target.origin;
        } catch {
            return false;
        }
    });
    return known ? target.href : null;
}
