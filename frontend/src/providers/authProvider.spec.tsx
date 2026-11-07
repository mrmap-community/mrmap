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
 */
import { AdminContext, TestMemoryRouter, useLogout } from 'react-admin';
import type { DataProvider } from 'react-admin';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import tokenAuthProvider, { AUTH_TOKEN_LOCAL_STORAGE_NAME, setAuthToken } from './authProvider';

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
