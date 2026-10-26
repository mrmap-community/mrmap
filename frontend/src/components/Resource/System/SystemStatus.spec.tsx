import { useGetOne, useRedirect } from 'react-admin';

import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SystemStatusProvider } from '../../../context/SystemStatusContext';
import SystemStatusIndicator from '../../Layout/SystemStatusIndicator';
import SystemStatus from './SystemStatus';

vi.mock('react-admin', async () => ({
    ...await vi.importActual('react-admin'),
    useGetOne: vi.fn(),
    useRedirect: vi.fn(),
    useCreatePath: () => () => '/SystemInfo',
    useTranslate: () => (key: string) => key,
}));

const snapshot = () => ({
    id: 'current', observedAt: new Date().toISOString(), stale: false, staleAfter: 45,
    components: {
        workers: { status: 'healthy', detail: '2 workers responding' },
        beat: { status: 'healthy', detail: 'Beat scheduler healthcheck passed' },
        redis: { status: 'healthy', detail: 'Reachable' },
        database: { status: 'healthy', detail: 'Reachable' },
    },

});

beforeEach(() => {
    vi.mocked(useGetOne).mockReset();
    vi.mocked(useGetOne, { partial: true }).mockReturnValue({ data: snapshot(), isPending: false });
});
afterEach(() => vi.useRealTimers());

describe('SystemStatus', () => {
    it('shows container health without duplicating periodic tasks', () => {
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        expect(screen.getByText('2 workers responding')).toBeInTheDocument();
        expect(screen.getAllByText('systemStatus.states.healthy')).toHaveLength(4);
        expect(screen.queryByRole('table')).not.toBeInTheDocument();
    });

    it('shows stopped containers as down', () => {
        const data = snapshot();
        data.components.workers = { status: 'down', detail: 'Worker container exited' };
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ data, isPending: false });
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        expect(screen.getByText('systemStatus.states.down')).toBeInTheDocument();
    });

    it('ages previously healthy observations even without a new response', () => {
        vi.useFakeTimers();
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        act(() => vi.advanceTimersByTime(50000));
        expect(screen.queryByText('systemStatus.states.healthy')).not.toBeInTheDocument();
        expect(screen.getByRole('alert')).toHaveTextContent('systemStatus.stale');
        expect(screen.getAllByText('systemStatus.states.unknown')).toHaveLength(4);
    });

    it('does not retain green health indicators after a request fails', () => {
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ data: snapshot(), isPending: false, error: new Error('offline') });
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        expect(screen.queryByText('systemStatus.states.healthy')).not.toBeInTheDocument();
        expect(screen.getByRole('alert')).toHaveTextContent('systemStatus.stale');
    });

    it('hides the staff-only panel on forbidden responses', () => {
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ isPending: false, error: Object.assign(new Error('Forbidden'), { response: { status: 403 } }) });
        const { container } = render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        expect(container).toBeEmptyDOMElement();
    });

    it('reports unavailable monitoring instead of showing an empty healthy panel', () => {
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ isPending: false, error: new Error('offline') });
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        expect(screen.getByRole('alert')).toHaveTextContent('systemStatus.unavailable');
    });
});

describe('global system status', () => {
    const renderIndicator = () => render(<SystemStatusProvider><SystemStatusIndicator /></SystemStatusProvider>);

    it('shares a single query with the details panel and links to SystemInfo', () => {
        const redirect = vi.fn();
        vi.mocked(useRedirect).mockReturnValue(redirect);
        render(<SystemStatusProvider><SystemStatusIndicator /><SystemStatus /></SystemStatusProvider>);
        expect(useGetOne).toHaveBeenCalledTimes(1);
        fireEvent.click(screen.getByRole('button', { name: 'systemStatus.title: systemStatus.states.healthy' }));
        expect(redirect).toHaveBeenCalledWith('/SystemInfo');
    });

    it.each(['down', 'degraded', 'unknown'])('summarizes a %s component', status => {
        const data = snapshot();
        data.components.redis.status = status;
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ data, isPending: false });
        renderIndicator();
        expect(screen.getByRole('button')).toHaveAccessibleName(`systemStatus.title: systemStatus.states.${status}`);
    });

    it('treats missing components as unknown', () => {
        const data = { ...snapshot(), components: {} };
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ data, isPending: false });
        renderIndicator();
        expect(screen.getByRole('button')).toHaveAccessibleName('systemStatus.title: systemStatus.states.unknown');
    });

    it('updates the global indicator when observations expire', () => {
        vi.useFakeTimers();
        renderIndicator();
        act(() => vi.advanceTimersByTime(50000));
        expect(screen.getByRole('button')).toHaveAccessibleName('systemStatus.title: systemStatus.states.unknown');
    });

    it('shows checking while the first request is pending', () => {
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ isPending: true });
        renderIndicator();
        expect(screen.getByRole('button')).toHaveAccessibleName('systemStatus.title: systemStatus.checking');
    });

    it('shows unknown when a request fails despite cached healthy data', () => {
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ data: snapshot(), isPending: false, error: new Error('offline') });
        renderIndicator();
        expect(screen.getByRole('button')).toHaveAccessibleName('systemStatus.title: systemStatus.states.unknown');
    });

    it.each([401, 403])('hides the global indicator for HTTP %s', status => {
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ isPending: false, error: Object.assign(new Error('Forbidden'), { status }) });
        const { container } = renderIndicator();
        expect(container).toBeEmptyDOMElement();
    });
});

