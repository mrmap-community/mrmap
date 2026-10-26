import { AdminContext, testDataProvider, useGetOne, useRedirect } from 'react-admin';

import { focusManager, QueryClient } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
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
    const getOne = vi.fn();
    let queryClient: QueryClient;

    const renderProvider = async () => {
        await act(async () => {
            render(
                <AdminContext dataProvider={testDataProvider({ getOne })} queryClient={queryClient}>
                    <SystemStatusProvider>{null}</SystemStatusProvider>
                </AdminContext>,
            );
        });
    };

    const setTabVisible = async (visible: boolean) => {
        vi.spyOn(document, 'visibilityState', 'get').mockReturnValue(visible ? 'visible' : 'hidden');
        await act(async () => window.dispatchEvent(new Event('visibilitychange')));
    };

    const advanceTime = async (milliseconds: number) => {
        await act(async () => vi.advanceTimersByTimeAsync(milliseconds));
    };

    beforeEach(async () => {
        const actual = await vi.importActual<typeof import('react-admin')>('react-admin');
        vi.mocked(useGetOne).mockImplementation(actual.useGetOne);
        vi.useFakeTimers();
        vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
        focusManager.setFocused(undefined);
        getOne.mockReset();
        getOne.mockResolvedValue({ data: snapshot() });
        queryClient = new QueryClient();
    });
    afterEach(() => {
        cleanup();
        queryClient.clear();
        vi.restoreAllMocks();
        focusManager.setFocused(undefined);
    });

    it('polls every 15 seconds while the tab is visible', async () => {
        await renderProvider();
        expect(getOne).toHaveBeenCalledTimes(1);
        await advanceTime(15000);
        expect(getOne).toHaveBeenCalledTimes(2);
    });

    it('pauses while the tab is hidden', async () => {
        await renderProvider();
        await setTabVisible(false);
        await advanceTime(30000);
        expect(getOne).toHaveBeenCalledTimes(1);
    });

    it('keeps polling a visible tab when the window loses focus', async () => {
        await renderProvider();
        vi.spyOn(document, 'hasFocus').mockReturnValue(false);
        fireEvent.blur(window);
        await advanceTime(15000);
        expect(getOne).toHaveBeenCalledTimes(2);
    });

    it('refreshes immediately and resumes polling when the tab becomes visible', async () => {
        await renderProvider();
        await setTabVisible(false);
        await advanceTime(30000);
        await setTabVisible(true);
        expect(getOne).toHaveBeenCalledTimes(2);
        await advanceTime(15000);
        expect(getOne).toHaveBeenCalledTimes(3);
    });

    it('does not refetch when the visible window regains focus', async () => {
        await renderProvider();
        fireEvent.blur(window);
        fireEvent.focus(window);
        await advanceTime(0);
        expect(getOne).toHaveBeenCalledTimes(1);
    });

    it.each([401, 403])('stops polling after HTTP %s', async status => {
        getOne.mockRejectedValue(Object.assign(new Error('Forbidden'), { response: { status } }));
        await renderProvider();
        await advanceTime(30000);
        expect(getOne).toHaveBeenCalledTimes(1);
    });

    it('does not poll after the initial request when mounted in a hidden tab', async () => {
        vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
        await renderProvider();
        await advanceTime(30000);
        expect(getOne).toHaveBeenCalledTimes(1);
    });
});
