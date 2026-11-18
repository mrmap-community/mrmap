/**
 * Pins the browser-session contract of #835 (accepted decision Q8=B): a login
 * turns Basic credentials into a Django session whose cookie the browser
 * attaches on its own, state-changing requests repeat the CSRF cookie in its
 * header, and a logout flushes the session at the backend. The provider holds
 * no credential - `localStorage` only keeps the identity marker - and a legacy
 * knox token a pre-#835 frontend left behind is revoked once and dropped.
 *
 * The first suites call the provider directly: login, CSRF double-submit,
 * rollout revocation, offline tolerance and "the backend decides whether the
 * cookie still authenticates" are properties of the provider alone. Later
 * suites run it through react-admin's own hooks (`useLogout`,
 * `useRequireAccess`, `useLogoutIfAccessDenied`), because "lands on /login",
 * "lands on /access-denied" and the translated notification are those hooks'
 * business, not the provider's.
 *
 * The `canAccess` suite pins #836 on top of it: resource checks answer from
 * one permission snapshot per session - never per render - and every way this
 * file knows to end or invalidate the session drops that snapshot.
 *
 * The role suite pins what #737 sits on: the ids `who-am-i` carries become
 * definition slugs through the two role API reads of #736 before the snapshot
 * is handed out, an unanswered step degrades to the superuser flag, and the
 * `getPermissionSnapshot` seam answers the cached snapshot - after an
 * invalidation a fresh one.
 *
 * The `checkAuth`/`checkError` suites pin #834's lifecycle on its session
 * form: only the backend's answer (the probe, or the JSON:API error code -
 * not the status, because this deployment answers a dead session with 403
 * too) ends the session, and it ends with the reason as a translation key so
 * the login page can name it in the user's language.
 */
import {
  AdminContext,
  // The application renders this through react-admin's own Admin; AdminContext
  // alone has no notification host, so the spec that asserts the toast mounts it.
  Notification,
  TestMemoryRouter,
  useLogoutIfAccessDenied,
  useLogout,
  useRequireAccess,
} from 'react-admin';
import type { DataProvider } from 'react-admin';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import sessionAuthProvider, {
  AUTH_SESSION_LOCAL_STORAGE_NAME,
  consumeSessionEndReason,
  getCsrfToken,
  getPermissionSnapshot,
  getSessionEndReason,
  invalidatePermissionSnapshot,
  onPermissionLost,
  setSession,
} from './authProvider';
import i18nProvider from './i18nProvider';

vi.mock('../context/HttpClientContext', () => ({ API_BASE_URL: 'https://mrmap.test' }));

const SESSION_URL = 'https://mrmap.test/api/auth/session';
const LEGACY_LOGOUT_URL = 'https://mrmap.test/api/auth/logout';
const WHO_AM_I_URL = 'https://mrmap.test/api/accounts/who-am-i/';
const LEGACY_KEY = 'mrmap.auth';

/** The provider as the application builds it, with the mocked API base URL. */
const authProvider = sessionAuthProvider();

/** The session marker #835 keeps: identity only, never a credential. */
const storeSession = () => setSession({
  id: 1,
  fullName: 'Ada Lovelace',
  openedAt: new Date().toISOString(),
});

const storedSession = () => localStorage.getItem(AUTH_SESSION_LOCAL_STORAGE_NAME);

/** The CSRF cookie Django answers; the provider copies it into its header. */
const CSRF_VALUE = 'csrf-test-value';
const withCsrfCookie = () => { document.cookie = `csrftoken=${CSRF_VALUE}; path=/`; };
const clearCsrfCookie = () => {
  document.cookie = 'csrftoken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
};

interface Backend {
  attributes?: Record<string, unknown>;
  /** what the session probe answers: a response, a network error, or authenticated */
  probe?: Response | Error | boolean;
  /** what the login POST answers; default: accepted with 204 */
  login?: Response;
  /** override for any request, e.g. a refused logout */
  extra?: (request: Request) => Response | undefined;
}

