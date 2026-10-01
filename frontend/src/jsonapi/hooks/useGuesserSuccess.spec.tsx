import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import useGuesserSuccess from './useGuesserSuccess';

const mocks = vi.hoisted(() => ({ notify: vi.fn(), redirect: vi.fn(), getErrors: vi.fn((): unknown[] => []) }));
vi.mock('react-admin', () => ({
  useNotify: () => mocks.notify,
  useRedirect: () => mocks.redirect,
  useTranslate: () => (key: string) => key,
}));
vi.mock('../components/ReferenceManyErrorsProvider', () => ({ useReferenceManyErrors: () => ({ getErrors: mocks.getErrors }) }));
beforeEach(() => { vi.clearAllMocks(); mocks.getErrors.mockReturnValue([]); });
describe('useGuesserSuccess', () => {
  it('notifies creation and uses the current redirect after rerender', () => {
    const { result, rerender } = renderHook(({ resource, redirectTo }) => useGuesserSuccess({ resource, redirectTo, action: 'created', undoable: false }), { initialProps: { resource: 'Service', redirectTo: 'list' } });
    rerender({ resource: 'Other', redirectTo: 'show' });
    result.current({ id: 1 });
    expect(mocks.notify).toHaveBeenCalledWith('resources.Other.notifications.created', expect.objectContaining({ type: 'info' }));
    expect(mocks.redirect).toHaveBeenCalledWith('show', 'Other', 1, { id: 1 });
  });
  it('redirects partial successes to edit with relationship errors', () => {
    const errors = [{ source: 'probes' }];
    mocks.getErrors.mockReturnValue(errors);
    const { result } = renderHook(() => useGuesserSuccess({ resource: 'Service', action: 'update', undoable: true }));
    result.current({ id: 2 });
    expect(mocks.notify).toHaveBeenCalledWith('resources.Service.notifications.updated_with_errors', expect.objectContaining({ type: 'warning', undoable: true }));
    expect(mocks.redirect).toHaveBeenCalledWith('edit', 'Service', 2, undefined, { referenceManyErrors: errors });
  });
});
