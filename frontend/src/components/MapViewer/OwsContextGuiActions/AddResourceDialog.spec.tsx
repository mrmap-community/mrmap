import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AddResourceDialog from './AddResourceDialog';

const state = vi.hoisted(() => ({
  addWMSByUrl: vi.fn<(url: string, headers?: Headers) => void>(),
  addWFSByUrl: vi.fn<(url: string, headers?: Headers) => void>(),
  setOpen: vi.fn<(open: boolean) => void>(),
}));

// the dialog is the unit under test, the context of the viewer only answers with the appended wms
vi.mock('../../../react-ows-lib/ContextProvider/OwsContextBase', () => ({
  useOwsContextBase: () => ({ addWMSByUrl: state.addWMSByUrl, addWFSByUrl: state.addWFSByUrl }),
}));

vi.mock('react-admin', () => ({ useTranslate: () => (key: string) => ({
  'viewerAdd.title': 'Add map service', 'viewerAdd.description': 'Enter a capabilities URL.',
  'viewerAdd.protocol': 'Service type', 'viewerAdd.url': 'Get Capabilities Url',
  'viewerAdd.username': 'Username (optional)', 'viewerAdd.password': 'Password (optional)',
  'ra.action.cancel': 'Cancel', 'ra.action.add': 'Add',
} as Record<string, string>)[key] ?? key }));

const capabilitiesUrl = 'https://wms.example.test/ows?SERVICE=WMS&REQUEST=GetCapabilities';

const enterCapabilitiesUrl = () => {
  fireEvent.change(screen.getByLabelText(/Get Capabilities Url/), { target: { value: capabilitiesUrl } });
};

describe('AddResourceDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('appends the wms of the entered capabilities url', () => {
    render(<AddResourceDialog open setOpen={state.setOpen} />);

    enterCapabilitiesUrl();
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(state.addWMSByUrl).toHaveBeenCalledWith(capabilitiesUrl, undefined);
    expect(state.setOpen).toHaveBeenCalledWith(false);
  });

  it('passes entered credentials as basic authorization header', () => {
    render(<AddResourceDialog open setOpen={state.setOpen} />);

    enterCapabilitiesUrl();
    fireEvent.change(screen.getByLabelText(/Username/), { target: { value: 'reader' } });
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: 'test-password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    const [url, headers] = state.addWMSByUrl.mock.calls[0];
    expect(url).toBe(capabilitiesUrl);
    expect(headers?.get('Authorization')).toBe(`Basic ${btoa('reader:test-password')}`);
  });

  it('appends a WFS using the selected service type and preserves credentials', () => {
    render(<AddResourceDialog open setOpen={state.setOpen} />);
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Service type' }));
    fireEvent.click(screen.getByRole('option', { name: 'WFS' }));
    const wfsUrl = 'https://wfs.example.test/ows?SERVICE=WFS&REQUEST=GetCapabilities';
    fireEvent.change(screen.getByLabelText(/Get Capabilities Url/), { target: { value: wfsUrl } });
    fireEvent.change(screen.getByLabelText(/Username/), { target: { value: 'reader' } });
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(state.addWMSByUrl).not.toHaveBeenCalled();
    const [url, headers] = state.addWFSByUrl.mock.calls[0];
    expect(url).toBe(wfsUrl);
    expect(headers?.get('Authorization')).toBe(`Basic ${btoa('reader:secret')}`);
    expect(state.setOpen).toHaveBeenCalledWith(false);
  });
});
