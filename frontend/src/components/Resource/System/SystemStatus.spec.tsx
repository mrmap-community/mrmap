import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useGetOne } from 'react-admin';
import SystemStatus from './SystemStatus';

vi.mock('react-admin', async () => ({
    ...await vi.importActual('react-admin'),
    useGetOne: vi.fn(),
    useTranslate: () => (key: string) => key,
}));

const snapshot = () => ({
    id: 'current', observedAt: new Date().toISOString(), stale: false, staleAfter: 45,
    components: {
        workers: { status: 'healthy', detail: '2 workers responding' },
        beat: { status: 'connected', detail: 'Beat connected to PostgreSQL (1 sessions)' },
        redis: { status: 'healthy', detail: 'Reachable' },
        database: { status: 'healthy', detail: 'Reachable' },
    },
    tasks: [{ id: 'Refresh views', name: 'Refresh views', status: 'overdue', detail: 'Expected dispatch is missing' }],
    tasksAvailable: true, taskTotal: 1, taskCounts: { overdue: 1 },
});

beforeEach(() => {
    vi.mocked(useGetOne).mockReset();
    vi.mocked(useGetOne, { partial: true }).mockReturnValue({ data: snapshot(), isPending: false });
});
afterEach(() => vi.useRealTimers());

describe('SystemStatus', () => {
    it('shows responding services separately from overdue periodic schedules', () => {
        render(<SystemStatus />);
        expect(screen.getByText('2 workers responding')).toBeInTheDocument();
        expect(screen.getByText('Refresh views')).toBeInTheDocument();
        expect(screen.getByText('Expected dispatch is missing')).toBeInTheDocument();
        expect(screen.getAllByText('systemStatus.states.healthy')).toHaveLength(3);
        expect(screen.getByText('systemStatus.states.connected')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'systemStatus.flower' })).toHaveAttribute('href', '/flower/');
    });

    it('shows a connected idle Beat without periodic tasks', () => {
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ data: { ...snapshot(), tasks: [], taskCounts: {}, taskTotal: 0 }, isPending: false });
        render(<SystemStatus />);
        expect(screen.getByText('systemStatus.states.connected')).toBeInTheDocument();
    });

    it('ages previously healthy observations even without a new response', () => {
        vi.useFakeTimers();
        render(<SystemStatus />);
        act(() => vi.advanceTimersByTime(50000));
        expect(screen.queryByText('systemStatus.states.healthy')).not.toBeInTheDocument();
        expect(screen.queryByText('systemStatus.states.connected')).not.toBeInTheDocument();
        expect(screen.getByRole('alert')).toHaveTextContent('systemStatus.stale');
        expect(screen.getAllByText('systemStatus.states.unknown')).toHaveLength(5);
    });

    it('does not retain green health indicators after a request fails', () => {
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ data: snapshot(), isPending: false, error: new Error('offline') });
        render(<SystemStatus />);
        expect(screen.queryByText('systemStatus.states.healthy')).not.toBeInTheDocument();
        expect(screen.queryByText('systemStatus.states.connected')).not.toBeInTheDocument();
        expect(screen.getByRole('alert')).toHaveTextContent('systemStatus.stale');
    });

    it('hides the staff-only panel on forbidden responses', () => {
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ isPending: false, error: Object.assign(new Error('Forbidden'), { response: { status: 403 } }) });
        const { container } = render(<SystemStatus />);
        expect(container).toBeEmptyDOMElement();
    });

    it('reports unavailable monitoring instead of showing an empty healthy panel', () => {
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ isPending: false, error: new Error('offline') });
        render(<SystemStatus />);
        expect(screen.getByRole('alert')).toHaveTextContent('systemStatus.unavailable');
    });
});
