/**
 * Pins the "add member" control of the #737 Members screen: it is only there
 * for someone who administrates the selected organization, and what it sends
 * is the resource-identifier payload `POST /organizations/{id}/members` asks
 * for (#736) - not a plain `create_User`. The user search input stands in as
 * a stub; the dialog machinery around it is the shared one.
 */
import type { ReactNode } from 'react';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AddMemberDialogButton from './AddMemberDialogButton';

const state = vi.hoisted(() => ({
  scope: { organizationId: 'o1' as string | undefined, canAdminister: true },
  formValues: {} as Record<string, unknown>,
  create: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock('../Generic/Administration/OrganizationScopeContext', () => ({
  useOrganizationScope: () => state.scope,
}));

// the user search reads the schema of its reference through the jsonapi
// layer; here it stands in for a choice the screen already had in hand
vi.mock('../../../jsonapi/components/SchemaAutocompleteInput', () => ({
  default: () => (
    <button
      onClick={() => {
        state.formValues.user = { id: 'u9', stringRepresentation: 'ada' };
      }}
    >
      choose-user
    </button>
  ),
}));

vi.mock('react-admin', () => ({
  Button: ({
    label,
    children,
    onClick,
    type,
    disabled,
    form,
  }: {
    label?: string,
    children?: ReactNode,
    onClick?: () => void,
    type?: "button" | "submit" | "reset",
    disabled?: boolean,
    form?: string,
  }) => (
    <button onClick={onClick} type={type} disabled={disabled} form={form}>
      {label ?? children}
    </button>
  ),
  ResourceContextProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
  // the form carries the dialog's submit button; values arrive from the stub
  SimpleForm: ({ id, onSubmit, children }: {
    id?: string,
    onSubmit?: (values: Record<string, unknown>) => unknown,
    children?: ReactNode,
  }) => (
    <form
      id={id}
      data-testid="member-form"
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit?.(state.formValues);
      }}
    >
      {children}
    </form>
  ),
  useCreate: () => [state.create],
  useNotify: () => state.notify,
  useRefresh: () => state.refresh,
  useTranslate: () => (key: string) => key,
}));

const openDialog = () => {
  fireEvent.click(screen.getByText('administration.members.add'));
  return screen.getByTestId('member-form');
};

beforeEach(() => {
  state.scope = { organizationId: 'o1', canAdminister: true };
  state.formValues = {};
  state.create = vi.fn().mockResolvedValue({ data: { id: 'u9' } });
  state.notify = vi.fn();
  state.refresh = vi.fn();
});

describe('visibility', () => {
  it('is not there for a caller who does not administrate the organization', () => {
    state.scope = { organizationId: 'o1', canAdminister: false };
    render(<AddMemberDialogButton />);
    expect(screen.queryByText('administration.members.add')).not.toBeInTheDocument();
  });

  it('is not there while no organization is selected', () => {
    state.scope = { organizationId: undefined, canAdminister: false };
    render(<AddMemberDialogButton />);
    expect(screen.queryByText('administration.members.add')).not.toBeInTheDocument();
  });

  it('opens the dialog with the shared title', () => {
    render(<AddMemberDialogButton />);
    openDialog();
    expect(screen.getByText('administration.members.addTitle')).toBeInTheDocument();
  });
});

describe('the add itself', () => {
  it('posts the chosen user as member of the selected organization', async () => {
    render(<AddMemberDialogButton />);
    openDialog();

    fireEvent.click(screen.getByText('choose-user'));
    fireEvent.submit(screen.getByTestId('member-form'));

    await waitFor(() => expect(state.create).toHaveBeenCalled());
    expect(state.create).toHaveBeenCalledWith(
      'User',
      {
        data: { id: 'u9' },
        meta: { relatedResource: { resource: 'Organization', id: 'o1' } },
      },
      { returnPromise: true },
    );
  });

  it('names the added user, refreshes the list and closes', async () => {
    render(<AddMemberDialogButton />);
    openDialog();
    fireEvent.click(screen.getByText('choose-user'));
    fireEvent.submit(screen.getByTestId('member-form'));

    await waitFor(() => expect(state.notify).toHaveBeenCalledWith(
      'administration.members.added',
      { type: 'success', messageArgs: { user: 'ada' } },
    ));
    expect(state.refresh).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId('member-form')).not.toBeInTheDocument());
  });

  it('reports a refusal without closing - the server stays the last word', async () => {
    state.create = vi.fn().mockRejectedValue(new Error('403'));
    render(<AddMemberDialogButton />);
    openDialog();
    fireEvent.click(screen.getByText('choose-user'));
    fireEvent.submit(screen.getByTestId('member-form'));

    await waitFor(() => expect(state.notify).toHaveBeenCalledWith(
      'administration.members.addFailed',
      { type: 'error' },
    ));
    expect(state.refresh).not.toHaveBeenCalled();
    expect(screen.getByTestId('member-form')).toBeInTheDocument();
  });

  it('sends nothing without a chosen user', async () => {
    render(<AddMemberDialogButton />);
    openDialog();
    fireEvent.submit(screen.getByTestId('member-form'));

    await waitFor(() => expect(state.create).not.toHaveBeenCalled());
    expect(state.notify).not.toHaveBeenCalled();
  });
});
