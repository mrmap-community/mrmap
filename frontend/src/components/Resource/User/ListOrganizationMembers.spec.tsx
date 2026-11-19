/**
 * Pins the wiring of the #737 Members screen: it lists the User resource
 * through the organization's own member collection (the nested operation of
 * #736, not a filtered `list_User`), names its columns explicitly with the
 * roles column as the chip cell, offers "add member" instead of a plain
 * "create user" - and only to someone who administrates the selection. The
 * rows carry the assign control, and the toolbar offers the audit trail of the
 * memberships (#741).
 */
import type { ReactElement, ReactNode } from 'react';
import { WrapperField } from 'react-admin';

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ListOrganizationMembers from './ListOrganizationMembers';
import MemberRolesCell from './MemberRolesCell';

const state = vi.hoisted(() => ({
  scope: { organizationId: 'o1', canAdminister: true },
  listProps: undefined as Record<string, unknown> | undefined,
}));

vi.mock('../Generic/Administration/OrganizationScopeContext', () => ({
  OrganizationScopeProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
  useOrganizationScope: () => state.scope,
}));

vi.mock('../Generic/Administration/OrganizationScopeSelect', () => ({
  default: () => <span>scope-select</span>,
}));

// its own spec pins the target of the link; this screen pins that it offers it
vi.mock('../Generic/History/HistoryChangelogLink', () => ({
  default: () => <span>membership-audit-link</span>,
}));

vi.mock('../../../jsonapi/components/ListGuesser', () => ({
  default: (props: Record<string, unknown>) => {
    state.listProps = props;
    return <div data-testid="list">{props.header as ReactNode}</div>;
  },
}));

vi.mock('../../../jsonapi/hooks/useFieldsForOperation', () => ({
  useFieldsForOperation: () => [
    { props: { source: 'id' }, component: 'span' },
    { props: { source: 'username' }, component: 'span' },
    { props: { source: 'stringRepresentation' }, component: 'span' },
    { props: { source: 'organization' }, component: 'span' },
  ],
}));

vi.mock('../../Lists/CustomListActions', () => ({
  default: ({ createButton, additionalActions }: {
    createButton?: unknown,
    additionalActions?: ReactNode,
  }) => (
    <div data-testid="actions">
      {createButton === false && <span>no-create-button</span>}
      {additionalActions}
    </div>
  ),
}));

vi.mock('./AddMemberDialogButton', () => ({ default: () => <span>add-member</span> }));
vi.mock('./AssignRoleButton', () => ({ default: () => <span>assign-role</span> }));
vi.mock('./MemberRolesCell', () => ({
  default: ({ label }: { label?: string }) => <span>roles-cell:{label}</span>,
}));

vi.mock('react-admin', () => ({
  useTranslate: () => (key: string) => key,
  WrapperField: ({ children }: { children?: ReactNode }) => <>{children}</>,
}));

beforeEach(() => {
  state.scope = { organizationId: 'o1', canAdminister: true };
  state.listProps = undefined;
});

describe('the list', () => {
  it('reads users through the selected organization member collection', () => {
    render(<ListOrganizationMembers />);
    expect(state.listProps?.resource).toBe('User');
    expect(state.listProps?.relatedResource).toEqual({ resource: 'Organization', id: 'o1' });
    expect(state.listProps?.sort).toEqual({ field: 'username', order: 'ASC' });
  });

  it('names the columns: the user identity fields, then the roles chips', () => {
    render(<ListOrganizationMembers />);
    const columns = state.listProps?.columns as ReactElement[];
    // no raw id column and no organization relationship column
    expect(columns).toHaveLength(3);
    expect(columns[2].type).toBe(MemberRolesCell);
    expect((columns[2].props as { label: string }).label)
      .toBe('administration.members.roles');
  });

  it('carries the assign control on the rows and the scope selector in the header', () => {
    render(<ListOrganizationMembers />);
    expect(screen.getByText('scope-select')).toBeInTheDocument();

    const rowActions = state.listProps?.rowActions as ReactElement;
    expect(rowActions.type).toBe(WrapperField);
    // the assign button renders inside it - the same element the row builds
    const { unmount } = render(rowActions);
    expect(screen.getByText('assign-role')).toBeInTheDocument();
    unmount();
  });
});

describe('the toolbar', () => {
  it('offers add member to an administrator instead of a create button', () => {
    render(<ListOrganizationMembers />);
    const actions = state.listProps?.actions as ReactElement;

    const { unmount } = render(actions);
    expect(screen.getByText('no-create-button')).toBeInTheDocument();
    // the member dialog renders inside, the plain create_User does not exist here
    expect(screen.getByText('add-member')).toBeInTheDocument();
    expect(screen.getByText('membership-audit-link')).toBeInTheDocument();
    unmount();
  });

  it('offers no member action to a caller who does not administrate', () => {
    state.scope = { organizationId: 'o1', canAdminister: false };
    render(<ListOrganizationMembers />);
    const actions = state.listProps?.actions as ReactElement;

    const { unmount } = render(actions);
    expect(screen.getByText('no-create-button')).toBeInTheDocument();
    expect(screen.queryByText('add-member')).not.toBeInTheDocument();
    unmount();
  });
});
