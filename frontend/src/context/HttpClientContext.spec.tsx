import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HttpClientBase, useHttpClientContext } from './HttpClientContext';

const LOCALE_STORAGE_NAME = 'RaStore.locale';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  client: vi.fn(),
  init: vi.fn(),
}));

// The boot is what this spec is about, so neither the megabyte transfer nor
// the client build is real here: what is asserted is how often the document
// is asked for and how long a failing boot waits between the attempts.
vi.mock('axios', () => {
  class AxiosHeaders {
    constructor(init?: Record<string, string>) {
      Object.assign(this, init);
    }
  }
  return {
    default: { get: (url: string, config: unknown) => mocks.get(url, config) },
    AxiosHeaders,
    AxiosError: class AxiosError extends Error {},
  };
});

vi.mock('openapi-client-axios', () => ({
  default: class OpenAPIClientAxios {
    constructor(config: unknown) {
      mocks.client(config);
    }

    init = () => mocks.init();
  },
}));

vi.mock('../providers/i18nProvider', () => ({
  LOCALE_STORAGE_NAME: 'RaStore.locale',
}));

const DOCUMENT = { openapi: '3.0.3', info: { title: 'mrmap', version: '1' }, paths: {} };

const networkError = Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK' });

const Probe = () => {
  const { status } = useHttpClientContext();
  return <span data-testid="status">{status}</span>;
};

const boot = () => render(<HttpClientBase><Probe /></HttpClientBase>);

const bootTwice = () => render(
  <>
    <HttpClientBase><Probe /></HttpClientBase>
    <HttpClientBase><Probe /></HttpClientBase>
  </>,
);

// The document memo lives on the module, for the lifetime of the application
// and not of a test - which is the whole point of it. Every test therefore
// boots in its own language, so it never inherits another test's memo.
beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  mocks.init.mockResolvedValue({ api: {} });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('HttpClientBase', () => {
  it('fetches the document once per locale for the whole application', async () => {
    localStorage.setItem(LOCALE_STORAGE_NAME, 'en');
    mocks.get.mockResolvedValue({ data: DOCUMENT });

    bootTwice();

    // two boots, one transfer, and each of them builds its client once - the
    // second init() per boot used to repeat the whole buildSchema (#1337)
    await waitFor(() => expect(mocks.client).toHaveBeenCalledTimes(2));
    expect(mocks.get).toHaveBeenCalledTimes(1);
    expect(mocks.init).toHaveBeenCalledTimes(2);

    const [url, config] = mocks.get.mock.calls[0];
    expect(url).toContain('/api/schema');
    expect(config.params).toEqual({ lang: 'en' });
    expect(config.headers['Accept-Language']).toBe('en');
    await waitFor(() => screen.getAllByText('ready'));
  });

  it('asks for the document in the language the ui shows', async () => {
    localStorage.setItem(LOCALE_STORAGE_NAME, 'de');
    mocks.get.mockResolvedValue({ data: DOCUMENT });

    boot();

    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
    expect(mocks.get.mock.calls[0][1].params).toEqual({ lang: 'de' });
  });

  it('waits progressively longer while the api is unreachable', async () => {
    vi.useFakeTimers();
    localStorage.setItem(LOCALE_STORAGE_NAME, 'fr');
    mocks.get.mockRejectedValue(networkError);

    boot();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(mocks.get).toHaveBeenCalledTimes(1);

    // the first wait is the 2 s of the old interval ...
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(mocks.get).toHaveBeenCalledTimes(2);

    // ... the second is twice that, so a cold backend is not asked for a
    // megabyte every two seconds while it is still generating (#1337)
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(mocks.get).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(mocks.get).toHaveBeenCalledTimes(3);

    expect(screen.getByTestId('status')).toHaveTextContent('error');
  });

  it('retries a failed fetch instead of reusing the rejected document', async () => {
    vi.useFakeTimers();
    localStorage.setItem(LOCALE_STORAGE_NAME, 'es');
    mocks.get
      .mockRejectedValueOnce(networkError)
      .mockResolvedValueOnce({ data: DOCUMENT });

    boot();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByTestId('status')).toHaveTextContent('error');

    // the memo has to let go of the rejected promise, or every later attempt
    // would be handed the same rejection and the boot could never recover
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(mocks.get).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByTestId('status')).toHaveTextContent('ready');
  });
});
