import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useAuthState, useCanAccess, useGetOne, type RaRecord } from 'react-admin';

interface Observation {
    status: string;
    detail: string;
    last_seen?: string | null;
}

export interface SystemStatusRecord extends RaRecord {
    observedAt: string | null;
    stale: boolean;
    staleAfter: number;
    /** The observation per component; what a deployment could not observe is
     * absent from the answer instead of carrying an observation of its own. */
    components: Partial<Record<string, Observation>>;
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

/**
 * Whether an answer of the read is an observation.
 *
 * `GET /api/system/status/current` is `IsAdminUser` (#1445), and a refusal
 * which keeps the session does not reach this provider as an error: react-admin's
 * data provider answers it with an EMPTY RECORD instead, because its
 * `checkError` rejected without logging the caller out (#834's contract). Such
 * a record carries no component and no observation time, so anything reading
 * it must say "unavailable" rather than index into it (#1805).
 */
export const hasObservation = (record: SystemStatusRecord | undefined):
    record is SystemStatusRecord => record?.components !== undefined;

export const SystemStatusProvider = ({ children }: { children: ReactNode }) => {
    // #833: the system status is an operator view - an anonymous visitor of a
    // published service must not fire this read at all, because its 401 would
    // run the authProvider's checkError and log out a visitor who never
    // logged in; without a session the status simply reads forbidden.
    const { authenticated } = useAuthState();
    // #1805: one step further for the same reason. `GET /api/system/status/
    // current` answers `IsAdminUser`, so every persona of the shipped role
    // catalogue except a superuser used to pay a 403 for the indicator: the
    // authProvider's checkError keeps the session for a refused action but
    // rejects, and react-admin's data provider answers that refusal with an
    // EMPTY RECORD instead of an error - which the context then read as an
    // observation, threw on the missing components, and the error boundary of
    // the layout replaced the whole application. The read is therefore gated
    // on the very check which gates the screen these observations belong to
    // (#836's table behind `canAccess`): what the deployment refuses is never
    // asked, and the answer of the table is the degradation below.
    const { canAccess: mayRead, isPending: accessIsPending } = useCanAccess({
        resource: 'SystemInfo',
        action: 'list',
    });
    const readable = !accessIsPending && mayRead === true;
    const { data, error, isPending } = useGetOne<SystemStatusRecord>(
        'SystemStatus', { id: 'current' },
        {
            enabled: !!authenticated && readable,
            // TanStack Query pauses polling in hidden tabs and refreshes stale data on return.
            refetchInterval: query => [401, 403].includes(httpStatus(query.state.error) ?? 0)
                // the empty record of a swallowed refusal never becomes an
                // observation, so polling it again would only repeat the 403
                || (query.state.data !== undefined && !hasObservation(query.state.data))
                ? false : POLLING_INTERVAL,
            refetchIntervalInBackground: false,
            retry: false,
        },
    );
    const [clock, setClock] = useState(Date.now());
    useEffect(() => {
        const timer = window.setInterval(() => setClock(Date.now()), 5000);
        return () => window.clearInterval(timer);
    }, []);
    // the refused caller - anonymous, or signed in without the operator's
    // answer of the table - never fired the read; a 401 or 403 which still
    // arrives (a revoked role the cached table does not know yet) stays here
    // and reads the same: a grey indicator, page intact. A check which has
    // not answered yet is not a refusal: the readers show their checking
    // state until it has.
    const refused = !accessIsPending && mayRead !== true;
    const forbidden = !authenticated || refused || [401, 403].includes(httpStatus(error) ?? 0);
    const observedAt = Date.parse(data?.observedAt ?? '');
    const stale = !!error || !data || data.stale || !Number.isFinite(observedAt) ||
        !Number.isFinite(data.staleAfter) || clock - observedAt > data.staleAfter * 1000;
    // a swallowed refusal answers a record without any observation: missing
    // states read unknown, never crash the provider above the layout
    const states = systemComponents.map(name => data?.components?.[name]?.status);
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