/** Routes every URL the provider talks to and counts the calls per endpoint. */
const mockBackend = (backend: Backend = {}) => {
  const probe = backend.probe === true || backend.probe === undefined
    ? new Response(JSON.stringify({ authenticated: true }), {
        status: 200, headers: { 'content-type': 'application/json' },
      })
    : backend.probe === false
      ? new Response(JSON.stringify({ authenticated: false }), {
          status: 200, headers: { 'content-type': 'application/json' },
        })
      : backend.probe;
  const fetchMock = vi.fn(async (request: Request) => {
    const routed = backend.extra?.(request);
    if (routed !== undefined) return routed;
    if (request.url === WHO_AM_I_URL) {
      return new Response(
        JSON.stringify({
          data: { id: '1', attributes: { username: 'ada', ...backend.attributes } },
        }),
        { status: 200 },
      );
    }
    if (request.url === SESSION_URL && request.method === 'GET') {
      if (probe instanceof Error) throw probe;
      return probe;
    }
    if (request.url === SESSION_URL && request.method === 'POST') {
      return backend.login ?? new Response(null, { status: 204 });
    }
    return new Response(null, { status: 204 });
  });
  vi.stubGlobal('fetch', fetchMock);
  const hits = (url: string, method?: string) => () =>
    fetchMock.mock.calls.filter(
      ([request]) =>
        (request as Request).url === url
        && (method === undefined || (request as Request).method === method),
    );
  return {
    fetchMock,
    whoAmIs: hits(WHO_AM_I_URL),
    probes: hits(SESSION_URL, 'GET'),
    logins: hits(SESSION_URL, 'POST'),
    closes: hits(SESSION_URL, 'DELETE'),
    legacyLogouts: hits(LEGACY_LOGOUT_URL),
  };
};

/** The fetch of a backend that answers nothing. */
const mockOffline = () => {
  const fetchMock = vi.fn().mockRejectedValue(new Error('offline'));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
};

beforeEach(() => {
  localStorage.clear();
  clearCsrfCookie();
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  clearCsrfCookie();
});

describe('authProvider.login', () => {
  it('turns basic credentials into the session and keeps no credential itself', async () => {
    withCsrfCookie();
    const backend = mockBackend();

    await expect(authProvider.login?.({ username: 'ada', password: 'pw' }))
      .resolves.toBe(true);

    const [[post]] = backend.logins();
    expect(post).toBeInstanceOf(Request);
    expect(post.url).toBe(SESSION_URL);
    expect(post.method).toBe('POST');
    expect(post.credentials).toBe('include');
    // the credential of this one request, never stored anywhere
    expect(post.headers.get('authorization')).toBe('Basic ' + btoa('ada:pw'));
    expect(post.headers.get('x-csrftoken')).toBe(CSRF_VALUE);

    // what the browser remembers afterwards is the identity, not a token
    expect(JSON.parse(storedSession()!)).toEqual(expect.objectContaining({
      id: '1', fullName: 'ada',
    }));
    expect(localStorage.getItem(LEGACY_KEY)).toBeNull();
  });

  it('asks the who-am-i the session now authenticates', async () => {
    const backend = mockBackend();

    await authProvider.login?.({ username: 'ada', password: 'pw' });

    const [[identity]] = backend.whoAmIs();
    expect(identity.credentials).toBe('include');
    // no Authorization header to attach any more: the cookie authenticates
    expect(identity.headers.get('authorization')).toBeNull();
  });

  it('reports the reason of a refused login and stores no session', async () => {
    mockBackend({
      // the json:api error document of the stack's exception handler
      login: new Response(JSON.stringify({
        errors: [{ detail: 'Invalid credentials.', code: 'not_authenticated' }],
      }), {
        status: 403, headers: { 'content-type': 'application/json' },
      }),
    });

    await expect(authProvider.login?.({ username: 'ada', password: 'pw' }))
      .rejects.toThrow('Invalid credentials.');
    expect(storedSession()).toBeNull();
  });

  it('reads a plain detail answer too', async () => {
    mockBackend({
      login: new Response(JSON.stringify({ detail: 'Invalid credentials.' }), {
        status: 403, headers: { 'content-type': 'application/json' },
      }),
    });

    await expect(authProvider.login?.({ username: 'ada', password: 'pw' }))
      .rejects.toThrow('Invalid credentials.');
    expect(storedSession()).toBeNull();
  });

  it('falls back to the status text when the refusal is not JSON', async () => {
    mockBackend({
      login: new Response('<html>proxy says no</html>', {
        status: 401, statusText: 'Unauthorized',
        headers: { 'content-type': 'text/html' },
      }),
    });

    await expect(authProvider.login?.({ username: 'ada', password: 'pw' }))
      .rejects.toThrow('Unauthorized');
    expect(storedSession()).toBeNull();
  });

  it('sends no CSRF header while this browser has no cookie yet', async () => {
    const backend = mockBackend();

    await authProvider.login?.({ username: 'ada', password: 'pw' });

    const [[post]] = backend.logins();
    expect(post.headers.get('x-csrftoken')).toBeNull();
  });
});

