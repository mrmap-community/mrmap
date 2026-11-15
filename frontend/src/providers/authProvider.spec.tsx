/**
 * Pins the logout contract of #832: the credential is revoked at the backend
 * before the local copy disappears, and a logout which the backend cannot
 * answer still ends the local session.
 *
 * The first three tests call the provider directly - revocation, offline
 * tolerance and the absence of a request without a stored token are properties
 * of the provider alone. The last one runs the provider through react-admin's
 * `useLogout`, because "lands on /login" is that hook's business: it navigates
 * to the login page when `authProvider.logout()` resolves and does nothing when
 * it rejects. A logout which throws would therefore keep the user on the page
 * they wanted to leave with a token the local state no longer carries.
 *
 * The `canAccess` suite at the bottom pins #836 on top of it: resource checks
 * answer from one permission snapshot per login instead of a per-render
 * network call, every way this file knows to end or invalidate the session
 * drops that snapshot, and react-admin's own route guard uses the answers to
 * turn a deep link into its standard access-denied state.
 */
import { AdminContext, TestMemoryRouter, useLogout, useRequireAccess } from 'react-admin';
import type { DataProvider } from 'react-admin';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import tokenAuthProvider, { AUTH_TOKEN_LOCAL_STORAGE_NAME, getAuthToken, setAuthToken } from './authProvider';

vi.mock('../context/HttpClientContext', () => ({ API_BASE_URL: 'https://mrmap.test' }));

const LOGOUT_URL = 'https://mrmap.test/api/auth/logout';
const TOKEN = 'a-copied-knox-token';

/** The provider as the application builds it, with the mocked API base URL. */
const authProvider = tokenAuthProvider();

/** A token as the login stored it: knox' expiry plus the identity of #727. */
const storeToken = () => setAuthToken({
  token: TOKEN,
  expiry: new Date(Date.now() + 60_000).toISOString(),
  id: 1,
  fullName: 'Ada Lovelace',
});

const storedToken = () => localStorage.getItem(AUTH_TOKEN_LOCAL_STORAGE_NAME);

