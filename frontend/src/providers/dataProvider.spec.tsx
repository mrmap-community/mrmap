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
