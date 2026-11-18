import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useAuthState, useGetOne, type RaRecord } from 'react-admin';

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

export const SystemStatusProvider = ({ children }: { children: ReactNode }) => {
    // #833: the system status is an operator view - an anonymous visitor of a
    // published service must not fire this read at all, because its 401 would
    // run the authProvider's checkError and log out a visitor who never
    // logged in; without a session the status simply reads forbidden.
    const { authenticated } = useAuthState();
    const { data, error, isPending } = useGetOne<SystemStatusRecord>(
        'SystemStatus', { id: 'current' },
        {
            enabled: !!authenticated,
            // TanStack Query pauses polling in hidden tabs and refreshes stale data on return.
            refetchInterval: query => [401, 403].includes(httpStatus(query.state.error) ?? 0) ? false : POLLING_INTERVAL,
            refetchIntervalInBackground: false,
            retry: false,
        },
    );
    const [clock, setClock] = useState(Date.now());
    useEffect(() => {
        const timer = window.setInterval(() => setClock(Date.now()), 5000);
        return () => window.clearInterval(timer);
    }, []);
    const forbidden = !authenticated || [401, 403].includes(httpStatus(error) ?? 0);
    const observedAt = Date.parse(data?.observedAt ?? '');
    const stale = !!error || !data || data.stale || !Number.isFinite(observedAt) ||
        !Number.isFinite(data.staleAfter) || clock - observedAt > data.staleAfter * 1000;
    const states = systemComponents.map(name => data?.components[name]?.status);
    let health: Health = 'unknown';
    if (!stale) {
        if (states.includes('down')) health = 'down';
        else if (states.includes('degraded')) health = 'degraded';
        else if (states.every(status => status === 'healthy')) health = 'healthy';
    }

    const value = useMemo(
        () => ({ data, isPending, forbidden, stale, health }),
        [data, isPending, forbidden, stale, health],
    );

    return (
        <SystemStatusContext.Provider value={value}>
            {children}
        </SystemStatusContext.Provider>
    );
};

export const useSystemStatus = () => {
    const context = useContext(SystemStatusContext);
    if (!context) throw new Error('useSystemStatus must be used inside SystemStatusProvider');
    return context;
};
