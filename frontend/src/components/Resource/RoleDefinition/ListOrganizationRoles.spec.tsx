/**
 * Pins the Roles screen of the #737 administration area: the definitions
 * catalogue annotated with the selected organization - the member counts of
 * #736 read off the organization's role rows, the permissions grouped per
 * model from the codenames the list answers *when the operation's `include`
 * enum declares them* (an include the schema does not name is a 400, so the
 * absence of the enum must not send one), falling back to the honest count.
 */
import type { ReactElement, ReactNode } from 'react';

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ListOrganizationRoles from './ListOrganizationRoles';

const state = vi.hoisted(() => ({
  scope: {
    organizationId: 'o1' as string | undefined,
    roles: [] as { id: string, definitionId: string, slug: string, label: string, memberCount: number }[],
  },
  schemaOperation: undefined as Record<string, unknown> | undefined,
  listProps: undefined as Record<string, unknown> | undefined,
  cellRecord: undefined as Record<string, unknown> | undefined,
}));

vi.mock('../Generic/Administration/OrganizationScopeContext', () => ({
  OrganizationScopeProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
  useOrganizationScope: () => state.scope,
}));

vi.mock('../Generic/Administration/OrganizationScopeSelect', () => ({
  default: () => <span>scope-select</span>,
}));

vi.mock('../../../jsonapi/components/ListGuesser', () => ({
  default: (props: Record<string, unknown>) => {
    state.listProps = props;
    return (
      <div data-testid="list">
        {props.header as ReactNode}
        {(props.columns as ReactElement[] | undefined)?.map((column, index) => (
          <div key={index}>{column}</div>
        ))}
      </div>
    );
  },
}));

vi.mock('../../../jsonapi/hooks/useResourceSchema', () => ({
  default: () => ({ operation: state.schemaOperation }),
}));

vi.mock('../../../jsonapi/hooks/useFieldsForOperation', () => ({
  useFieldsForOperation: () => [
    { props: { source: 'id' }, component: ({ source }: { source: string }) => <span>{source}</span> },
    { props: { source: 'slug' }, component: ({ source }: { source: string }) => <span>{source}</span> },
    { props: { source: 'label' }, component: ({ source }: { source: string }) => <span>{source}</span> },
    { props: { source: 'description' }, component: ({ source }: { source: string }) => <span>{source}</span> },
  ],
}));

// only `getIncludeOptions` is a runtime member of this module for the
// screen; the include enum of the real schema is the contract, the mock
// answers it per test
vi.mock('../../../jsonapi/utils', () => ({
  getIncludeOptions: (operation?: Record<string, unknown>) =>
    (operation?.__include as string[] | undefined) ?? [],
}));

vi.mock('react-admin', () => ({
  useTranslate: () => (key: string) => key,
  // the schema grid hands a record to each cell; the spec answers one
  FunctionField: ({ label, render }: {
    label?: string,
    render: (record: Record<string, unknown>) => ReactNode,
  }) => (
    <div>
      <span>{label}</span>
      {render(state.cellRecord as Record<string, unknown>)}
    </div>
  ),
}));

beforeEach(() => {
  state.scope = {
    organizationId: 'o1',
    roles: [
      { id: 'r1', definitionId: 'd1', slug: 'organization_admin', label: '', memberCount: 3 },
      { id: 'r2', definitionId: 'd2', slug: 'harvester', label: '', memberCount: 0 },
    ],
  };
  state.schemaOperation = { __include: ['permissions'] };
  state.listProps = undefined;
  state.cellRecord = {
    id: 'd1',
    permissions: [
      { id: 'p1', codename: 'view_user' },
      { id: 'p2', codename: 'change_user' },
      { id: 'p3', codename: 'view_roledefinition' },
    ],
  };
});

describe('the include of permissions', () => {
  it('asks for the include only because the operation enum declares it', () => {
    render(<ListOrganizationRoles />);
    expect(state.listProps?.queryOptions).toEqual({
      meta: { jsonApiParams: { include: 'permissions' } },
    });
  });

  it('sends no include the schema does not declare - the backend answers 400', () => {
    state.schemaOperation = {};
    render(<ListOrganizationRoles />);
    expect(state.listProps?.queryOptions).toBeUndefined();
  });

  it('sends none while the schema is not loaded at all', () => {
    state.schemaOperation = undefined;
    render(<ListOrganizationRoles />);
    expect(state.listProps?.queryOptions).toBeUndefined();
  });
});

describe('the columns', () => {
  it('names slug, label and description explicitly, in order', () => {
    render(<ListOrganizationRoles />);
    const columns = state.listProps?.columns as ReactElement[];
    expect(columns).toHaveLength(5);
    const schemaSources = columns.slice(0, 3)
      .map(column => (column.props as { source: string }).source);
    expect(schemaSources).toEqual(['slug', 'label', 'description']);
  });

  it('counts the members of the selected organization per definition', () => {
    render(<ListOrganizationRoles />);
    expect(screen.getByText('administration.roles.members')).toBeInTheDocument();
    // the record on trial is the definition d1 - held by three members
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('answers zero for a definition nobody in the organization holds', () => {
    state.cellRecord = { id: 'd2', permissions: [] };
    render(<ListOrganizationRoles />);
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('groups the permissions per model with their actions', () => {
    render(<ListOrganizationRoles />);
    expect(screen.getByText('administration.roles.permissions')).toBeInTheDocument();
    expect(screen.getByText('user')).toBeInTheDocument();
    expect(screen.getByText('roledefinition')).toBeInTheDocument();
    // the actions of the user model: view and change
    expect(screen.getAllByText('view')).toHaveLength(2);
    expect(screen.getByText('change')).toBeInTheDocument();
  });

  it('falls back to the honest count when the rows carry no codenames', () => {
    state.cellRecord = { id: 'd1', permissions: [{ id: 'p1' }, { id: 'p2' }] };
    render(<ListOrganizationRoles />);
    expect(screen.getByText('administration.roles.permissionCount')).toBeInTheDocument();
    expect(screen.queryByText('user')).not.toBeInTheDocument();
  });

  it('counts zero without a permissions member at all', () => {
    state.cellRecord = { id: 'd1' };
    render(<ListOrganizationRoles />);
    expect(screen.getByText('administration.roles.permissionCount')).toBeInTheDocument();
  });
});

describe('the screen frame', () => {
  it('sorts by slug and puts the organization selector above the grid', () => {
    render(<ListOrganizationRoles />);
    expect(state.listProps?.resource).toBe('RoleDefinition');
    expect(state.listProps?.sort).toEqual({ field: 'slug', order: 'ASC' });
    expect(screen.getByText('scope-select')).toBeInTheDocument();
  });
});