/** Answers the logout request; rejects it when an error is given. */
const mockFetch = (error?: Error, status = 204) => {
  const fetchMock = error
    ? vi.fn().mockRejectedValue(error)
    : vi.fn().mockResolvedValue(new Response(null, { status }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
};

beforeEach(() => {
  localStorage.clear();
  storeToken();
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('authProvider.logout', () => {
  it('revokes the stored token at the backend before dropping it locally', async () => {
    const fetchMock = mockFetch();

    await authProvider.logout?.({});

    const [[request]] = fetchMock.mock.calls;
    expect(request).toBeInstanceOf(Request);
    expect(request.url).toBe(LOGOUT_URL);
    expect(request.method).toBe('POST');
    expect(request.headers.get('authorization')).toBe(`Token ${TOKEN}`);
    expect(storedToken()).toBeNull();
  });

  it('ends the local session when the backend cannot be reached', async () => {
    mockFetch(new Error('offline'));

    await expect(authProvider.logout?.({})).resolves.toBeUndefined();

    expect(storedToken()).toBeNull();
  });

  it('ends the local session when the backend refuses the request', async () => {
    mockFetch(undefined, 500);

    await expect(authProvider.logout?.({})).resolves.toBeUndefined();

    expect(storedToken()).toBeNull();
  });

  it('asks nothing when no token is stored', async () => {
    const fetchMock = mockFetch();
    setAuthToken(undefined);

    await authProvider.logout?.({});

    expect(fetchMock).not.toHaveBeenCalled();
    expect(storedToken()).toBeNull();
  });
});

describe('logout through react-admin', () => {
  const LogoutTrigger = () => {
    const logout = useLogout();
    return <button onClick={() => { void logout(); }}>log out</button>;
  };

  it('lands on /login although the revocation request failed', async () => {
    mockFetch(new Error('offline'));
    let pathname = '/';
    render(
      <TestMemoryRouter
        initialEntries={['/resources/WMS/1']}
        locationCallback={(location) => { pathname = location.pathname; }}
      >
        <AdminContext authProvider={authProvider} dataProvider={{} as DataProvider}>
          <LogoutTrigger />
        </AdminContext>
      </TestMemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: /log out/i }));

    await waitFor(() => expect(pathname).toBe('/login'));
    expect(storedToken()).toBeNull();
  });
});

/**
 * The #836 contract, judged against the provider as the app builds it:
 * canAccess answers from one snapshot fetched per login - never per
 * render - resets it whenever the session ends or a 401 arrives, denies
 * anonymous checks, honours the superuser flag who-am-i already answers
 * and the #738 record field once it is there, and leaves react-admin's
 * route guards enough truth to gate deep links with.
 */
describe('authProvider.canAccess', () => {
  const WHO_AM_I_URL = 'https://mrmap.test/api/accounts/who-am-i/';

  /** The provider's check as the plain params object the hooks hand it. */
  type CanAccess = (params: {
    resource: string;
    action: string;
    record?: Record<string, unknown>;
  }) => Promise<boolean>;
  const canAccessOf = (provider: ReturnType<typeof tokenAuthProvider>): CanAccess =>
    provider.canAccess as unknown as CanAccess;

  /**
   * Answers who-am-i with these attributes; other verbs get 204, a login gets
   * the given token. `whoAmIFetches` counts the snapshot fetches only.
   */
  const mockBackend = (
    attributes: Record<string, unknown>,
    login?: { token: string; expiry: string },
  ) => {
    const fetchMock = vi.fn(async (request: Request) => {
      if (request.url === WHO_AM_I_URL) {
        return new Response(
          JSON.stringify({
            data: { id: '1', attributes: { username: 'ada', ...attributes } },
          }),
          { status: 200 },
        );
      }
      if (login !== undefined && request.method === 'POST') {
        return new Response(JSON.stringify(login), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      }
      return new Response(null, { status: 204 });
    });
    vi.stubGlobal('fetch', fetchMock);
    return {
      fetchMock,
      whoAmIFetches: () =>
        fetchMock.mock.calls.filter(([request]) => (request as Request).url === WHO_AM_I_URL),
    };
  };

  beforeEach(() => {
    localStorage.clear();
    storeToken();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('answers a batch of resource checks from one who-am-i fetch, not one per check', async () => {
    const { whoAmIFetches } = mockBackend({});
    const canAccess = canAccessOf(tokenAuthProvider());

    const checks: Promise<boolean>[] = [];
    for (const resource of ['WebMapService', 'User']) {
      for (const action of ['list', 'show', 'create', 'edit', 'delete']) {
        // a menu, a toolbar and a datagrid mounting side by side ask the
        // same questions concurrently, and re-render asks them again
        for (let render = 0; render < 4; render++) {
          checks.push(canAccess({ resource, action }));
        }
      }
    }
    const answers = await Promise.all(checks);
    expect(answers.filter(Boolean)).toHaveLength(20); // four repeats of the five WMS actions

    expect(whoAmIFetches()).toHaveLength(1);
    const [[snapshotRequest]] = whoAmIFetches();
    expect((snapshotRequest as Request).headers.get('authorization')).toBe(`Token ${TOKEN}`);

    await canAccess({ resource: 'WebMapService', action: 'list' });
    expect(whoAmIFetches()).toHaveLength(1);
  });

  it('keeps ordinary resources open and administration screens shut to a plain user', async () => {
    mockBackend({});
    const canAccess = canAccessOf(tokenAuthProvider());

    expect(await canAccess({ resource: 'WebMapService', action: 'list' })).toBe(true);
    expect(await canAccess({ resource: 'User', action: 'list' })).toBe(false);
    expect(await canAccess({ resource: 'PeriodicTask', action: 'list' })).toBe(false);
  });

  it('grants the administration screens to the superuser who-am-i answers', async () => {
    mockBackend({ isSuperuser: true });
    const canAccess = canAccessOf(tokenAuthProvider());

    expect(await canAccess({ resource: 'User', action: 'list' })).toBe(true);
    expect(await canAccess({ resource: 'SystemInfo', action: 'list' })).toBe(true);
  });

  it('denies every check to an anonymous visitor without asking the backend', async () => {
    const { whoAmIFetches } = mockBackend({ isSuperuser: true });
    setAuthToken(undefined);
    const canAccess = canAccessOf(tokenAuthProvider());

    expect(await canAccess({ resource: 'WebMapService', action: 'list' })).toBe(false);
    expect(await canAccess({ resource: 'User', action: 'list' })).toBe(false);
    expect(whoAmIFetches()).toHaveLength(0);
  });

  it('fetches a fresh snapshot after the logout dropped the old session', async () => {
    const { whoAmIFetches } = mockBackend({ isSuperuser: true });
    const provider = tokenAuthProvider();

    expect(await canAccessOf(provider)({ resource: 'User', action: 'list' })).toBe(true);
    await provider.logout?.({});

    storeToken(); // a new login of a user who kept the administration role
    expect(await canAccessOf(provider)({ resource: 'User', action: 'list' })).toBe(true);
    expect(whoAmIFetches()).toHaveLength(2);
  });

  it('drops the snapshot when the stored session expires', async () => {
    const { whoAmIFetches } = mockBackend({ isSuperuser: true });
    const canAccess = canAccessOf(tokenAuthProvider());

    expect(await canAccess({ resource: 'User', action: 'list' })).toBe(true);

    const stored = getAuthToken();
    setAuthToken({ ...stored!, expiry: new Date(Date.now() - 1000).toISOString() });
    expect(await canAccess({ resource: 'User', action: 'list' })).toBe(false);
    expect(whoAmIFetches()).toHaveLength(1); // the expired session asks nothing

    storeToken();
    expect(await canAccess({ resource: 'User', action: 'list' })).toBe(true);
    expect(whoAmIFetches()).toHaveLength(2);
  });

  it('drops the snapshot when any endpoint answers 401', async () => {
    const { whoAmIFetches } = mockBackend({ isSuperuser: true });
    const provider = tokenAuthProvider();

    expect(await canAccessOf(provider)({ resource: 'User', action: 'list' })).toBe(true);
    await expect(provider.checkError?.({ status: 401 })).rejects.toThrow('unauthorized');

    storeToken();
    expect(await canAccessOf(provider)({ resource: 'User', action: 'list' })).toBe(true);
    expect(whoAmIFetches()).toHaveLength(2);
  });

  it('seeds the snapshot from the who-am-i the login itself makes', async () => {
    const { whoAmIFetches } = mockBackend(
      { isSuperuser: true },
      { token: TOKEN, expiry: new Date(Date.now() + 60_000).toISOString() },
    );
    setAuthToken(undefined);
    const provider = tokenAuthProvider();

    await provider.login?.({ username: 'ada', password: 'pw' });

    expect(await canAccessOf(provider)({ resource: 'User', action: 'list' })).toBe(true);
    expect(whoAmIFetches()).toHaveLength(1); // login's own, canAccess adds none
  });

  it('judges a record carrying #738 allowedActions by the field instead of the table', async () => {
    mockBackend({});
    const canAccess = canAccessOf(tokenAuthProvider());

    expect(
      await canAccess({
        resource: 'WebMapService',
        action: 'edit',
        record: { id: '1', allowedActions: ['view'] },
      }),
    ).toBe(false);
    expect(
      await canAccess({
        resource: 'WebMapService',
        action: 'edit',
        record: { id: '1', allowedActions: ['view', 'change'] },
      }),
    ).toBe(true);
    // without the field the resource table answers, as it does today
    expect(await canAccess({ resource: 'WebMapService', action: 'edit' })).toBe(true);
  });
});

/**
 * "invisible and unroutable" is half react-admin's: its `useRequireAccess` -
 * the guard every list, create and edit route runs - turns a denied check
 * into a navigation to the standard access-denied state. These two tests pin
 * that the provider's answers actually drive that guard.
 */
describe('route access through react-admin', () => {
  const AccessProbe = ({ resource }: { resource: string }) => {
    useRequireAccess({ resource, action: 'list' });
    return <span>opened {resource}</span>;
  };

  beforeEach(() => {
    localStorage.clear();
    storeToken();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('redirects a deep link into a denied resource to the access-denied state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ data: { id: '1', attributes: { username: 'ada' } } }), {
          status: 200,
        }),
      ),
    );
    let pathname = '/User';
    render(
      <TestMemoryRouter
        initialEntries={['/User']}
        locationCallback={(location) => { pathname = location.pathname; }}
      >
        <AdminContext authProvider={tokenAuthProvider()} dataProvider={{} as DataProvider}>
          <AccessProbe resource="User" />
        </AdminContext>
      </TestMemoryRouter>,
    );

    await waitFor(() => expect(pathname).toBe('/access-denied'));
  });

  it('leaves the deep link of a granted resource alone', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            data: { id: '1', attributes: { username: 'ada', isSuperuser: true } },
          }),
          { status: 200 },
        ),
      ),
    );
    let pathname = '/User';
    render(
      <TestMemoryRouter
        initialEntries={['/User']}
        locationCallback={(location) => { pathname = location.pathname; }}
      >
        <AdminContext authProvider={tokenAuthProvider()} dataProvider={{} as DataProvider}>
          <AccessProbe resource="User" />
        </AdminContext>
      </TestMemoryRouter>,
    );

    expect(await screen.findByText('opened User')).toBeInTheDocument();
    expect(pathname).toBe('/User');
  });
});
