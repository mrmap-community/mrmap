import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
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

export const SystemStatusProvider = ({ children }: { children: ReactNode }) => {
    const { data, error, isPending } = useGetOne<SystemStatusRecord>(
        'SystemStatus', { id: 'current' },
        {
            refetchInterval: query => [401, 403].includes(httpStatus(query.state.error) ?? 0) ? false : 15000,
            refetchIntervalInBackground: true,
            retry: false,
        },
    );
    const [clock, setClock] = useState(Date.now());
    useEffect(() => {
        const timer = window.setInterval(() => setClock(Date.now()), 5000);
        return () => window.clearInterval(timer);
    }, []);

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
