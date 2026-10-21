import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import InitialFromOwsContextDialog from './InitialFromOwsContextDialog';

const state = vi.hoisted(() => ({
  initialFromOwsContext: vi.fn<(url: string) => void>(),
  setOpen: vi.fn<(open: boolean) => void>(),
}));

// the dialog is the unit under test, the context of the viewer only answers with the read document
vi.mock('../../../react-ows-lib/ContextProvider/OwsContextBase', () => ({
  useOwsContextBase: () => ({ initialFromOwsContext: state.initialFromOwsContext }),
}));

const contextUrl = 'https://context.example.test/ows-context/1/';

describe('InitialFromOwsContextDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('initializes the context with the entered capabilities url', () => {
    render(<InitialFromOwsContextDialog open setOpen={state.setOpen} />);

    fireEvent.change(screen.getByLabelText(/Get Capabilities Url/), { target: { value: contextUrl } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(state.initialFromOwsContext).toHaveBeenCalledWith(contextUrl);
    expect(state.setOpen).toHaveBeenCalledWith(false);
  });
});