describe('getCsrfToken', () => {
  it('answers the CSRF cookie this browser was given', () => {
    withCsrfCookie();
    expect(getCsrfToken()).toBe(CSRF_VALUE);
  });

  it('answers nothing without the cookie', () => {
    expect(getCsrfToken()).toBeUndefined();
  });
});

describe('the legacy browser token of the rollout (#835)', () => {
  it('revokes the token the previous frontend left in localStorage and drops it', async () => {
    localStorage.setItem(LEGACY_KEY, JSON.stringify({ token: 'an-old-knox-token' }));
    const backend = mockBackend();

    sessionAuthProvider();

    // dropped synchronously when the provider is built, revoked at the backend
    expect(localStorage.getItem(LEGACY_KEY)).toBeNull();
    await waitFor(() => expect(backend.legacyLogouts()).toHaveLength(1));
    const [[revocation]] = backend.legacyLogouts();
    expect(revocation.method).toBe('POST');
    expect(revocation.headers.get('authorization')).toBe('Token an-old-knox-token');
  });

  it('drops an unparseable value without asking anything', async () => {
    localStorage.setItem(LEGACY_KEY, 'not-a-session-at-all');
    const backend = mockBackend();

    sessionAuthProvider();

    expect(localStorage.getItem(LEGACY_KEY)).toBeNull();
    await Promise.resolve();
    expect(backend.legacyLogouts()).toHaveLength(0);
  });

  it('is not asked about again once dropped', async () => {
    localStorage.setItem(LEGACY_KEY, JSON.stringify({ token: 'an-old-knox-token' }));
    const first = mockBackend();
    sessionAuthProvider();
    await waitFor(() => expect(first.legacyLogouts()).toHaveLength(1));

    mockBackend();
    sessionAuthProvider();
    await Promise.resolve();

    // the second page load has nothing left to revoke
    expect(localStorage.getItem(LEGACY_KEY)).toBeNull();
  });

  it('survives an unreachable backend without blocking the login page', async () => {
    localStorage.setItem(LEGACY_KEY, JSON.stringify({ token: 'an-old-knox-token' }));
    mockOffline();

    expect(() => sessionAuthProvider()).not.toThrow();
    await waitFor(() => expect(localStorage.getItem(LEGACY_KEY)).toBeNull());
  });
});

describe('authProvider.logout', () => {
  beforeEach(() => {
    localStorage.clear();
    storeSession();
  });

  it('closes the session at the backend before dropping the marker', async () => {
    withCsrfCookie();
    const backend = mockBackend();

    await authProvider.logout?.({});

    const [[close]] = backend.closes();
    expect(close.url).toBe(SESSION_URL);
    expect(close.method).toBe('DELETE');
    expect(close.credentials).toBe('include');
    // an unsafe request the session authenticates: CSRF or nothing
    expect(close.headers.get('x-csrftoken')).toBe(CSRF_VALUE);
    expect(close.headers.get('authorization')).toBeNull();
    expect(storedSession()).toBeNull();
  });

  it('ends the local session when the backend cannot be reached', async () => {
    mockOffline();

    await expect(authProvider.logout?.({})).resolves.toBeUndefined();

    expect(storedSession()).toBeNull();
  });

  it('ends the local session when the backend refuses the request', async () => {
    mockBackend({
      extra: request =>
        request.method === 'DELETE' ? new Response(null, { status: 500 }) : undefined,
    });

    await expect(authProvider.logout?.({})).resolves.toBeUndefined();

    expect(storedSession()).toBeNull();
  });

  it('asks the backend to close even when this browser kept no marker', async () => {
    // the cookie can outlive the marker (another tab ended it); the server
    // still learns that this caller signed out
    setSession(undefined);
    const backend = mockBackend();

    await authProvider.logout?.({});

    expect(backend.closes()).toHaveLength(1);
  });
});

describe('logout through react-admin', () => {
  const LogoutTrigger = () => {
    const logout = useLogout();
    return <button onClick={() => { void logout(); }}>log out</button>;
  };

  it('lands on /login although the closing request failed', async () => {
    storeSession();
    mockOffline();
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
    expect(storedSession()).toBeNull();
  });
});

