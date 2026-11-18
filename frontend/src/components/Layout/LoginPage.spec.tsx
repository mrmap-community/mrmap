/**
 * The login page of #834 on its session form (#835): when the backend stopped
 * accepting this browser's session, the page the redirect lands on names the
 * reason - translated, in the user's language - above react-admin's form; a
 * deliberate logout or a fresh visit shows none, and the reason is consumed so
 * it never repeats.
 */
import { AdminContext, TestMemoryRouter } from 'react-admin';
import type { DataProvider } from 'react-admin';

import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import sessionAuthProvider, {
  consumeSessionEndReason,
  setSession,
} from '../../providers/authProvider';
import i18nProvider from '../../providers/i18nProvider';
import LoginPage from './LoginPage';

vi.mock('../../context/HttpClientContext', () => ({ API_BASE_URL: 'https://mrmap.test' }));

const SESSION_URL = 'https://mrmap.test/api/auth/session';

/**
 * Ends the session the way the application does: the browser still carries
 * its marker, but the session probe answers that the server stopped accepting
 * this cookie - the same `checkAuth` call react-admin's route guard makes
 * when it sends the user to /login (#835: the backend decides, the client no
 * longer reads an expiry of its own).
 */
const expireSession = async () => {
  setSession({
    id: 1,
    fullName: 'Ada Lovelace',
    openedAt: new Date().toISOString(),
  });
  vi.stubGlobal('fetch', vi.fn(async (request: Request) =>
    request.url === SESSION_URL
      ? new Response(JSON.stringify({ authenticated: false }), {
          status: 200, headers: { 'content-type': 'application/json' },
        })
      : new Response(null, { status: 204 }),
  ));
  await sessionAuthProvider().checkAuth?.({}).catch(() => undefined);
  vi.unstubAllGlobals();
};

const renderLoginPage = () => render(
  <TestMemoryRouter initialEntries={['/login']}>
    <AdminContext
      authProvider={sessionAuthProvider()}
      dataProvider={{} as DataProvider}
      i18nProvider={i18nProvider}
    >
      <LoginPage />
    </AdminContext>
  </TestMemoryRouter>,
);

beforeEach(() => {
  localStorage.clear();
});

afterEach(async () => {
  // changeLocale switches a module-level catalog, so leave no locale behind
  await i18nProvider.changeLocale('en');
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('LoginPage', () => {
  it('shows the login form', () => {
    renderLoginPage();
    expect(screen.getByRole('textbox', { name: 'Username' })).toBeInTheDocument();
  });

  it('names the expired session above the form', async () => {
    await expireSession();

    renderLoginPage();

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Your session has expired. Please log in again.',
    );
  });

  it('names it in German too', async () => {
    await i18nProvider.changeLocale('de');
    await expireSession();

    renderLoginPage();

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.',
    );
  });

  it('answers the reason once: the next visit shows a plain form', async () => {
    await expireSession();

    const { unmount } = renderLoginPage();
    await screen.findByRole('status');
    unmount();

    renderLoginPage();
    expect(consumeSessionEndReason()).toBeUndefined();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('shows nothing after a deliberate logout', () => {
    renderLoginPage();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
