/**
 * Pins the scope the two #737 administration screens share, judged without
 * the network: the react-admin reads are stubbed, the permission snapshot of
 * #836 comes through the authProvider seam.
 *
 * - an organization administrator is offered only the organizations whose
 *   `organization_admin` role they hold; a platform holder (and a superuser)
 *   every one - the AC "a platform administrator can switch organization";
 * - the selection lives in the store and never outlives its validity: a
 *   stale or empty selection lands on the first administrable organization,
 *   or on none at all;
 * - the role rows of the selected organization carry their resolved
 *   definition (slug, label) and the member count of #736;
 * - `reloadSnapshot` invalidates the cached snapshot and re-reads it, which
 *   is what the self-revocation of the Members screen rides on.
 */
import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  OrganizationScopeProvider,
  useOrganizationScope,
  type OrganizationScope,
} from './OrganizationScopeContext';

const state = vi.hoisted(() => ({
  snapshot: undefined as {
    roles: string[];
    administeredOrganizationIds: string[];
    isSuperuser: boolean;
  } | undefined,
  snapshotReads: 0,
  invalidated: 0,
  organizations: [] as { id: string }[],
  organizationsPending: false,
  roleRows: [] as Record<string, unknown>[],
  definitions: [] as Record<string, unknown>[],
  storeValue: undefined as string | undefined,
}));

vi.mock('../../../../providers/authProvider', () => ({
  getPermissionSnapshot: () => {
    state.snapshotReads += 1;
    return state.snapshot === undefined
      ? undefined
      : Promise.resolve(state.snapshot);
  },
  invalidatePermissionSnapshot: () => { state.invalidated += 1; },
}));

vi.mock('react-admin', async () => {
  // the real useStore re-renders on a write; the stand-in keeps that property
  // through a genuine useState, while `state.storeValue` stays observable
  const { useState } = await vi.importActual<typeof import('react')>('react');
  return {
    useStore: (_key: string, initial: unknown) => {
      const [value, setValue] = useState(state.storeValue ?? initial);
      return [value, (next: string | undefined) => {
        state.storeValue = next;
        setValue(next);
      }];
    },
    useGetList: (resource: string) => resource === 'Organization'
      ? { data: state.organizations, isPending: state.organizationsPending }
      : { data: state.roleRows, isPending: false },
    useGetMany: (_resource: string, _params: unknown, _options: unknown) => ({
      data: state.definitions,
    }),
  };
});

/** Reads the live scope of the surrounding provider on every render. */
const Probe = ({ read }: { read: (scope: OrganizationScope) => void }) => {
  read(useOrganizationScope());
  return null;
};

const renderScope = () => {
  let scope!: OrganizationScope;
  render(
    <OrganizationScopeProvider>
      <Probe read={(value) => { scope = value; }} />
    </OrganizationScopeProvider>,
  );
  return () => scope;
};

beforeEach(() => {
  state.snapshot = undefined;
  state.snapshotReads = 0;
  state.invalidated = 0;
  state.organizations = [];
  state.organizationsPending = false;
  state.roleRows = [];
  state.definitions = [];
  state.storeValue = undefined;
});

describe('the organizations the scope offers', () => {
  it('offers an organization administrator only the organizations they administrate', async () => {
    state.snapshot = {
      roles: ['organization_admin'], administeredOrganizationIds: ['o1'], isSuperuser: false,
    };
    state.organizations = [{ id: 'o1' }, { id: 'o2' }];
    const scope = renderScope();

    await waitFor(() => expect(scope().snapshot).toBeDefined());
    expect(scope().organizations.map(o => String(o.id))).toEqual(['o1']);
    expect(scope().canAdminister).toBe(true);
  });

  it('offers a platform holder every organization - the organization switch of the AC', async () => {
    state.snapshot = {
      roles: ['platform_admin'], administeredOrganizationIds: [], isSuperuser: false,
    };
    state.organizations = [{ id: 'o1' }, { id: 'o2' }];
    const scope = renderScope();

    await waitFor(() => expect(scope().snapshot).toBeDefined());
    expect(scope().organizations.map(o => String(o.id))).toEqual(['o1', 'o2']);
    expect(scope().canAdminister).toBe(true);
  });

  it('offers a superuser every organization too', async () => {
    state.snapshot = { roles: [], administeredOrganizationIds: [], isSuperuser: true };
    state.organizations = [{ id: 'o1' }, { id: 'o2' }];
    const scope = renderScope();

    await waitFor(() => expect(scope().snapshot).toBeDefined());
    expect(scope().organizations).toHaveLength(2);
  });

  it('offers nothing to a caller without administration', async () => {
    state.snapshot = { roles: ['harvester'], administeredOrganizationIds: [], isSuperuser: false };
    state.organizations = [{ id: 'o1' }];
    const scope = renderScope();

    await waitFor(() => expect(scope().snapshot).toBeDefined());
    expect(scope().organizations).toEqual([]);
    expect(scope().canAdminister).toBe(false);
    expect(scope().organizationId).toBeUndefined();
  });
});

