import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { INPUT } from '../ui';

interface PinInputProps {
    id: string;
    value: string;
    onChange: (pin: string) => void;
    autoComplete?: 'current-password' | 'new-password';
    autoFocus?: boolean;
}

// Masked 4-digit PIN field with a show/hide toggle; only accepts digits
export default function PinInput({
    id,
    value,
    onChange,
    autoComplete = 'current-password',
    autoFocus = false,
}: PinInputProps) {
    const { t } = useTranslation();
    const [show, setShow] = useState(false);
    return (
        <div className="relative">
            <input
                id={id}
                type={show ? 'text' : 'password'}
                inputMode="numeric"
                autoComplete={autoComplete}
                autoFocus={autoFocus}
                maxLength={4}
                value={value}
                onChange={(e) => {
                    if (/^\d*$/.test(e.target.value)) onChange(e.target.value);
                }}
                placeholder={t('login.pin')}
                className={`${INPUT} pr-12 tracking-widest placeholder:tracking-normal`}
            />
            <button
                type="button"
                onClick={() => setShow(!show)}
                aria-label={show ? t('login.hidePin') : t('login.showPin')}
                className="absolute inset-y-0 right-0 px-3 text-slate-400 hover:text-white"
            >
                {show ? '🙈' : '👁️'}
            </button>
        </div>
    );
}
