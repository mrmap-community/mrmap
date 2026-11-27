/**
 * The resource-level access policy behind `authProvider.canAccess` (#836).
 *
 * react-admin asks `canAccess` on every component mount - menu entries, list
 * routes, create buttons - and react-query caches the answer per
 * (resource, action), so a network call inside the provider would run once
 * per resource per session at least, and the old `getPermissions` open item shows
 * how badly permission fetches interact with the login/logout render cycle.
 * The authProvider therefore fetches one permission snapshot next to
 * `getIdentity` and answers every check from it. This module is that answer:
 * a pure table - snapshot and request in, boolean out - so the policy of
 * which screen belongs to whom lives in exactly one readable place and vitest
 * can pin it without react-admin at all.
 */

export interface PermissionSnapshot {
  /**
   * The definition slugs of the roles the caller actively holds - resolved
   * by the authProvider from `who-am-i`'s role ids through the role API of
   * #736 (see `resolveAdministrationFromRoles`).
   */
  roles: string[],
  /**
   * The ids of the organizations whose `organization_admin` role the caller
   * actively holds; the scope the #737 administration screens offer to an
   * organization administrator. Empty for everybody else.
   */
  administeredOrganizationIds: string[],
  /**
   * Django's `is_superuser`, which the current `who-am-i` already answers as
   * `isSuperuser` - the break-glass signal beside the #736 roles.
   */
  isSuperuser: boolean
}

/** The snapshot a request without a session is judged against. */
export const ANONYMOUS_SNAPSHOT: PermissionSnapshot = {
  roles: [], administeredOrganizationIds: [], isSuperuser: false
}

/**
 * The screens that manage the platform, its accounts and its schedule. An
 * entry belongs here when opening it already reveals or lets change something
 * only an administrator may see - the #737 Members and Roles screens are the
 * `list` of the User and RoleDefinition resources named here, so they are
 * gated through the very same check. Everything not named here stays visible
 * to every logged-in user as today; the backend keeps enforcing the records.
 */
export const ADMINISTRATION_RESOURCES: ReadonlySet<string> = new Set([
  // accounts, as registered by components/Resource/Definition.tsx
  "User",
  "Organization",
  "Group",
  // platform administration and the scheduler
  "SystemInfo",
  "PeriodicTask",
  "CrontabSchedule",
  // the role resources #736 adds and #737 builds its screens on
  "Role",
  "RoleDefinition",
  "RoleMembership",
])

/**
 * The public read-only seam of #833: anonymously reachable `list`/`show`
 * resources - the kinds of service the backend answers for the anonymous
 * `anonymous_viewer` role once a record is explicitly published (#739's
 * `ROLE_MANAGED_MODELS`: WMS and WFS; catalogues stay private). The screen
 * itself only ever renders what the api answers, so this table names the
 * screens the frontend may open without a session; the deployment switch
 * `MRMAP_PERMISSION_FILTERED_LIST_MODELS` decides what those screens contain.
 */
export const PUBLIC_READ_RESOURCES: ReadonlySet<string> = new Set<string>([
  "WebMapService",
  "WebFeatureService",
])

/**
 * The role slugs that grant administration, named by the builtin catalogue
 * #736 seeded (`backend/accounts/migrations/0005_the_builtin_role_catalogue_is_seeded.py`).
 * `organization_admin` administers one organization - through the #836 table
 * it reaches the administration screens for the organization it holds the
 * role in, which is where its role rows point; `platform_admin` administers
 * the whole instance. The backend keeps enforcing every record either way, so
 * a coarser menu visibility here never opens a screen's data.
 */
export const ADMINISTRATION_ROLES: ReadonlySet<string> = new Set([
  "organization_admin",
  "platform_admin",
])

/** The slug whose role row, held for an organization, administers it. */
export const ORGANIZATION_ADMINISTRATION_ROLE = "organization_admin"

/** The slug that answers administration of the whole instance (#727 Q6). */
export const PLATFORM_ADMINISTRATION_ROLE = "platform_admin"

/** The snapshot-level actions; record-scoped refinement is #738's field. */
const READ_ACTIONS = new Set(["list", "show"])

/**
 * A react-admin action named as #738's `allowedActions` field spells it.
 * Actions missing here have no record-level spelling; their check stays at
 * the resource level instead of guessing what the backend would say.
 */
const RECORD_ACTION_NAMES: Record<string, string> = {
  list: "view",
  show: "view",
  edit: "change",
  delete: "delete",
}

export const hasAdministration = (
  snapshot: PermissionSnapshot,
  administrationRoles: ReadonlySet<string> = ADMINISTRATION_ROLES
): boolean =>
  snapshot.isSuperuser || snapshot.roles.some(role => administrationRoles.has(role))

/**
 * Whether the caller administers the whole instance rather than one
 * organization: the superuser flag or the active `platform_admin` role. The
 * #737 screens use it to offer every organization to the selector instead of
 * only the ones the caller administrates.
 */
export const isPlatformAdministration = (snapshot: PermissionSnapshot): boolean =>
  snapshot.isSuperuser || snapshot.roles.includes(PLATFORM_ADMINISTRATION_ROLE)

/**
 * Reads the permission-relevant members of the `who-am-i` answer. Roles
 * arrive as JSON:API resource identifiers (`relationships.roles.data`) which
 * carry role "row" ids, not definition slugs - the slugs are what this
 * module's tables name, and the authProvider resolves them through the role
 * API of #736 (`resolveAdministrationFromRoles`). Until that resolution ran,
 * `roles` stays empty and only `isSuperuser` answers administration.
 * `who-am-i` camelizes its member names (settings.py
 * JSON_API_FORMAT_FIELD_NAMES).
 */
