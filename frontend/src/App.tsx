import { useTranslation } from 'react-i18next';

// The start page and the family login (Task 7 fills it in)
export default function App() {
    const { t } = useTranslation();
    return <h1 className="p-4 text-2xl font-semibold">{t('app.title')}</h1>;
}
