import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Logout from './pages/Logout';
import ResetPin from './pages/ResetPin';
import ConfirmEmail from './pages/ConfirmEmail';
import Settings from './pages/Settings';
import Start from './pages/Start';

function Pages() {
    const { person, loading } = useAuth();
    if (loading) return null;
    if (!person) return <Login />;
    return (
        <Layout>
            <Routes>
                <Route path="/" element={<Start />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </Layout>
    );
}

// Not logged in: the login screen at any address (it keeps ?next= for the app that sent the person here)
export default function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <Routes>
                    {/* Logged in or not: the apps' "Log out", and the link from the "Forgot PIN" mail */}
                    <Route path="/logout" element={<Logout />} />
                    <Route path="/reset-pin" element={<ResetPin />} />
                    <Route path="/confirm-email" element={<ConfirmEmail />} />
                    <Route path="*" element={<Pages />} />
                </Routes>
            </AuthProvider>
        </BrowserRouter>
    );
}
