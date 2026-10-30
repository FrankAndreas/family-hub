import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { logoutTarget } from '../next';

// /logout?next=<app>: the apps' "Log out" ends the login here, for the hub and every app, then shows the login
export default function Logout() {
    const { logout } = useAuth();
    const navigate = useNavigate();
    const [params] = useSearchParams();
    const next = params.get('next');

    useEffect(() => {
        void logout().finally(() => navigate(logoutTarget(next), { replace: true }));
    }, [logout, navigate, next]);

    return null;
}
