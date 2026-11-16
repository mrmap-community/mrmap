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
   * The caller's role names as `who-am-i` will carry them once #736 extends
   * it; empty while the endpoint does not answer roles yet.
   */
  roles: string[],
  /**
   * Django's `is_superuser`, which the current `who-am-i` already answers as
   * `isSuperuser` - the only administration signal available before #736.
   */
  isSuperuser: boolean
}

/** The snapshot a request without a session is judged against. */
export const ANONYMOUS_SNAPSHOT: PermissionSnapshot = { roles: [], isSuperuser: false }

/**
 * The screens that manage the platform, its accounts and its schedule. An
 * entry belongs here when opening it already reveals or lets change something
 * only an administrator may see - #737's Members and Roles screens are the
 * next of them, so the resource names #736 introduces are listed now and
 * cannot ship ungated. Everything not named here stays visible to every
 * logged-in user as today; the backend keeps enforcing the records.
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
 * resources. Empty until #833 chooses the published set; until then every
 * anonymous check is denied, which is what `requireAuth` enforces anyway.
 */
export const PUBLIC_READ_RESOURCES: ReadonlySet<string> = new Set<string>([])

/**
 * The role names that grant administration. Empty until #736 names the
 * builtin catalogue; tests inject their set through `administrationRoles` to
 * pin the wiring, and wiring #736 means filling this one table.
 */
export const ADMINISTRATION_ROLES: ReadonlySet<string> = new Set<string>([])

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
 * Reads the permission-relevant members of the `who-am-i` answer, tolerating
 * both shapes #736 may deliver roles in - attributes or a JSON:API
 * relationship - and answers the empty roles list while neither exists.
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
  return { roles, isSuperuser: attributes.isSuperuser === true }
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
