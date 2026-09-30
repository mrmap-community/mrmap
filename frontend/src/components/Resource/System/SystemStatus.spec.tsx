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
        render(<SystemStatus />);
        expect(screen.getByText('2 workers responding')).toBeInTheDocument();
        expect(screen.getAllByText('systemStatus.states.healthy')).toHaveLength(4);
        expect(screen.queryByRole('table')).not.toBeInTheDocument();
    });

    it('shows stopped containers as down', () => {
        const data = snapshot();
        data.components.workers = { status: 'down', detail: 'Worker container exited' };
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ data, isPending: false });
        render(<SystemStatus />);
        expect(screen.getByText('systemStatus.states.down')).toBeInTheDocument();
    });

    it('ages previously healthy observations even without a new response', () => {
        vi.useFakeTimers();
        render(<SystemStatus />);
        act(() => vi.advanceTimersByTime(50000));
        expect(screen.queryByText('systemStatus.states.healthy')).not.toBeInTheDocument();
        expect(screen.getByRole('alert')).toHaveTextContent('systemStatus.stale');
        expect(screen.getAllByText('systemStatus.states.unknown')).toHaveLength(4);
    });

    it('does not retain green health indicators after a request fails', () => {
        vi.mocked(useGetOne, { partial: true }).mockReturnValue({ data: snapshot(), isPending: false, error: new Error('offline') });
        render(<SystemStatus />);
        expect(screen.queryByText('systemStatus.states.healthy')).not.toBeInTheDocument();
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