describe('system status polling', () => {
    const refetch = vi.fn();

    type PollingOptions = {
        refetchInterval: (query: { state: { error: unknown } }) => number | false,
        refetchIntervalInBackground: boolean,
    };

    // The options the provider last handed to the query are what an instance of
    // MrMap would poll with; the query itself is react-admin's.
    const pollingOptions = () => vi.mocked(useGetOne).mock.calls.at(-1)?.[2] as unknown as PollingOptions;
    const interval = (error: unknown = null) => pollingOptions().refetchInterval({ state: { error } });

    /** Pretends the user left or returned, the way a browser tells the page about it. */
    const setPageActive = (active: boolean, reason: 'visibilitychange' | 'focus' = 'visibilitychange') => {
        vi.spyOn(document, 'visibilityState', 'get').mockReturnValue(active ? 'visible' : 'hidden');
        vi.spyOn(document, 'hasFocus').mockReturnValue(active);
        act(() => {
            if (reason === 'visibilitychange') document.dispatchEvent(new Event('visibilitychange'));
            else window.dispatchEvent(new Event(active ? 'focus' : 'blur'));
        });
    };

    beforeEach(() => {
        refetch.mockClear();
        vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
        vi.spyOn(document, 'hasFocus').mockReturnValue(true);
        vi.mocked(useGetOne, { partial: true })
            .mockReturnValue({ data: snapshot(), isPending: false, refetch });
    });
    afterEach(() => vi.restoreAllMocks());

    it('polls while the page is visible and focused', () => {
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        expect(interval()).toBe(15000);
        expect(pollingOptions().refetchIntervalInBackground).toBe(false);
        expect(refetch).not.toHaveBeenCalled();
    });

    it('pauses while the tab is hidden', () => {
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        setPageActive(false);
        expect(interval()).toBe(false);
        expect(refetch).not.toHaveBeenCalled();
    });

    it('pauses while the window is unfocused', () => {
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        setPageActive(false, 'focus');
        expect(interval()).toBe(false);
    });

    it('resumes and refreshes the status when the tab becomes visible again', () => {
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        setPageActive(false);
        setPageActive(true);
        expect(refetch).toHaveBeenCalledTimes(1);
        expect(interval()).toBe(15000);
    });

    it('resumes and refreshes the status when the window regains focus', () => {
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        setPageActive(false, 'focus');
        setPageActive(true, 'focus');
        expect(refetch).toHaveBeenCalledTimes(1);
        expect(interval()).toBe(15000);
    });

    it('does not request anything while it stays active', () => {
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        setPageActive(true);
        setPageActive(true);
        expect(refetch).not.toHaveBeenCalled();
    });

    it.each([401, 403])('keeps polling stopped after HTTP %s also when the page is active', status => {
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        const error = Object.assign(new Error('Forbidden'), { response: { status } });
        setPageActive(false);
        setPageActive(true);
        expect(interval(error)).toBe(false);
    });

    it('does not poll a page which was already hidden when the panel was mounted', () => {
        vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
        render(<SystemStatusProvider><SystemStatus /></SystemStatusProvider>);
        expect(interval()).toBe(false);
        expect(refetch).not.toHaveBeenCalled();
    });
});
