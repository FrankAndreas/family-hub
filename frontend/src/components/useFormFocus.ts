import { useEffect, useRef } from 'react';

// An add/edit form that opens above a long list: bring it into view and put the cursor in its first field. `opened`
// names what the form is for (null: closed), so editing another entry does it again
export function useFormFocus(opened: string | null) {
    const ref = useRef<HTMLFormElement>(null);
    useEffect(() => {
        const form = ref.current;
        if (opened === null || !form) return;
        form.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        form.querySelector<HTMLElement>('input, select')?.focus({ preventScroll: true });
    }, [opened]);
    return ref;
}
