import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { logoutStep } from '../next';

// /logout?next=<app>: the apps' "Log out" ends the login here, for the hub and every app, then shows the login.
// Outside the login is Cloudflare Access's, so it waits to learn where the person is
export default function Logout() {
    const { person, loading, logout } = useAuth();
    const navigate = useNavigate();
    const [params] = useSearchParams();
    const next = params.get('next');

    useEffect(() => {
        if (loading) return;
        const step = logoutStep(person, next);
        if ('leave' in step) window.location.href = step.leave;
        else void logout().finally(() => navigate(step.hub, { replace: true }));
        // Once: logging out clears the person, which must not run it again
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [loading]);

    return null;
}