describe('the persisted selection', () => {
  it('adopts the first visible organization for an empty selection', async () => {
    state.snapshot = {
      roles: ['organization_admin'], administeredOrganizationIds: ['o2'], isSuperuser: false,
    };
    state.organizations = [{ id: 'o1' }, { id: 'o2' }];
    renderScope();

    await waitFor(() => expect(state.storeValue).toBe('o2'));
  });

  it('replaces a stored selection the caller no longer administrates', async () => {
    state.snapshot = {
      roles: ['organization_admin'], administeredOrganizationIds: ['o1'], isSuperuser: false,
    };
    state.organizations = [{ id: 'o1' }, { id: 'o2' }];
    // the store still holds the organization of a former administration role
    state.storeValue = 'o9';
    renderScope();

    await waitFor(() => expect(state.storeValue).toBe('o1'));
  });

  it('keeps a stored selection that is still valid', async () => {
    state.snapshot = {
      roles: ['platform_admin'], administeredOrganizationIds: [], isSuperuser: false,
    };
    state.organizations = [{ id: 'o1' }, { id: 'o2' }];
    state.storeValue = 'o2';
    const scope = renderScope();

    await waitFor(() => expect(scope().snapshot).toBeDefined());
    expect(scope().organizationId).toBe('o2');
  });
});

describe('the role rows of the selected organization', () => {
  it('joins each row with its definition and keeps the member count', async () => {
    state.snapshot = {
      roles: ['organization_admin'], administeredOrganizationIds: ['o1'], isSuperuser: false,
    };
    state.organizations = [{ id: 'o1' }];
    state.storeValue = 'o1';
    state.roleRows = [
      { id: 'r1', roleDefinition: { id: 'd1' }, memberCount: 3 },
      {
        // a row whose definition the join cannot answer reads unresolved,
        // it never invents a slug
        id: 'r2', roleDefinition: { id: 'd9' }, memberCount: 0,
      },
    ];
    state.definitions = [
      { id: 'd1', slug: 'organization_admin', label: 'Organization Admin' },
    ];
    const scope = renderScope();

    await waitFor(() => expect(scope().roles).toHaveLength(2));
    expect(scope().roles[0]).toEqual({
      id: 'r1',
      definitionId: 'd1',
      slug: 'organization_admin',
      label: 'Organization Admin',
      memberCount: 3,
    });
    expect(scope().roles[1].slug).toBe('');
    expect(scope().roles[1].memberCount).toBe(0);
  });
});

describe('reloadSnapshot', () => {
  it('invalidates the cached snapshot and reads it again', async () => {
    state.snapshot = {
      roles: ['organization_admin'], administeredOrganizationIds: ['o1'], isSuperuser: false,
    };
    state.organizations = [{ id: 'o1' }];
    const scope = renderScope();
    await waitFor(() => expect(scope().snapshot).toBeDefined());
    expect(state.snapshotReads).toBe(1);

    scope().reloadSnapshot();

    await waitFor(() => expect(state.invalidated).toBe(1));
    await waitFor(() => expect(state.snapshotReads).toBe(2));
    await waitFor(() => expect(scope().snapshot).toEqual(state.snapshot));
  });

  it('answers no snapshot and no options without a session', async () => {
    state.snapshot = undefined;
    state.organizations = [{ id: 'o1' }];
    const scope = renderScope();

    await waitFor(() => expect(scope().snapshot).toBeUndefined());
    expect(scope().organizations).toEqual([]);
    expect(scope().canAdminister).toBe(false);
    // the read seam still asks nothing while no session backs it
    expect(state.snapshotReads).toBe(1);
  });
});

describe('useOrganizationScope outside its provider', () => {
  it('refuses instead of answering a plausible empty scope', () => {
    const ConsoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    expect(() => render(<Probe read={() => undefined} />)).toThrow(
      /needs an OrganizationScopeProvider/,
    );
    ConsoleError.mockRestore();
  });
});
