/**
 * Pins the row-level "assign role" control of the #737 Members screen: the
 * offer list is the selected organization's role rows the member does not
 * hold yet, and assigning posts the membership into that role's own
 * collection (`create_related_RoleMembership_of_Role`), never a plain
 * `create_RoleMembership`. A refused write (the backend decides who may
 * assign, #736) is a notification, not a silent local change.
 */
import type { ReactNode } from 'react';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AssignRoleButton from './AssignRoleButton';

const state = vi.hoisted(() => ({
  record: undefined as Record<string, unknown> | undefined,
  scope: {
    roles: [] as { id: string, slug: string, label: string }[],
    canAdminister: true,
  },
  formValues: {} as Record<string, unknown>,
  create: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
  invalidate: vi.fn(),
}));

vi.mock('../Generic/Administration/OrganizationScopeContext', () => ({
  useOrganizationScope: () => state.scope,
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: state.invalidate }),
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
  SimpleForm: ({ id, onSubmit, children }: {
    id?: string,
    onSubmit?: (values: Record<string, unknown>) => unknown,
    children?: ReactNode,
  }) => (
    <form
      id={id}
      data-testid="assign-form"
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit?.(state.formValues);
      }}
    >
      {children}
    </form>
  ),
  // the choice list is what the component computed; picking one stands in
  // for the select interaction the real react-hook-form would carry
  SelectInput: ({ choices }: { choices?: { id: string, name: string }[] }) => (
    <>
      {(choices ?? []).map(choice => (
        <button
          key={choice.id}
          onClick={() => { state.formValues.role = choice.id; }}
        >
          pick-{choice.name}
        </button>
      ))}
    </>
  ),
  useCreate: () => [state.create],
  useNotify: () => state.notify,
  useRecordContext: () => state.record,
  useRefresh: () => state.refresh,
  useTranslate: () => (key: string) => key,
}));

beforeEach(() => {
  state.record = { id: '42', username: 'ada', roles: [{ id: 'r1' }] };
  state.scope = {
    roles: [
      { id: 'r1', slug: 'organization_admin', label: 'Organization Admin' },
      { id: 'r2', slug: 'harvester', label: '' },
    ],
    canAdminister: true,
  };
  state.formValues = {};
  state.create = vi.fn().mockResolvedValue({ data: { id: 'm1' } });
  state.notify = vi.fn();
  state.refresh = vi.fn();
  state.invalidate = vi.fn();
});

const openDialog = () => {
  fireEvent.click(screen.getByText('administration.members.assign'));
  return screen.getByTestId('assign-form');
};

describe('the offer list', () => {
  it('offers the organization roles the member does not hold yet', () => {
    render(<AssignRoleButton />);
    openDialog();
    expect(screen.getByText('pick-harvester')).toBeInTheDocument();
    // held already - assigning it again would only fail at the server
    expect(screen.queryByText('pick-Organization Admin')).not.toBeInTheDocument();
    expect(screen.queryByText('pick-organization_admin')).not.toBeInTheDocument();
  });

  it('falls back to the definition slug when a definition carries no label', () => {
    state.scope = {
      roles: [{ id: 'r2', slug: 'harvester', label: '' }],
      canAdminister: true,
    };
    render(<AssignRoleButton />);
    openDialog();
    expect(screen.getByText('pick-harvester')).toBeInTheDocument();
  });

  it('is not there for a caller who does not administrate', () => {
    state.scope = { roles: state.scope.roles, canAdminister: false };
    render(<AssignRoleButton />);
    expect(screen.queryByText('administration.members.assign')).not.toBeInTheDocument();
  });

  it('is not there when there is nothing left to offer', () => {
    state.scope = {
      roles: [{ id: 'r1', slug: 'organization_admin', label: '' }],
      canAdminister: true,
    };
    render(<AssignRoleButton />);
    expect(screen.queryByText('administration.members.assign')).not.toBeInTheDocument();
  });
});

describe('the assign itself', () => {
  it('posts the membership into the chosen role collection', async () => {
    render(<AssignRoleButton />);
    openDialog();
    fireEvent.click(screen.getByText('pick-harvester'));
    fireEvent.submit(screen.getByTestId('assign-form'));

    await waitFor(() => expect(state.create).toHaveBeenCalledWith(
      'RoleMembership',
      {
        data: { role: { id: 'r2' }, user: { id: '42' } },
        meta: { relatedResource: { resource: 'Role', id: 'r2' } },
      },
      { returnPromise: true },
    ));
  });

  it('names the assigned role, re-reads the members list and closes', async () => {
    render(<AssignRoleButton />);
    openDialog();
    fireEvent.click(screen.getByText('pick-harvester'));
    fireEvent.submit(screen.getByTestId('assign-form'));

    await waitFor(() => expect(state.notify).toHaveBeenCalledWith(
      'administration.members.assigned',
      { type: 'success', messageArgs: { role: 'harvester' } },
    ));
    // the chips read the roles the members list answers per row, so that
    // collection alone is re-read - no global refresh (#1464)
    expect(state.invalidate).toHaveBeenCalledWith({ queryKey: ['User', 'getList'] });
    expect(state.refresh).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId('assign-form')).not.toBeInTheDocument());
  });

  it('reports a refusal and keeps the dialog', async () => {
    state.create = vi.fn().mockRejectedValue(new Error('403'));
    render(<AssignRoleButton />);
    openDialog();
    fireEvent.click(screen.getByText('pick-harvester'));
    fireEvent.submit(screen.getByTestId('assign-form'));

    await waitFor(() => expect(state.notify).toHaveBeenCalledWith(
      'administration.members.assignFailed',
      { type: 'error' },
    ));
    expect(state.invalidate).not.toHaveBeenCalled();
    expect(state.refresh).not.toHaveBeenCalled();
    expect(screen.getByTestId('assign-form')).toBeInTheDocument();
  });

  it('sends nothing while no role is chosen', async () => {
    render(<AssignRoleButton />);
    openDialog();
    fireEvent.submit(screen.getByTestId('assign-form'));

    await waitFor(() => expect(state.create).not.toHaveBeenCalled());
    expect(state.notify).not.toHaveBeenCalled();
  });
});
