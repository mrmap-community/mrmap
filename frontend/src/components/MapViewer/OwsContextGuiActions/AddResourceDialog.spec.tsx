import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AddResourceDialog from './AddResourceDialog';

const state = vi.hoisted(() => ({
  addWMSByUrl: vi.fn<(url: string, headers?: Headers) => void>(),
  setOpen: vi.fn<(open: boolean) => void>(),
}));

// the dialog is the unit under test, the context of the viewer only answers with the appended wms
vi.mock('../../../react-ows-lib/ContextProvider/OwsContextBase', () => ({
  useOwsContextBase: () => ({ addWMSByUrl: state.addWMSByUrl }),
}));

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
});
