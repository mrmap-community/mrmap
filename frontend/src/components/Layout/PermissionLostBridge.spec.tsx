/**
 * The bridge of #834: when the server refuses an action of a still-valid
 * session - the `permission_denied` answer of the auth contract - the cached
 * access answers and the open screens must revalidate at once. The spec fires
 * the real provider's `checkError` so it pins the seam itself, not a mocked
 * event.
 */
import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import tokenAuthProvider, { setAuthToken } from '../../providers/authProvider';
import PermissionLostBridge from './PermissionLostBridge';

const mocks = vi.hoisted(() => ({
  invalidateQueries: vi.fn(),
  refresh: vi.fn(),
}));

// the two hooks the bridge acts through, asserted by their call signatures
vi.mock('react-admin', () => ({ useRefresh: () => mocks.refresh }));
vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}));
vi.mock('../../context/HttpClientContext', () => ({ API_BASE_URL: 'https://mrmap.test' }));

/** The JSON:API error body of a refused action, as the fetch layer hands it on. */
const REFUSAL = { status: 403, message: 'no', body: { errors: [{ code: 'permission_denied' }] } };

/** The refusal of a live session, as a dataProvider error reaches the app. */
const refuseAction = async () => {
  await tokenAuthProvider().checkError?.(REFUSAL).catch(() => undefined);
};

beforeEach(() => {
  localStorage.clear();
  setAuthToken({
    token: 'a-live-knox-token',
    expiry: new Date(Date.now() + 60_000).toISOString(),
    id: 1,
    fullName: 'Ada Lovelace',
  });
  mocks.invalidateQueries.mockClear();
  mocks.refresh.mockClear();
});

afterEach(() => {
  localStorage.clear();
});

describe('PermissionLostBridge', () => {
  it('drops the cached access answers and refreshes the screens on a refusal', async () => {
    render(<PermissionLostBridge />);

    await refuseAction();

    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['canAccess'] });
    expect(mocks.refresh).toHaveBeenCalled();
  });

  it('stops listening when unmounted', async () => {
    const { unmount } = render(<PermissionLostBridge />);
    unmount();

    await refuseAction();

    expect(mocks.invalidateQueries).not.toHaveBeenCalled();
    expect(mocks.refresh).not.toHaveBeenCalled();
  });
});
