import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AddResourceDialog from './AddResourceDialog';

const state = vi.hoisted(() => ({
  addWMSByUrl: vi.fn<(url: string, headers?: Headers) => void>(),
  addWFSByUrl: vi.fn<(url: string, headers?: Headers) => void>(),
  addServiceByUrl: vi.fn<(url: string, headers?: Headers) => void>(),
  setOpen: vi.fn<(open: boolean) => void>(),
}));

// the dialog is the unit under test, the context of the viewer only answers with the appended wms
vi.mock('../../../react-ows-lib/ContextProvider/OwsContextBase', () => ({
  useOwsContextBase: () => ({
    addWMSByUrl: state.addWMSByUrl,
    addWFSByUrl: state.addWFSByUrl,
    addServiceByUrl: state.addServiceByUrl,
  }),
}));
vi.mock('react-admin', () => ({
  useTranslate: () => (key: string) => key,
}));

const capabilitiesUrl = 'https://wms.example.test/ows?SERVICE=WMS&REQUEST=GetCapabilities';

const enterCapabilitiesUrl = () => {
  fireEvent.change(screen.getByLabelText(/addResource.url/), { target: { value: capabilitiesUrl } });
};

describe('AddResourceDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('appends the wms of the entered capabilities url', () => {
    render(<AddResourceDialog open setOpen={state.setOpen} />);

    enterCapabilitiesUrl();
    fireEvent.click(screen.getByRole('button', { name: 'ra.action.add' }));

    expect(state.addServiceByUrl).toHaveBeenCalledWith(capabilitiesUrl, undefined);
    expect(state.setOpen).toHaveBeenCalledWith(false);
  });

  it('routes an explicitly chosen protocol to the matching append', () => {
    render(<AddResourceDialog open setOpen={state.setOpen} />);

    enterCapabilitiesUrl();
    fireEvent.mouseDown(screen.getByLabelText('addResource.protocol'));
    fireEvent.click(screen.getByRole('option', { name: 'WFS' }));
    fireEvent.click(screen.getByRole('button', { name: 'ra.action.add' }));

    expect(state.addWFSByUrl).toHaveBeenCalledWith(capabilitiesUrl, undefined);
    expect(state.addServiceByUrl).not.toHaveBeenCalled();
  });

  it('passes entered credentials as basic authorization header', () => {
    render(<AddResourceDialog open setOpen={state.setOpen} />);

    enterCapabilitiesUrl();
    fireEvent.change(screen.getByLabelText('addResource.username'), { target: { value: 'reader' } });
    fireEvent.change(screen.getByLabelText('addResource.password'), { target: { value: 'test-password' } });
    fireEvent.click(screen.getByRole('button', { name: 'ra.action.add' }));

    const [url, headers] = state.addServiceByUrl.mock.calls[0];
    expect(url).toBe(capabilitiesUrl);
    expect(headers?.get('Authorization')).toBe(`Basic ${btoa('reader:test-password')}`);
  });
});