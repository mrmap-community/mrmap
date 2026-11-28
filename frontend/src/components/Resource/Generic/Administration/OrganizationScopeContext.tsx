import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
  type ReactElement,
} from "react";
import { useGetList, useGetMany, useStore, type RaRecord } from "react-admin";

import {
  getPermissionSnapshot,
  invalidatePermissionSnapshot,
} from "../../../../providers/authProvider";
import {
  isPlatformAdministration,
  type PermissionSnapshot,
} from "../../../../providers/permissions";

/** One role row of the selected organization, with its resolved definition. */
export interface OrganizationRole {
  id: string,
  definitionId: string,
  slug: string,
  label: string,
  memberCount: number,
}

export interface OrganizationScope {
  /** The caller's resolved snapshot while it is still loading: `undefined`. */
  snapshot: PermissionSnapshot | undefined,
  /** The organizations the caller may pick: administered ones, all for a platform holder. */
  organizations: RaRecord[],
  loadingOrganizations: boolean,
  /** The selected organization, kept across the two #737 screens. */
  organizationId: string | undefined,
  setOrganizationId: (id: string | undefined) => void,
  /** The role rows of the selected organization, definitions resolved. */
  roles: OrganizationRole[],
  loadingRoles: boolean,
  /** Whether the caller administers the selected organization. */
  canAdminister: boolean,
  /** Re-reads the snapshot after the caller's own permissions changed. */
  reloadSnapshot: () => void,
}

const OrganizationScopeContext = createContext<OrganizationScope | null>(null);

/**
 * The page size of the organization and role reads. The selectors are
 * pickers, not pagers, and 100 is the `MAX_PAGE_SIZE` the API answers at
 * most (`MrMap/settings.py` JSON_API_PAGINATION) - an instance beyond a
 * hundred organizations would need a searchable picker, not this page.
 */
const SCOPE_PAGE_SIZE = 100;

const useOrganizationScopeState = (): OrganizationScope => {
  const [snapshot, setSnapshot] = useState<PermissionSnapshot | undefined>(undefined);
  const [snapshotNonce, setSnapshotNonce] = useState(0);
  useEffect(() => {
    let open = true;
    // no session answers no snapshot; the screens stay without options then,
    // which is what their access check leaves them anyway
    void getPermissionSnapshot()?.then(current => {
      if (open) {
        setSnapshot(current);
      }
    });
    return () => { open = false; };
  }, [snapshotNonce]);
  const reloadSnapshot = () => {
    invalidatePermissionSnapshot();
    setSnapshotNonce(nonce => nonce + 1);
  };

  const [organizationId, setOrganizationId] = useStore<string | undefined>(
    "administration.organization",
    undefined
  );

  const platform = snapshot !== undefined && isPlatformAdministration(snapshot);
  // every organization, ordered by its display string; the pickers of #1035
  // read `stringRepresentation` and so does this one
  const { data: allOrganizations, isPending: organizationsPending } = useGetList(
    "Organization",
    {
      pagination: { page: 1, perPage: SCOPE_PAGE_SIZE },
      sort: { field: "stringRepresentation", order: "ASC" },
    }
  );
  const organizations = useMemo<RaRecord[]>(() => {
    const rows = allOrganizations ?? [];
    if (snapshot === undefined) {
      return [];
    }
    return platform
      ? rows
      : rows.filter(organization =>
        snapshot.administeredOrganizationIds.includes(String(organization.id)));
  }, [allOrganizations, platform, snapshot]);

  const { data: roleRows, isPending: rolesPending } = useGetList(
    "Role",
    {
      pagination: { page: 1, perPage: SCOPE_PAGE_SIZE },
      sort: { field: "stringRepresentation", order: "ASC" },
      ...(organizationId !== undefined
        ? { meta: { relatedResource: { resource: "Organization", id: organizationId } } }
        : {}),
    },
    { enabled: organizationId !== undefined }
  );
  const definitionIds = useMemo(
    () => (roleRows ?? [])
      .map(row => (row.roleDefinition as { id?: string } | undefined)?.id)
      .filter((id): id is string => typeof id === "string"),
    [roleRows]
  );
  const { data: definitions } = useGetMany(
    "RoleDefinition",
    { ids: definitionIds },
    { enabled: definitionIds.length > 0 }
  );
  const roles = useMemo<OrganizationRole[]>(() =>
    (roleRows ?? []).map(row => {
      const definitionId = (row.roleDefinition as { id?: string } | undefined)?.id ?? "";
      const definition = (definitions ?? []).find(candidate => String(candidate.id) === definitionId);
      return {
        id: String(row.id),
        definitionId,
        slug: (definition?.slug as string | undefined) ?? "",
        label: (definition?.label as string | undefined) ?? "",
        memberCount: (row.memberCount as number | undefined) ?? 0,
      };
    }),
  [roleRows, definitions]);

  // the selection survives navigation between the two screens (the store),
  // but never outlives its own validity: an administrator who lost the role
  // - or an empty selection at all - lands on the first organization they do
  // administrate, or on none when they administrate none
  useEffect(() => {
    if (snapshot === undefined || organizationsPending) {
      return;
    }
    const valid = organizationId !== undefined
      && organizations.some(organization => String(organization.id) === organizationId);
    if (!valid) {
      setOrganizationId(organizations.length > 0 ? String(organizations[0].id) : undefined);
    }
  }, [organizations, organizationId, organizationsPending, setOrganizationId, snapshot]);

  const canAdminister = organizationId !== undefined && (
    platform
    || snapshot?.administeredOrganizationIds.includes(organizationId) === true
  );

  return {
    snapshot,
    organizations,
    loadingOrganizations: organizationsPending || snapshot === undefined,
    organizationId,
    setOrganizationId,
    roles,
    loadingRoles: rolesPending,
    canAdminister,
    reloadSnapshot,
  };
};

/**
 * The scope the #737 administration screens share: the selected organization,
 * the caller's place in it and the role rows of that organization. The
 * selection lives in the store so switching between Members and Roles keeps
 * it; the organization list is what the permission snapshot of #836 makes
 * visible - an organization administrator sees the organizations whose
 * `organization_admin` role they hold, a platform holder every one
 * (AC: "a platform administrator can switch organization").
 */
export const OrganizationScopeProvider = ({ children }: PropsWithChildren): ReactElement => {
  const scope = useOrganizationScopeState();
  return (
    <OrganizationScopeContext.Provider value={scope}>
      {children}
    </OrganizationScopeContext.Provider>
  );
};

/** The scope of the surrounding #737 screen; only inside its provider. */
export const useOrganizationScope = (): OrganizationScope => {
  const scope = useContext(OrganizationScopeContext);
  if (scope === null) {
    throw new Error("useOrganizationScope needs an OrganizationScopeProvider");
  }
  return scope;
};