export const permissionSnapshotFromWhoAmI = (body: unknown): PermissionSnapshot => {
  const data = (body as {
    data?: {
      attributes?: Record<string, unknown>
      relationships?: { roles?: { data?: unknown } }
    }
  } | undefined)?.data
  const attributes = data?.attributes ?? {}
  const rawRoles = attributes.roles ?? data?.relationships?.roles?.data
  const roles = Array.isArray(rawRoles)
    ? rawRoles
      .map(role =>
        typeof role === "string" ? role : (role as { name?: unknown })?.name
      )
      .filter((name): name is string => typeof name === "string")
    : []
  return {
    roles,
    administeredOrganizationIds: [],
    isSuperuser: attributes.isSuperuser === true
  }
}

/**
 * The ids of the role rows `who-am-i` answers for the caller - the input of
 * the slug resolution in the authProvider. An empty list means the caller
 * holds no role at all and the resolution has nothing to ask.
 */
export const callerRoleIdsFromWhoAmI = (body: unknown): string[] => {
  const rawRoles = (body as {
    data?: { relationships?: { roles?: { data?: unknown } } }
  } | undefined)?.data?.relationships?.roles?.data
  if (!Array.isArray(rawRoles)) {
    return []
  }
  return rawRoles
    .map(role =>
      typeof role === "string" ? role : (role as { id?: unknown })?.id
    )
    .filter((id): id is string => typeof id === "string")
}

/** The `data` member of a JSON:API collection answer; anything else - an
 * unanswered read included - reads as the empty list. */
const rawData = (body: unknown): {
  id?: string
  attributes?: Record<string, unknown>
  relationships?: Record<string, { data?: { id?: string } | null }>
}[] => {
  const data = (body as { data?: unknown } | undefined)?.data
  return Array.isArray(data) ? data as ReturnType<typeof rawData> : []
}

/**
 * The one Role relationship both reads of the slug resolution need: the
 * definition the row instantiates. `MrMap/settings.py` sets
 * `JSON_API_FORMAT_FIELD_NAMES = "camelize"`, so the API answers it as
 * `roleDefinition` - the same inflection this module already reads its
 * attributes under (`isActive`, `isSuperuser`) (#1803).
 */
const roleDefinitionIdOf = (role: {
  relationships?: Record<string, { data?: { id?: string } | null }>
}): string | undefined =>
  role.relationships?.roleDefinition?.data?.id

/**
 * The definition ids the caller's Role rows link to - the `filter[id.in]`
 * input of the second read of the slug resolution. An unanswered read answers
 * the empty list, which is what lets the caller skip that read instead of
 * asking it with an empty filter.
 */
export const roleDefinitionIdsOf = (rolesBody: unknown): string[] =>
  rawData(rolesBody)
    .map(roleDefinitionIdOf)
    .filter((id): id is string => typeof id === "string")

/**
 * Turns the two documents of the slug resolution - the caller's Role rows
 * (`GET /roles?filter[id.in]=...`) and their RoleDefinition rows
 * (`GET /roledefinitions?filter[id.in]=...`) - into the snapshot's role
 * slugs and administered organizations. Only active rows count: a retired
 * role grants nothing, which is the same rule the backend applies.
 * A Role whose definition is absent from the second answer contributes
 * nothing - the snapshot is judged by what the API actually answered.
 */
export const resolveAdministrationFromRoles = (
  rolesBody: unknown,
  definitionsBody: unknown
): Pick<PermissionSnapshot, "roles" | "administeredOrganizationIds"> => {
  const slugs = new Map<string, string>(
    rawData(definitionsBody)
      .filter(definition => typeof definition.attributes?.slug === "string")
      .map(definition => [definition.id!, definition.attributes!.slug as string])
  )
  const roles: string[] = []
  const administeredOrganizationIds: string[] = []
  for (const role of rawData(rolesBody)) {
    if (role.attributes?.isActive !== true) {
      continue
    }
    const slug = slugs.get(roleDefinitionIdOf(role) ?? "")
    if (slug === undefined) {
      continue
    }
    roles.push(slug)
    const organizationId = role.relationships?.organization?.data?.id
    if (slug === ORGANIZATION_ADMINISTRATION_ROLE && organizationId !== undefined) {
      administeredOrganizationIds.push(organizationId)
    }
  }
  return { roles, administeredOrganizationIds }
}

export interface AccessCheck {
  action: string
  resource: string
  /** The record react-admin checks a control for, if the check is record-scoped. */
  record?: Record<string, unknown>
  /** Whether a live, unexpired session backs the check. */
  authenticated: boolean
  snapshot: PermissionSnapshot
  /** Overridable for specs; production calls use the module's #736 table. */
  administrationRoles?: ReadonlySet<string>
}

/**
 * Answers one `canAccess` question. The precedence is the contract #836
 * accepted with #738: a record carrying the backend's `allowedActions` is
 * judged by that field alone - it already reflects publication, scoped roles
 * and ownership -; otherwise the decision is the resource table's, which is
 * also where anonymous requests are denied outside #833's public set.
 */
export const canAccessFromSnapshot = ({
  action,
  resource,
  record,
  authenticated,
  snapshot,
  administrationRoles = ADMINISTRATION_ROLES,
}: AccessCheck): boolean => {
  const allowedActions = record?.allowedActions
  if (Array.isArray(allowedActions)) {
    const actionName = RECORD_ACTION_NAMES[action]
    if (actionName !== undefined) {
      return allowedActions.includes(actionName)
    }
  }
  if (ADMINISTRATION_RESOURCES.has(resource)) {
    return hasAdministration(snapshot, administrationRoles)
  }
  if (!authenticated) {
    return PUBLIC_READ_RESOURCES.has(resource) && READ_ACTIONS.has(action)
  }
  return true
}
