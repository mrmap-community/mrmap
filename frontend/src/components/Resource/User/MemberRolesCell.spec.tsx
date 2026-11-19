/**
 * Pins the role chips of one member row of the #737 Members screen:
 *
 * - one chip per role the member holds in the selected organization, labelled
 *   by its definition slug, with the raw id for a role the scope cannot
 *   resolve - the chip never invents a name;
 * - revoking addresses the membership row through its two sides (the
 *   declared `role` and `user` filters of `/memberships`) and deletes it;
 * - only a caller who administrates the organization gets the revoke control;
 * - revoking the caller's own `organization_admin` role refreshes the
 *   permission snapshot and react-admin's cached access answers, and when no
 *   administration is left, the screen is left behind with a warning instead
 *   of standing there as a broken table (bound Q9 of #727).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MemberRolesCell from './MemberRolesCell';

const state = vi.hoisted(() => ({
  record: undefined as Record<string, unknown> | undefined,
  identity: { id: '42' } as { id: string } | undefined,
  scope: {
    roles: [] as { id: string, slug: string }[],
    canAdminister: true,
    reloadSnapshot: vi.fn(),
  },
  getList: vi.fn(),
  del: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
  navigate: vi.fn(),
  invalidate: vi.fn(),
  freshSnapshot: undefined as unknown,
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => state.navigate,
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: state.invalidate }),
}));

vi.mock('../../../providers/authProvider', () => ({
  getPermissionSnapshot: () =>
    state.freshSnapshot === undefined ? undefined : Promise.resolve(state.freshSnapshot),
}));

vi.mock('../Generic/Administration/OrganizationScopeContext', () => ({
  useOrganizationScope: () => state.scope,
}));

vi.mock('react-admin', () => ({
  useRecordContext: () => state.record,
  useGetIdentity: () => ({ data: state.identity }),
  useDataProvider: () => ({ getList: state.getList, delete: state.del }),
  useNotify: () => state.notify,
  useRefresh: () => state.refresh,
  useTranslate: () => (key: string) => key,
}));

/** The revoke control MUI renders into the chip for its delete action. */
const revokeIcon = (index = 0) =>
  screen.getAllByTestId('CloseIcon')[index];

const held = (roleIds: string[]) => ({
  roles: roleIds.map(id => ({ id })),
});

beforeEach(() => {
  state.record = { id: '42', username: 'ada', ...held(['r2']) };
  state.identity = { id: '42' };
  state.scope = {
    roles: [{ id: 'r2', slug: 'harvester' }],
    canAdminister: true,
    reloadSnapshot: vi.fn(),
  };
  state.getList = vi.fn().mockResolvedValue({ data: [{ id: 'm1' }] });
  state.del = vi.fn().mockResolvedValue({});
  state.notify = vi.fn();
  state.refresh = vi.fn();
  state.navigate = vi.fn();
  state.invalidate = vi.fn();
  state.freshSnapshot = undefined;
});

describe('the chips', () => {
  it('labels each held role by its definition, unresolved roles by their id', () => {
    state.record = { id: '42', ...held(['r2', 'rX']) };
    render(<MemberRolesCell />);
    expect(screen.getByText('harvester')).toBeInTheDocument();
    expect(screen.getByText('rX')).toBeInTheDocument();
  });

  it('says so when the member holds no role', () => {
    state.record = { id: '42', roles: [] };
    render(<MemberRolesCell />);
    expect(screen.getByText('administration.members.noRoles')).toBeInTheDocument();
  });

  it('offers revoke to a caller who administrates the organization', () => {
    render(<MemberRolesCell />);
    expect(screen.getAllByTestId('CloseIcon')).toHaveLength(1);
  });

  it('offers no revoke to a caller who does not administrate', () => {
    state.scope = { ...state.scope, canAdminister: false };
    render(<MemberRolesCell />);
    expect(screen.queryByTestId('CloseIcon')).not.toBeInTheDocument();
  });
});

