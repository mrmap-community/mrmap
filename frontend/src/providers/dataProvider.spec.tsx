import type OpenAPIClientAxios from 'openapi-client-axios';

import { AdminContext, Create, Edit, HttpError, SimpleForm, TextInput } from 'react-admin';

import { fireEvent, render, screen } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import { describe, expect, it, vi } from 'vitest';

import GlobalFormError from '../jsonapi/components/GlobalFormError';
import dataProvider from './dataProvider';

vi.mock('./authProvider', () => ({ getAuthToken: () => undefined }));
vi.mock('./i18nProvider', () => ({ default: { getLocale: () => 'en' } }));
vi.mock('../jsonapi/utils', () => ({
  capsulateJsonApiPrimaryData: (data: unknown) => data,
  encapsulateJsonApiDocumentData: vi.fn(),
  encapsulateJsonApiPrimaryData: (_: unknown, data: unknown) => data,
}));

const globalMessage = 'There is an existing harvesting job for this service.';
type ApiError = { detail: string; source?: { pointer?: string }; status?: string; code?: string };

const makeProvider = (errors: ApiError[]) => {
  const error = new AxiosError('Request failed with status code 400', 'ERR_BAD_REQUEST', undefined, undefined, {
    data: { errors }, status: 400, statusText: 'Bad Request', headers: {},
    config: { headers: new AxiosHeaders() },
  });
  const request = vi.fn().mockRejectedValue(error);
  const getAxiosConfigForOperation = vi.fn(() => ({}));
  const httpClient = {
    getOperation: vi.fn(() => ({})),
    getAxiosConfigForOperation,
    axiosConfigDefaults: {},
    client: { request, api: { getAxiosConfigForOperation } },
  } as unknown as OpenAPIClientAxios;
  return dataProvider({ httpClient });
};

