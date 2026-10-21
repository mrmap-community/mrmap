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
  encapsulateJsonApiPrimaryData: vi.fn(),
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
