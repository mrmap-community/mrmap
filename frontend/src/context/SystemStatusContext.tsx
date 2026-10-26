import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { useGetOne, type RaRecord } from 'react-admin';

interface Observation {
    status: string;
    detail: string;
    last_seen?: string | null;
}

export interface SystemStatusRecord extends RaRecord {
    observedAt: string | null;
    stale: boolean;
    staleAfter: number;
    components: Record<string, Observation>;
}

export const systemComponents = ['workers', 'beat', 'redis', 'database'] as const;
type Health = 'healthy' | 'down' | 'degraded' | 'unknown';

interface SystemStatusContextValue {
    data?: SystemStatusRecord;
    isPending: boolean;
    forbidden: boolean;
    stale: boolean;
    health: Health;
}

const SystemStatusContext = createContext<SystemStatusContextValue | undefined>(undefined);
const httpStatus = (error: unknown) => {
    const value = error as { response?: { status?: number }; status?: number } | null;
    return value?.response?.status ?? value?.status;
};

const POLLING_INTERVAL = 15000;

/** The page is worth polling while the user can see it. */
const isPageActive = () => document.visibilityState === 'visible' && document.hasFocus();

const usePageActive = () => {
    const [active, setActive] = useState(isPageActive);
    useEffect(() => {
        const update = () => setActive(isPageActive());
        document.addEventListener('visibilitychange', update);
        window.addEventListener('focus', update);
        window.addEventListener('blur', update);
        // The page may have been hidden or unfocused while this component was not mounted.
        update();
        return () => {
            document.removeEventListener('visibilitychange', update);
            window.removeEventListener('focus', update);
            window.removeEventListener('blur', update);
        };
    }, []);
    return active;
};

export const SystemStatusProvider = ({ children }: { children: ReactNode }) => {
    const active = usePageActive();
    const { data, error, isPending, refetch } = useGetOne<SystemStatusRecord>(
        'SystemStatus', { id: 'current' },
        {
            // Polling stops while the tab is hidden or the window is unfocused (#749) and
            // stops altogether on a response which says the user may not read the status.
            refetchInterval: query => !active ||
                [401, 403].includes(httpStatus(query.state.error) ?? 0) ? false : POLLING_INTERVAL,
            refetchIntervalInBackground: false,
            retry: false,
        },
    );
    const [clock, setClock] = useState(Date.now());
    useEffect(() => {
        const timer = window.setInterval(() => setClock(Date.now()), 5000);
        return () => window.clearInterval(timer);
    }, []);
    // The observations which are on screen are refreshed as soon as the user returns; the
    // interval which was paused in the meantime would only deliver them one tick later.
    const wasActive = useRef(active);
    useEffect(() => {
        if (active && !wasActive.current) void refetch?.();
        wasActive.current = active;
    }, [active, refetch]);

    const forbidden = [401, 403].includes(httpStatus(error) ?? 0);
    const observedAt = Date.parse(data?.observedAt ?? '');
    const stale = !!error || !data || data.stale || !Number.isFinite(observedAt) ||
        !Number.isFinite(data.staleAfter) || clock - observedAt > data.staleAfter * 1000;
    const states = systemComponents.map(name => data?.components[name]?.status);
    const health: Health = stale ? 'unknown'
        : states.includes('down') ? 'down'
        : states.includes('degraded') ? 'degraded'
        : states.every(status => status === 'healthy') ? 'healthy' : 'unknown';

    return (
        <SystemStatusContext.Provider value={{ data, isPending, forbidden, stale, health }}>
            {children}
        </SystemStatusContext.Provider>
    );
};

export const useSystemStatus = () => {
    const context = useContext(SystemStatusContext);
    if (!context) throw new Error('useSystemStatus must be used inside SystemStatusProvider');
    return context;
};