/**
 * The #836 contract, judged against the provider as the app builds it:
 * canAccess answers from one snapshot fetched per session - never per
 * render - resets it whenever the session ends or the backend refuses,
 * denies anonymous checks, honours the superuser flag who-am-i already
 * answers and the #738 record field once it is there, and leaves
 * react-admin's route guards enough truth to gate deep links with.
 */
describe('authProvider.canAccess', () => {
  /** The provider's check as the plain params object the hooks hand it. */
  type CanAccess = (params: {
    resource: string;
    action: string;
    record?: Record<string, unknown>;
  }) => Promise<boolean>;
  const canAccessOf = (provider: ReturnType<typeof sessionAuthProvider>): CanAccess =>
    provider.canAccess as unknown as CanAccess;

  beforeEach(() => {
    localStorage.clear();
    storeSession();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('answers a batch of resource checks from one who-am-i fetch, not one per check', async () => {
    const backend = mockBackend();
    const canAccess = canAccessOf(sessionAuthProvider());

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

    expect(backend.whoAmIs()).toHaveLength(1);
    const [[snapshotRequest]] = backend.whoAmIs();
    // the session cookie is the credential: no header repeats it
    expect((snapshotRequest as Request).credentials).toBe('include');
    expect((snapshotRequest as Request).headers.get('authorization')).toBeNull();

    await canAccess({ resource: 'WebMapService', action: 'list' });
    expect(backend.whoAmIs()).toHaveLength(1);
  });

  it('keeps ordinary resources open and administration screens shut to a plain user', async () => {
    mockBackend();
    const canAccess = canAccessOf(sessionAuthProvider());

    expect(await canAccess({ resource: 'WebMapService', action: 'list' })).toBe(true);
    expect(await canAccess({ resource: 'User', action: 'list' })).toBe(false);
    expect(await canAccess({ resource: 'PeriodicTask', action: 'list' })).toBe(false);
  });

  it('grants the administration screens to the superuser who-am-i answers', async () => {
    mockBackend({ attributes: { isSuperuser: true } });
    const canAccess = canAccessOf(sessionAuthProvider());

    expect(await canAccess({ resource: 'User', action: 'list' })).toBe(true);
    expect(await canAccess({ resource: 'SystemInfo', action: 'list' })).toBe(true);
  });

  it('answers the public set of #833 to an anonymous visitor without asking the backend', async () => {
    const backend = mockBackend({ attributes: { isSuperuser: true } });
    setSession(undefined);
    const canAccess = canAccessOf(sessionAuthProvider());

    // the published kinds of service open their list and show screens -
    // what those screens contain stays the api's answer
    expect(await canAccess({ resource: 'WebMapService', action: 'list' })).toBe(true);
    expect(await canAccess({ resource: 'WebMapService', action: 'show' })).toBe(true);
    expect(await canAccess({ resource: 'WebFeatureService', action: 'list' })).toBe(true);
    // every write and every other resource stays denied, and answering the
    // whole table needs no backend: the anonymous path never fetches who-am-i
    expect(await canAccess({ resource: 'WebMapService', action: 'edit' })).toBe(false);
    expect(await canAccess({ resource: 'Layer', action: 'list' })).toBe(false);
    expect(await canAccess({ resource: 'User', action: 'list' })).toBe(false);
    expect(backend.whoAmIs()).toHaveLength(0);
  });

  it('fetches a fresh snapshot after the logout dropped the old session', async () => {
    const backend = mockBackend({ attributes: { isSuperuser: true } });
    const provider = sessionAuthProvider();

    expect(await canAccessOf(provider)({ resource: 'User', action: 'list' })).toBe(true);
    await provider.logout?.({});

    storeSession(); // a new login of a user who kept the administration role
    expect(await canAccessOf(provider)({ resource: 'User', action: 'list' })).toBe(true);
    expect(backend.whoAmIs()).toHaveLength(2);
  });

  it('drops the snapshot when the marker vanished - the server ended the session', async () => {
    // a session the *server* ended announces itself through refused calls, not
    // through a client-side expiry any more; whatever path learned it clears
    // the marker, and the check must not answer from the stale snapshot
    const backend = mockBackend({ attributes: { isSuperuser: true } });
    const canAccess = canAccessOf(sessionAuthProvider());

    expect(await canAccess({ resource: 'User', action: 'list' })).toBe(true);

    setSession(undefined);
    expect(await canAccess({ resource: 'User', action: 'list' })).toBe(false);
    expect(backend.whoAmIs()).toHaveLength(1); // an ended session asks nothing

    storeSession();
    expect(await canAccess({ resource: 'User', action: 'list' })).toBe(true);
    expect(backend.whoAmIs()).toHaveLength(2);
  });

  it('drops the snapshot when any endpoint answers 401', async () => {
    const backend = mockBackend({ attributes: { isSuperuser: true } });
    const provider = sessionAuthProvider();

    expect(await canAccessOf(provider)({ resource: 'User', action: 'list' })).toBe(true);
    await expect(provider.checkError?.({ status: 401 }))
      .rejects.toThrow('auth.sessionExpired');

    storeSession();
    expect(await canAccessOf(provider)({ resource: 'User', action: 'list' })).toBe(true);
    expect(backend.whoAmIs()).toHaveLength(2);
  });

  it('seeds the snapshot from the who-am-i the login itself makes', async () => {
    const backend = mockBackend({ attributes: { isSuperuser: true } });
    setSession(undefined);
    const provider = sessionAuthProvider();

    await provider.login?.({ username: 'ada', password: 'pw' });

    expect(await canAccessOf(provider)({ resource: 'User', action: 'list' })).toBe(true);
    expect(backend.whoAmIs()).toHaveLength(1); // login's own, canAccess adds none
  });

  it('judges a record carrying #738 allowedActions by the field instead of the table', async () => {
    mockBackend();
    const canAccess = canAccessOf(sessionAuthProvider());

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
    storeSession();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('redirects a deep link into a denied resource to the access-denied state', async () => {
    mockBackend(); // plain user, session accepted
    let pathname = '/User';
    render(
      <TestMemoryRouter
        initialEntries={['/User']}
        locationCallback={(location) => { pathname = location.pathname; }}
      >
        <AdminContext authProvider={sessionAuthProvider()} dataProvider={{} as DataProvider}>
          <AccessProbe resource="User" />
        </AdminContext>
      </TestMemoryRouter>,
    );

    await waitFor(() => expect(pathname).toBe('/access-denied'));
  });

  it('leaves the deep link of a granted resource alone', async () => {
    mockBackend({ attributes: { isSuperuser: true } });
    let pathname = '/User';
    render(
      <TestMemoryRouter
        initialEntries={['/User']}
        locationCallback={(location) => { pathname = location.pathname; }}
      >
        <AdminContext authProvider={sessionAuthProvider()} dataProvider={{} as DataProvider}>
          <AccessProbe resource="User" />
        </AdminContext>
      </TestMemoryRouter>,
    );

    expect(await screen.findByText('opened User')).toBeInTheDocument();
    expect(pathname).toBe('/User');
  });
});

/**
 * What the #737 administration screens sit on: the `who-am-i` answer carries
 * the caller's role rows as ids, the role API of #736 answers their slugs -
 * and the snapshot the `canAccess` table judges must already hold the slugs,
 * never the ids. All reads ride on the session cookie; an unanswered one
 * degrades to the superuser flag instead of failing the check, and the seam
 * `getPermissionSnapshot`/`invalidatePermissionSnapshot` hands the screens the
 * same cached snapshot - after a self-revocation invalidates it, a fresh one.
 */
describe('role slug resolution of #736 behind the snapshot', () => {
  const ROLES_URL = 'https://mrmap.test/api/accounts/roles/?filter[id.in]=11%2C13';
  const DEFINITIONS_URL =
    'https://mrmap.test/api/accounts/roledefinitions/?filter[id.in]=3%2C5';

  const WHO_AM_I = {
    data: {
      id: '1',
      attributes: { username: 'ada' },
      relationships: {
        roles: { data: [{ type: 'Role', id: '11' }, { type: 'Role', id: '13' }] },
      },
    },
  };
  const ROLE_ROWS = {
    data: [
      {
        id: '11',
        attributes: { isActive: true },
        relationships: {
          role_definition: { data: { type: 'RoleDefinition', id: '3' } },
          organization: { data: { type: 'Organization', id: '7' } },
        },
      },
      {
        // the platform role row: active, without an organization
        id: '13',
        attributes: { isActive: true },
        relationships: {
          role_definition: { data: { type: 'RoleDefinition', id: '5' } },
          organization: { data: null },
        },
      },
    ],
  };
  const DEFINITIONS = {
    data: [
      { id: '3', attributes: { slug: 'organization_admin' } },
      { id: '5', attributes: { slug: 'platform_admin' } },
    ],
  };

  /** Routes the three reads; a refused step answers the given status. */
  const mockRoles = (rolesStatus = 200, definitionsStatus = 200) => {
    const fetchMock = vi.fn(async (request: Request) => {
      if (request.url === WHO_AM_I_URL) {
        return new Response(JSON.stringify(WHO_AM_I), { status: 200 });
      }
      if (request.url === ROLES_URL) {
        return rolesStatus === 200
          ? new Response(JSON.stringify(ROLE_ROWS), { status: 200 })
          : new Response(null, { status: rolesStatus });
      }
      if (request.url === DEFINITIONS_URL) {
        return definitionsStatus === 200
          ? new Response(JSON.stringify(DEFINITIONS), { status: 200 })
          : new Response(null, { status: definitionsStatus });
      }
      return new Response(null, { status: 204 });
    });
    vi.stubGlobal('fetch', fetchMock);
    const hits = (url: string) => () =>
      fetchMock.mock.calls.filter(([request]) => (request as Request).url === url);
    return {
      fetchMock,
      whoAmIs: hits(WHO_AM_I_URL),
      roleReads: hits(ROLES_URL),
      definitionReads: hits(DEFINITIONS_URL),
    };
  };

  const canAccessUser = async (provider: ReturnType<typeof sessionAuthProvider>) =>
    (provider.canAccess as unknown as (p: {
      resource: string; action: string;
    }) => Promise<boolean>)({ resource: 'User', action: 'list' });

  beforeEach(() => {
    localStorage.clear();
    storeSession();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('resolves the who-am-i role ids into slugs through the two role API reads', async () => {
    const backend = mockRoles();
    const provider = sessionAuthProvider();

    expect(await canAccessUser(provider)).toBe(true);

    expect(backend.whoAmIs()).toHaveLength(1);
    expect(backend.roleReads()).toHaveLength(1);
    expect(backend.definitionReads()).toHaveLength(1);
    const [[roleRequest]] = backend.roleReads();
    // the session cookie authenticates these reads as well
    expect((roleRequest as Request).credentials).toBe('include');
    expect((roleRequest as Request).headers.get('authorization')).toBeNull();

    expect(await getPermissionSnapshot()).toEqual({
      roles: ['organization_admin', 'platform_admin'],
      administeredOrganizationIds: ['7'],
      isSuperuser: false,
    });
    // one resolution per session: the seam answers from the same snapshot
    await getPermissionSnapshot();
    expect(backend.whoAmIs()).toHaveLength(1);
    expect(backend.roleReads()).toHaveLength(1);
  });

  it('denies administration when the role read is refused - only the flag is left', async () => {
    mockRoles(403);
    const provider = sessionAuthProvider();

    expect(await canAccessUser(provider)).toBe(false);
    expect(await getPermissionSnapshot()).toEqual({
      roles: [], administeredOrganizationIds: [], isSuperuser: false,
    });
  });

  it('degrades to the unresolved snapshot when the definition read is refused', async () => {
    mockRoles(200, 403);
    const provider = sessionAuthProvider();

    expect(await canAccessUser(provider)).toBe(false);
    expect(await getPermissionSnapshot()).toEqual({
      roles: [], administeredOrganizationIds: [], isSuperuser: false,
    });
  });

  it('re-reads everything after the screens invalidated the snapshot', async () => {
    const backend = mockRoles();
    const provider = sessionAuthProvider();
    expect(await canAccessUser(provider)).toBe(true);

    // the self-revocation of the Members screen: the next answer must come
    // from the backend again, not from the session-stable cache
    invalidatePermissionSnapshot();

    expect(await canAccessUser(provider)).toBe(true);
    expect(backend.whoAmIs()).toHaveLength(2);
    expect(backend.roleReads()).toHaveLength(2);
  });

  it('answers nothing through the seam without a session', async () => {
    mockRoles();
    setSession(undefined);

    expect(getPermissionSnapshot()).toBeUndefined();
    expect(() => invalidatePermissionSnapshot()).not.toThrow();
  });
});

/**
 * #834's session lifecycle on its session form: *the backend* decides whether
 * this browser's cookie still authenticates - a session cookie carries no
 * client-readable expiry - and an ended session ends with the reason as a
 * translation key so react-admin's `useCheckAuth` can notify it in the user's
 * language while redirecting to /login. The probe runs once per page load.
 */
describe('authProvider.checkAuth', () => {
  let provider: ReturnType<typeof sessionAuthProvider>;

  beforeEach(() => {
    localStorage.clear();
    consumeSessionEndReason();
    storeSession();
    // the provider remembers that *this page load* confirmed the session -
    // as it does in the app, where one page load is one instance - so every
    // case has to start from a freshly built one
    provider = sessionAuthProvider();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('asks the backend once per page load and keeps an accepted session', async () => {
    const backend = mockBackend();

    await expect(provider.checkAuth?.({})).resolves.toBeUndefined();
    await expect(provider.checkAuth?.({})).resolves.toBeUndefined();

    expect(backend.probes()).toHaveLength(1);
    expect(storedSession()).not.toBeNull();
  });

  it('keeps the session it believes in when the probe is unreachable', async () => {
    // guessing "ended" from a network outage would log users out of a live
    // session; the data calls decide from here
    mockBackend({ probe: new Error('offline') });

    await expect(provider.checkAuth?.({})).resolves.toBeUndefined();
    expect(storedSession()).not.toBeNull();
  });

  it('refuses without a stored marker, setting no reason', async () => {
    const backend = mockBackend();
    setSession(undefined);

    await expect(provider.checkAuth?.({})).rejects.toThrow('not authenticated');
    expect(getSessionEndReason()).toBeUndefined();
    expect(backend.probes()).toHaveLength(0); // nothing to ask about
  });

  it('ends the session the backend no longer accepts, with the reason', async () => {
    mockBackend({ probe: false });

    await expect(provider.checkAuth?.({})).rejects.toThrow('auth.sessionExpired');
    expect(storedSession()).toBeNull();
    expect(getSessionEndReason()).toBe('auth.sessionExpired');
  });
});

/**
 * #834's `checkError` contract (docs/source/administration/authentication.md):
 * this deployment answers a dead session with the same 403 as a refused
 * action, so the JSON:API error code decides. A live session survives every
 * `permission_denied` and revalidates its rights; the session is given up
 * exactly when the code - or a 401 - says the cookie is gone.
 */
describe('authProvider.checkError', () => {
  /** who-am-i always answers; counts the snapshot fetches it causes. */
  const mockWhoAmI = () => {
    const backend = mockBackend({ attributes: { isSuperuser: true } });
    return backend.whoAmIs;
  };

  type CheckError = (error: unknown) => Promise<unknown>;
  const checkErrorOf = (provider: ReturnType<typeof sessionAuthProvider>) =>
    provider.checkError as unknown as CheckError;
  const canAccessUser = (provider: ReturnType<typeof sessionAuthProvider>) =>
    (provider.canAccess as unknown as (p: { resource: string; action: string }) =>
      Promise<boolean>)({ resource: 'User', action: 'list' });

  /** The AxiosError shape of the dataProvider and the HttpError shape both carry the code. */
  const denied = (code: string) =>
    code === 'authentication_failed' || code === 'not_authenticated'
      ? { status: 403, message: 'denied', response: { data: { errors: [{ code }] } } }
      : { status: 403, message: 'denied', body: { errors: [{ code }] } };

  /** The rejected value of a call: these cases assert on the thrown error,
   * and a call that resolved instead is itself the failure. */
  const rejection = async (
    promise: Promise<unknown>,
  ): Promise<Error & { logoutUser?: boolean }> => {
    const error = await promise.then(
      () => undefined,
      (reason: Error & { logoutUser?: boolean }) => reason,
    );
    if (error === undefined) {
      throw new Error('expected the call to reject');
    }
    return error;
  };

  beforeEach(() => {
    localStorage.clear();
    consumeSessionEndReason();
    storeSession(); // the session every case below starts from
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('keeps the session on permission_denied, notifies the key and revalidates', async () => {
    const whoAmIs = mockWhoAmI();
    const provider = sessionAuthProvider();
    expect(await canAccessUser(provider)).toBe(true); // snapshot holds one fetch
    const permissionLost = vi.fn();
    const unsubscribe = onPermissionLost(permissionLost);

    const failure = await rejection(checkErrorOf(provider)(denied('permission_denied')));

    expect(failure.message).toBe('auth.forbidden');
    expect(failure.logoutUser).toBe(false); // react-admin: notify, do NOT log out
    expect(storedSession()).not.toBeNull();
    expect(getSessionEndReason()).toBeUndefined();
    expect(permissionLost).toHaveBeenCalledOnce(); // the bridge's revalidation seam
    unsubscribe();

    expect(await canAccessUser(provider)).toBe(true);
    expect(whoAmIs()).toHaveLength(2); // the refused action dropped the snapshot
  });

  it.each(['authentication_failed', 'not_authenticated'] as const)(
    'ends the session on %s: session gone, reason set, snapshot silenced',
    async code => {
      const whoAmIs = mockWhoAmI();
      const provider = sessionAuthProvider();
      expect(await canAccessUser(provider)).toBe(true);

      const failure = await rejection(checkErrorOf(provider)(denied(code)));

      expect(failure.message).toBe('auth.sessionExpired');
      expect(storedSession()).toBeNull();
      expect(getSessionEndReason()).toBe('auth.sessionExpired');
      // ...and the gone session now denies without a stale cached grant
      expect(await canAccessUser(provider)).toBe(false);
      expect(whoAmIs()).toHaveLength(1);
    },
  );

  it('keeps a live session against a codeless 403 - a cookie has no expiry to fall back on', async () => {
    mockWhoAmI();
    const provider = sessionAuthProvider();

    const failure = await rejection(checkErrorOf(provider)({ status: 403 }));

    expect(failure.message).toBe('auth.forbidden');
    expect(failure.logoutUser).toBe(false);
    expect(storedSession()).not.toBeNull(); // a valid session is never logged out on a guess
  });

  it('ends the session outright on 401, whatever the code says', async () => {
    const provider = sessionAuthProvider();

    await expect(checkErrorOf(provider)({ status: 401 })).rejects.toThrow('auth.sessionExpired');
    expect(storedSession()).toBeNull();
    expect(getSessionEndReason()).toBe('auth.sessionExpired');
  });

  it('leaves every other status to its caller', async () => {
    const provider = sessionAuthProvider();

    await expect(checkErrorOf(provider)({ status: 500 })).resolves.toBeUndefined();
    expect(storedSession()).not.toBeNull();
  });

  it('answers a guarded-route refusal without a session, setting no reason', async () => {
    setSession(undefined);
    const provider = sessionAuthProvider();

    const failure = await rejection(checkErrorOf(provider)({ status: 401 }));

    expect(failure.message).toBe('not authenticated');
    expect(getSessionEndReason()).toBeUndefined();
  });
});

/**
 * The same contract through react-admin's real hook: `useLogoutIfAccessDenied`
 * (every dataProvider call runs it) logs out and redirects when the provider
 * says the session is gone, and for `permission_denied` shows the translated
 * key while the session - and the page - stay.
 */
describe('checkError through react-admin', () => {
  const AccessFailure = ({ error }: { error: unknown }) => {
    const logoutIfAccessDenied = useLogoutIfAccessDenied();
    return (
      <button onClick={() => { void logoutIfAccessDenied(error); }}>
        failed call
      </button>
    );
  };

  const runFailedCall = (error: unknown, initial = '/User') => {
    let pathname = initial;
    render(
      <TestMemoryRouter
        initialEntries={[initial]}
        locationCallback={(location) => { pathname = location.pathname; }}
      >
        <AdminContext
          authProvider={sessionAuthProvider()}
          dataProvider={{} as DataProvider}
          i18nProvider={i18nProvider}
        >
          <Notification />
          <AccessFailure error={error} />
        </AdminContext>
      </TestMemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /failed call/i }));
    return () => pathname;
  };

  beforeEach(() => {
    localStorage.clear();
    consumeSessionEndReason();
    storeSession();
    mockBackend(); // probe accepted, who-am-i answering, DELETE 204
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('shows the forbidden message and keeps the session and the page', async () => {
    runFailedCall({ status: 403, message: 'no', body: { errors: [{ code: 'permission_denied' }] } });

    expect(
      await screen.findByText('You no longer have the rights for this action.'),
    ).toBeInTheDocument();
    expect(storedSession()).not.toBeNull();
  });

  it('clears the session and lands on /login on 401', async () => {
    const pathname = runFailedCall({ status: 401, message: 'gone' });

    await waitFor(() => expect(pathname()).toBe('/login'));
    expect(storedSession()).toBeNull();
    expect(getSessionEndReason()).toBe('auth.sessionExpired');
  });
});