describe('JSON:API validation errors', () => {
  it.each(['create', 'update'] as const)('maps global and field errors for %s', async (method) => {
    const provider = makeProvider([
      { detail: globalMessage, status: '400', code: 'unique', source: { pointer: '/data' } },
      { detail: 'Invalid title', source: { pointer: '/data/attributes/title' } },
      { detail: 'Invalid service', source: { pointer: '/data/relationships/service' } },
      { detail: 'Invalid ID', source: { pointer: '/data/id' } },
    ]);
    const params = { id: 1, data: { title: 'New title' }, previousData: { id: 1 } };
    const submission = method === 'create'
      ? provider.create('HarvestingJob', params)
      : provider.update('HarvestingJob', params);
    await expect(submission).rejects.toMatchObject({
      status: 400,
      body: { errors: {
        root: { serverError: globalMessage },
        title: 'Invalid title', service: 'Invalid service', id: 'Invalid ID',
      } },
    });
  });

  it.each([undefined, {}, { pointer: '' }])('handles errors without a field pointer (%j)', async (source) => {
    const provider = makeProvider([{ detail: globalMessage, source }]);
    await expect(provider.create('HarvestingJob', { data: {} })).rejects.toMatchObject({
      body: { errors: { root: { serverError: globalMessage } } },
    });
  });

  // the record editor's findings rail needs the untouched error members:
  // the rule id, severity and ISO family survive beside the mapped messages
  it('hands the raw json:api error members through on the body', async () => {
    const findingError = {
      detail: 'CI-0160: extent missing', status: '400', code: 'invalid',
      source: { pointer: '/data/attributes/extent' },
      rule: 'CI-0160', severity: 'warning', meta: { family: 'extents' },
    };
    const provider = makeProvider([findingError]);
    await expect(provider.update('DatasetMetadataRecord', { id: 1, data: {}, previousData: { id: 1 } }))
      .rejects.toMatchObject({
        body: { jsonApiErrors: [findingError] },
      });
  });

  it('retains multiple global error messages', async () => {
    const provider = makeProvider([
      { detail: globalMessage, source: { pointer: '/data' } },
      { detail: 'Another validation error', source: { pointer: '/data' } },
    ]);
    await expect(provider.create('HarvestingJob', { data: {} })).rejects.toMatchObject({
      body: { errors: { root: { serverError: `${globalMessage}\nAnother validation error` } } },
    });
  });

  it('throws an HttpError for a bad request', async () => {
    const provider = makeProvider([]);
    await expect(provider.create('HarvestingJob', { data: {} })).rejects.toBeInstanceOf(HttpError);
  });

  it.each(['create', 'update'] as const)('displays the global error in a %s form', async (method) => {
    const provider = makeProvider([{ detail: globalMessage, source: { pointer: '/data' } }]);
    const record = { id: 1, title: 'Harvesting job' };
    provider.getOne = vi.fn().mockResolvedValue({ data: record });
    const form = <SimpleForm defaultValues={{ title: record.title }}><GlobalFormError /><TextInput source="title" /></SimpleForm>;
    render(
      <AdminContext dataProvider={provider}>
        {method === 'create'
          ? <Create resource="HarvestingJob" redirect={false}>{form}</Create>
          : <Edit resource="HarvestingJob" id={1} mutationMode="pessimistic" redirect={false}>{form}</Edit>}
      </AdminContext>
    );
    const title = await screen.findByRole('textbox');
    fireEvent.change(title, { target: { value: 'Changed title' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    expect(await screen.findByText(globalMessage)).toBeVisible();
    expect(screen.getByRole('textbox')).toHaveValue('Changed title');
  });
});

/**
 * The nested create of the #737 administration screens: adding a member and
 * assigning a role post into a related collection (`POST
 * /organizations/{id}/members`, `POST /roles/{id}/memberships`), so the
 * parent must reach the operation as its path parameter - the plain
 * `create_User` route would create a user instead of adding one.
 */
describe('create into a related collection', () => {
  const makeCreateProvider = () => {
    const request = vi.fn().mockResolvedValue({ data: { data: { id: 'u9' } } });
    const getAxiosConfigForOperation =
      vi.fn<(operationId: string, args: unknown[]) => unknown>(() => ({}));
    const getOperation = vi.fn(() => ({}));
    const httpClient = {
      getOperation,
      getAxiosConfigForOperation,
      axiosConfigDefaults: {},
      client: { request, api: { getAxiosConfigForOperation } },
    } as unknown as OpenAPIClientAxios;
    return { provider: dataProvider({ httpClient }), request, getAxiosConfigForOperation, getOperation };
  };

  it('posts to the related collection named by the meta parent', async () => {
    const { provider, getAxiosConfigForOperation } = makeCreateProvider();

    await provider.create('User', {
      data: { id: 'u9' },
      meta: { relatedResource: { resource: 'Organization', id: 'o1' } },
    });

    const [operationId, args] = getAxiosConfigForOperation.mock.calls[0];
    expect(operationId).toBe('create_related_User_of_Organization');
    expect(args[0]).toEqual({ OrganizationId: 'o1' });
    // the body is the user's resource identifier; the mocked capsulate is the identity
    expect(args[1]).toEqual({ data: { id: 'u9' } });
  });

  it('names the role parent of a membership assign with its own path parameter', async () => {
    const { provider, getAxiosConfigForOperation } = makeCreateProvider();

    await provider.create('RoleMembership', {
      data: { role: { id: 'r2' }, user: { id: 'u9' } },
      meta: { relatedResource: { resource: 'Role', id: 'r2' } },
    });

    const [operationId, args] = getAxiosConfigForOperation.mock.calls[0];
    expect(operationId).toBe('create_related_RoleMembership_of_Role');
    expect(args[0]).toEqual({ RoleId: 'r2' });
  });

  it('keeps a create without meta on the plain operation', async () => {
    const { provider, getAxiosConfigForOperation } = makeCreateProvider();

    await provider.create('User', { data: { username: 'ada' } });

    const [operationId, args] = getAxiosConfigForOperation.mock.calls[0];
    expect(operationId).toBe('create_User');
    expect(args[0]).toBeUndefined();
  });

  it('refuses to write without its parent instead of posting a malformed path', async () => {
    const { provider, request, getOperation } = makeCreateProvider();

    // the screens can hold an unresolved selection at runtime - the scope of
    // #737 answers `undefined` until the caller's organizations arrived; the
    // type names an id, so the runtime case has to be simulated here
    await expect(provider.create('User', {
      data: { id: 'u9' },
      meta: { relatedResource: { resource: 'Organization', id: undefined } as never },
    })).rejects.toThrow(/unresolved 'Organization' parent/);

    expect(request).not.toHaveBeenCalled();
    expect(getOperation).not.toHaveBeenCalled();
  });
});

/**
 * The failures which carry no answer at all: the catch of `create` read
 * `error.response.status` on every error, so a backend which never answered -
 * an unreachable host, a timeout - surfaced as a TypeError instead of the
 * error the screen can name. `update` and `custom` already guard with
 * `axios.isAxiosError`; `create` does the same now (#1463).
 */
describe('a request which never got an answer', () => {
  const makeRejectingProvider = (error: unknown) => {
    const request = vi.fn().mockRejectedValue(error);
    const getAxiosConfigForOperation = vi.fn(() => ({}));
    const httpClient = {
      getOperation: vi.fn(() => ({})),
      getAxiosConfigForOperation,
      axiosConfigDefaults: {},
      client: { request, api: { getAxiosConfigForOperation } },
    } as unknown as OpenAPIClientAxios;
    return { provider: dataProvider({ httpClient }), request };
  };

  it.each(['create', 'update'] as const)('lets the error of %s through unharmed', async (method) => {
    const networkError = new Error('Network Error');
    const { provider } = makeRejectingProvider(networkError);

    const submission = method === 'create'
      ? provider.create('HarvestingJob', { data: { title: 'Harvesting run' } })
      : provider.update('HarvestingJob', { id: 1, data: { title: 'Harvesting run' }, previousData: { id: 1 } });

    await expect(submission).rejects.toBe(networkError);
  });

  it('does not mistake an axios error without a response for a bad request', async () => {
    const timeout = new AxiosError('timeout of 5000ms exceeded', 'ECONNABORTED');
    const { provider } = makeRejectingProvider(timeout);

    await expect(provider.create('HarvestingJob', { data: {} })).rejects.toBe(timeout);
  });
});

/**
 * A resource the schema gives no `retrieve_` operation for has no record to
 * answer; the call used to swallow that and return `{ data: [] }` - an array
 * where a record belongs - so the screen showed an empty record instead of
 * failing (#1463, the family of #948 and #1034).
 */
describe('getOne of a resource without a retrieve operation', () => {
  const makeProvider = (getAxiosConfigForOperation: ReturnType<typeof vi.fn>) => {
    const request = vi.fn().mockResolvedValue({ data: { data: { id: '7', type: 'HarvestingJob' } } });
    const httpClient = {
      getOperation: vi.fn(() => undefined),
      getAxiosConfigForOperation,
      axiosConfigDefaults: {},
      client: { request, api: { getAxiosConfigForOperation } },
    } as unknown as OpenAPIClientAxios;
    return { provider: dataProvider({ httpClient }), request };
  };

  it('answers HttpError 404 instead of an array in place of the record', async () => {
    const throwing = vi.fn(() => {
      throw new Error('Operation not found.');
    });
    const { provider, request } = makeProvider(throwing);

    const retrieval = provider.getOne('HarvestingJob', { id: '7' });
    await expect(retrieval).rejects.toBeInstanceOf(HttpError);
    await expect(retrieval).rejects.toMatchObject({ status: 404 });
    await expect(retrieval).rejects.toThrow(/retrieve_HarvestingJob/);
    expect(request).not.toHaveBeenCalled();
  });

  it('still reads the record while the operation does exist', async () => {
    const { provider } = makeProvider(vi.fn(() => ({})));

    await expect(provider.getOne('HarvestingJob', { id: '7' }))
      .resolves.toMatchObject({ data: { id: '7' } });
  });
});

describe('realtime subscriptions', () => {
  // the transport contract of issue #1209: the backend only delivers to the
  // connections which subscribed to a topic (notify/consumers.py), so the
  // provider has to mirror its local subscriptions onto the socket - and
  // re-announce them over every new socket, because a reconnect happens on a
  // fresh connection which knows none of them (RealtimeBus re-attaches).
  const provider = makeProvider([]);

  type FakeSocket = {
    readyState: number;
    send: ReturnType<typeof vi.fn>;
    onmessage: ((event: MessageEvent) => void) | null;
  };
  const socketIn = (readyState: number): FakeSocket => ({
    readyState,
    send: vi.fn(),
    onmessage: null,
  });

  const framesSent = (socket: FakeSocket) =>
    socket.send.mock.calls.map(([frame]) => JSON.parse(String(frame)));
  const subscribedTopics = (socket: FakeSocket) =>
    framesSent(socket)
      .filter(frame => frame.action === 'subscribe')
      .map(frame => frame.topic);

  const attach = (socket: FakeSocket) =>
    provider.attachRealtimeOnMessage(socket as unknown as WebSocket);

  it('announces a topic subscribed while the socket connects when it opens', async () => {
    const connecting = socketIn(WebSocket.CONNECTING);
    await attach(connecting);
    const observer = vi.fn();
    const topic = 'resource/BackgroundProcess/11111111-1111-4111-8111-111111111111';

    await provider.subscribe(topic, observer);
    expect(connecting.send).not.toHaveBeenCalled();

    const opened = socketIn(WebSocket.OPEN);
    await attach(opened);
    expect(framesSent(opened)).toEqual([{ action: 'subscribe', topic }]);

    await provider.unsubscribe(topic, observer);
  });

  it('joins a topic once for all its observers and leaves it with the last', async () => {
    const socket = socketIn(WebSocket.OPEN);
    await attach(socket);
    const first = vi.fn();
    const second = vi.fn();
    const topic = 'resource/HarvestingJob';

    await provider.subscribe(topic, first);
    await provider.subscribe(topic, second);
    expect(subscribedTopics(socket)).toEqual([topic]);

    await provider.unsubscribe(topic, first);
    expect(framesSent(socket)).toEqual([{ action: 'subscribe', topic }]);

    await provider.unsubscribe(topic, second);
    expect(framesSent(socket)).toEqual([
      { action: 'subscribe', topic },
      { action: 'unsubscribe', topic },
    ]);
  });

  it('dispatches a bus message only to the observers of its topic', async () => {
    const socket = socketIn(WebSocket.OPEN);
    await attach(socket);
    const watcher = vi.fn();
    const bystander = vi.fn();
    const record = { type: 'BackgroundProcess', id: '7', attributes: { phase: 'running' } };

    await provider.subscribe('resource/BackgroundProcess/7', watcher);
    await provider.subscribe('resource/BackgroundProcess/8', bystander);

    socket.onmessage?.({
      data: JSON.stringify({
        topic: 'resource/BackgroundProcess/7',
        event: { type: 'updated', payload: { ids: ['7'], records: [record] } },
      }),
    } as MessageEvent);

    expect(watcher).toHaveBeenCalledWith({
      type: 'updated',
      payload: { ids: ['7'], records: [record] },
    });
    expect(bystander).not.toHaveBeenCalled();

    await provider.unsubscribe('resource/BackgroundProcess/7', watcher);
    await provider.unsubscribe('resource/BackgroundProcess/8', bystander);
  });

  it('replays every live subscription to each new socket', async () => {
    const keep = vi.fn();
    const alsoKeep = vi.fn();
    const first = socketIn(WebSocket.OPEN);
    await attach(first);
    await provider.subscribe('resource/BackgroundProcess/keep', keep);
    await provider.subscribe('resource/BackgroundProcess/alsoKeep', alsoKeep);

    // the socket of RealtimeBus dies; the hook re-attaches a new one, whose
    // send is a fresh mock - everything observed must be announced again or
    // the reloaded screen goes silent until its next refetch
    const second = socketIn(WebSocket.OPEN);
    await attach(second);
    expect(subscribedTopics(second)).toEqual([
      'resource/BackgroundProcess/keep',
      'resource/BackgroundProcess/alsoKeep',
    ]);

    await provider.unsubscribe('resource/BackgroundProcess/keep', keep);
    await provider.unsubscribe('resource/BackgroundProcess/alsoKeep', alsoKeep);
  });
});