describe('the revoke', () => {
  it('addresses the membership by its two sides and deletes that row', async () => {
    render(<MemberRolesCell />);
    fireEvent.click(revokeIcon());

    await waitFor(() => expect(state.del).toHaveBeenCalledWith('RoleMembership', { id: 'm1' }));
    expect(state.getList).toHaveBeenCalledWith('RoleMembership', {
      pagination: { page: 1, perPage: 1 },
      sort: { field: 'id', order: 'ASC' },
      filter: { role: 'r2', user: '42' },
    });
    await waitFor(() => expect(state.notify).toHaveBeenCalledWith(
      'administration.members.revoked',
      { type: 'success', messageArgs: { role: 'harvester' } },
    ));
    expect(state.refresh).toHaveBeenCalled();
    expect(state.navigate).not.toHaveBeenCalled();
  });

  it('reports a missing membership row as a failed revoke', async () => {
    state.getList = vi.fn().mockResolvedValue({ data: [] });
    render(<MemberRolesCell />);
    fireEvent.click(revokeIcon());

    await waitFor(() => expect(state.notify).toHaveBeenCalledWith(
      'administration.members.revokeFailed',
      { type: 'error' },
    ));
    expect(state.del).not.toHaveBeenCalled();
  });

  it('reports a refused revoke without touching the snapshot', async () => {
    state.getList = vi.fn().mockRejectedValue(new Error('403'));
    render(<MemberRolesCell />);
    fireEvent.click(revokeIcon());

    await waitFor(() => expect(state.notify).toHaveBeenCalledWith(
      'administration.members.revokeFailed',
      { type: 'error' },
    ));
    expect(state.del).not.toHaveBeenCalled();
    expect(state.scope.reloadSnapshot).not.toHaveBeenCalled();
  });
});

describe('revoking the caller own administration role', () => {
  beforeEach(() => {
    state.record = { id: '42', ...held(['r1']) };
    state.scope = {
      roles: [{ id: 'r1', slug: 'organization_admin' }],
      canAdminister: true,
      reloadSnapshot: vi.fn(),
    };
  });

  it('leaves the screen behind when no administration is left', async () => {
    state.freshSnapshot = {
      roles: [], administeredOrganizationIds: [], isSuperuser: false,
    };
    render(<MemberRolesCell />);
    fireEvent.click(revokeIcon());

    await waitFor(() => expect(state.navigate).toHaveBeenCalledWith('/'));
    expect(state.scope.reloadSnapshot).toHaveBeenCalledTimes(1);
    expect(state.invalidate).toHaveBeenCalledWith({ queryKey: ['canAccess'] });
    expect(state.notify).toHaveBeenCalledWith(
      'administration.members.selfRevoked',
      { type: 'warning' },
    );
    // the success wording of an ordinary revoke is not shown on top
    expect(state.notify).not.toHaveBeenCalledWith(
      'administration.members.revoked',
      expect.anything(),
    );
    expect(state.refresh).not.toHaveBeenCalled();
  });

  it('stays an ordinary revoke when administration is kept elsewhere', async () => {
    state.freshSnapshot = {
      roles: ['platform_admin'], administeredOrganizationIds: [], isSuperuser: false,
    };
    render(<MemberRolesCell />);
    fireEvent.click(revokeIcon());

    await waitFor(() => expect(state.notify).toHaveBeenCalledWith(
      'administration.members.revoked',
      { type: 'success', messageArgs: { role: 'organization_admin' } },
    ));
    expect(state.navigate).not.toHaveBeenCalled();
    expect(state.scope.reloadSnapshot).toHaveBeenCalledTimes(1);
  });

  it('leaves another caller row alone - the snapshot belongs to the actor, not to the member', async () => {
    state.identity = { id: '7' };
    render(<MemberRolesCell />);
    fireEvent.click(revokeIcon());

    await waitFor(() => expect(state.notify).toHaveBeenCalledWith(
      'administration.members.revoked',
      expect.anything(),
    ));
    expect(state.scope.reloadSnapshot).not.toHaveBeenCalled();
    expect(state.navigate).not.toHaveBeenCalled();
  });

  it('treats a non-administration self role as an ordinary revoke', async () => {
    state.record = { id: '42', ...held(['r2']) };
    render(<MemberRolesCell />);
    fireEvent.click(revokeIcon());

    await waitFor(() => expect(state.refresh).toHaveBeenCalled());
    expect(state.scope.reloadSnapshot).not.toHaveBeenCalled();
  });
});
