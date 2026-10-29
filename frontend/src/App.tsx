import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import Layout from './components/Layout';
import Login from './pages/Login';
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
                <Pages />
            </AuthProvider>
        </BrowserRouter>
    );
}
