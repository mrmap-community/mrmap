import { UserIdentity, type AuthProvider } from 'ra-core';

import { API_BASE_URL } from '../context/HttpClientContext';
import {
  ANONYMOUS_SNAPSHOT,
  callerRoleIdsFromWhoAmI,
  canAccessFromSnapshot,
  permissionSnapshotFromWhoAmI,
  resolveAdministrationFromRoles,
  roleDefinitionIdsOf,
  type PermissionSnapshot,
} from './permissions';

/** Name of the CSRF cookie Django answers (#835); `MrMap/settings.py` keeps it
 * readable on purpose, so a SPA can repeat its value in the header below. */
export const CSRF_COOKIE_NAME = 'csrftoken'

/** Header Django reads the repeated value from (`CSRF_HEADER_NAME` in the same
 * file). Both names are one contract with the backend, so they are named once
 * here and nowhere else. */
export const CSRF_HEADER_NAME = 'X-CSRFToken'

/**
 * The value of the CSRF cookie, or `undefined` when this browser has none yet.
 *
 * This is *not* a credential: it identifies no caller and grants nothing
 * without the session cookie, which JavaScript cannot read (#835). It is the
 * double-submit half of Django's CSRF protection, and every state-changing
 * request of this SPA carries it - the axios calls get it from the axios
 * defaults of `HttpClientContext`, the `fetch` calls of this file from here.
 */
export const getCsrfToken = (): string | undefined =>
  document.cookie
    .split('; ')
    .find(entry => entry.startsWith(`${CSRF_COOKIE_NAME}=`))
    ?.slice(CSRF_COOKIE_NAME.length + 1)

/** The header pair a state-changing `fetch` of this file needs. */
const csrfHeaders = (): Record<string, string> => {
  const token = getCsrfToken()
  return token ? {[CSRF_HEADER_NAME]: token} : {}
}


export interface LoginParams {
  username: string
  password: string
}


/**
 * What this browser remembers about its session (#835): who the user is and
 * that a session was opened here. The credential itself is absent by design -
 * it is the `HttpOnly` cookie the browser sends on its own, which is exactly
 * what the pre-#835 `localStorage` token was not.
 */
export interface AuthSession extends UserIdentity {
  openedAt: string
}


interface WhoAmIResult {
  identity: UserIdentity
  permissions: PermissionSnapshot
}

/** GETs one JSON:API collection with the session cookie this file already
 * uses for `who-am-i`; any failure - unreachable, refused, unexpected body -
 * answers `undefined` so the caller can degrade instead of failing the login. */
const fetchJsonApi = async (url: string): Promise<unknown> => {
  const request = new Request(url, {
    method: 'GET',
    credentials: 'include',
    headers: new Headers({
      'content-type': 'application/vnd.api+json'
    })
  })
  try {
    const response = await fetch(request)
    return response.ok ? await response.json() : undefined
  } catch {
    return undefined
  }
}

/**
 * Resolves the role ids `who-am-i` answers into definition slugs through the
 * role API of #736: `GET /roles?filter[id.in]=...` for the caller's role rows
 * and `GET /roledefinitions?filter[id.in]=...` for their slugs. Both lists
 * answer their `id` filter declared, both are readable by every authenticated
 * caller (`RoleAccessPermission`, `IsAuthenticatedReadOnlyOrPlatform`) - the
 * resolution asks nothing the caller may not read anyway. An unanswered step
 * degrades to the unresolved snapshot: without slugs only the superuser flag
 * grants administration, and the backend keeps enforcing every record.
 *
 * The URLs are written without the trailing slash (#1803): the accounts router
 * is a `NestedDefaultRouter(trailing_slash=False)` (`accounts/urls.py`), which
 * answers `/api/accounts/roles` and refuses `/api/accounts/roles/` - the same
 * shape `dataProvider.ts` already builds its `filter[id.in]` reads in.
 */
const resolveRoles = async (
  base: PermissionSnapshot,
  roleIds: string[],
): Promise<PermissionSnapshot> => {
  if (roleIds.length === 0) {
    return base
  }
  const rolesUrl = `${API_BASE_URL}/api/accounts/roles?filter[id.in]=${encodeURIComponent(roleIds.join(','))}`
  const rolesBody = await fetchJsonApi(rolesUrl)
  const definitionIds = roleDefinitionIdsOf(rolesBody)
  // without a single definition id the second read can only ask an empty
  // `in` filter, which the API answers 400 - the snapshot is what the first
  // read supports, so the request is left out instead of being fired (#1803)
  const definitionsBody = definitionIds.length === 0
    ? undefined
    : await fetchJsonApi(
      `${API_BASE_URL}/api/accounts/roledefinitions?filter[id.in]=${encodeURIComponent(definitionIds.join(','))}`
    )
  const resolved = resolveAdministrationFromRoles(rolesBody, definitionsBody)
  return {
    ...base,
    roles: [...new Set([...base.roles, ...resolved.roles])],
    administeredOrganizationIds: resolved.administeredOrganizationIds,
  }
}

const whoAmI = async (url: string): Promise<WhoAmIResult> => {

  const request = new Request(url, {
    method: 'GET',
    credentials: 'include',
    headers: new Headers({
      'content-type': 'application/vnd.api+json'
    })
  })

  const response = await fetch(request)
  if (response.ok) {
    const responseJson = await response.json()
    const name = [responseJson.data.attributes.firstName, responseJson.data.attributes.lastName]

    const fullName = name.filter(n => n !== undefined).join(" ")

    const userIdentity: UserIdentity = {
      id: responseJson.data.id,
      fullName: fullName !== " " && fullName || responseJson.data.attributes.username
    }
    // the role ids `who-am-i` carries become slugs through the two role API
    // reads of #736; identity and roles are one login, so this belongs here
    const permissions = await resolveRoles(
      permissionSnapshotFromWhoAmI(responseJson),
      callerRoleIdsFromWhoAmI(responseJson)
    )
    return { identity: userIdentity, permissions }
  }
  return { identity: {id: 0}, permissions: ANONYMOUS_SNAPSHOT }
}

/**
 * Asks the backend to close the server-side session (#832 for the browser,
 * #835 for how it is opened).
 *
 * ``DELETE /api/auth/session`` flushes the session row, so a cookie copied out
 * of this browser before the logout - by a malicious extension, a shared
 * browser or a leaked request - answers nothing afterwards. The request carries
 * the CSRF header: an unsafe request which the session authenticates is refused
 * without it, which is the price of a cookie the browser attaches by itself.
 *
 * Neither a rejected request nor an unreachable backend is reported: the caller
 * clears the local state either way, because a logout which depends on the
 * server would leave the user looking at the app with a session their browser
 * no longer carries.
 */
const closeSession = async (logoutUrl: string) => {
  const request = new Request(logoutUrl, {
    method: 'DELETE',
    credentials: 'include',
    headers: new Headers(csrfHeaders())
  })

  try {
    await fetch(request)
  } catch {
    // offline: the local logout below is all that can happen
  }
}

/** The key the frontend before #835 kept its knox token under. */
const LEGACY_TOKEN_LOCAL_STORAGE_NAME = "mrmap.auth"

/**
 * One-time rollout step of the browser migration (#835): a browser which
 * arrives from the previous frontend still carries the token that frontend put
 * in `localStorage`. That credential is reusable, readable by any script on
 * this page and now useless to the SPA, so it is revoked at the backend (which
 * deletes exactly that token row, #832) and dropped. Best effort in both
 * directions: an unreachable backend must not block the login page, and a
 * refused revocation means the row was already gone.
 *
 * Nothing here asks the user: the session they get afterwards is a new one, and
 * the machine clients of the same account keep their own tokens, which never
 * lived in this browser's storage.
 */
const revokeLegacyBrowserToken = async (legacyLogoutUrl: string) => {
  const stored = localStorage.getItem(LEGACY_TOKEN_LOCAL_STORAGE_NAME)
  if (stored === null || stored === undefined) {
    return
  }
  let token: string | undefined
  try {
    token = (JSON.parse(stored) as { token?: string }).token
  } catch {
    token = undefined
  }
  localStorage.removeItem(LEGACY_TOKEN_LOCAL_STORAGE_NAME)
  if (!token) {
    return
  }
  try {
    await fetch(new Request(legacyLogoutUrl, {
      method: 'POST',
      credentials: 'include',
      headers: new Headers({Authorization: `Token ${token}`})
    }))
  } catch {
    // unreachable: the row ages out on its own and the browser is clean anyway
  }
}

export const AUTH_SESSION_LOCAL_STORAGE_NAME = "mrmap.session"

/**
 * The session marker of this browser - identity plus the fact that a session
 * was opened here, never a credential (#835). Absent means the login page.
 */
export const getSession = (): AuthSession | undefined => {
  const stored = localStorage.getItem(AUTH_SESSION_LOCAL_STORAGE_NAME)
  if (stored === undefined || stored === null){
    return undefined
  } else {
    return JSON.parse(stored)
  }
}

/**
 * The seam the #737 administration screens use to ask who they are allowed
 * to administer, without going through react-admin's access checks. The
 * provider instance registers itself here when it is built - the application
 * builds exactly one, and a screen asking without a live session gets
 * `undefined` instead of a stale snapshot.
 */
let snapshotAccess: {
  current: () => Promise<PermissionSnapshot> | undefined
  invalidate: () => void
} | undefined

/** The caller's resolved permission snapshot, or `undefined` without session. */
export const getPermissionSnapshot = (): Promise<PermissionSnapshot> | undefined =>
  snapshotAccess?.current()

/**
 * Drops the cached snapshot so the next `canAccess` - and the next
 * `getPermissionSnapshot` - fetches anew. The Members screen calls it after
 * revoking the caller's own role (bound Q9 of #727: revocation refreshes the
 * permission-aware UI immediately); the backend stays authoritative either
 * way. react-admin caches its access answers per (resource, action), so a
 * caller that wants the menu to update invalidates those queries too.
 */
export const invalidatePermissionSnapshot = (): void => {
  snapshotAccess?.invalidate()
}

/**
 * Why the session ended, as a translation key (#834): `auth.sessionExpired`
 * when the server stopped accepting this browser's session - its lifetime ran
 * out, or somebody flushed it - and nothing at all after a deliberate logout.
 * The login page reads and consumes it so the user sees the reason in their
 * language.
 */
let sessionEndReason: string | undefined

/** Reads the reason without consuming it (specs, second looks). */
export const getSessionEndReason = (): string | undefined => sessionEndReason

/** Reads and clears the reason; the login page calls this on mount. */
export const consumeSessionEndReason = (): string | undefined => {
  const reason = sessionEndReason
  sessionEndReason = undefined
  return reason
}

/**
 * Subscribers for "the server refused this caller's rights although the
 * session is valid" (a `permission_denied` answer of #834's contract). The
 * provider itself cannot reach react-query; the mounted bridge invalidates the
 * cached access answers and refreshes the open screens through this seam -
 * the same pair the Members screen applies inline after a self-revocation.
 */
const permissionLostListeners = new Set<() => void>()

export const onPermissionLost = (listener: () => void): (() => void) => {
  permissionLostListeners.add(listener)
  return () => {
    permissionLostListeners.delete(listener)
  }
}

/**
 * The JSON:API error code of a failed API call, from either shape a caller
 * hands `checkError`: an HttpError carrying the parsed body, or the AxiosError
 * of the dataProvider with `response.data`. The contract of
 * `docs/source/administration/authentication.md` reads it because this
 * deployment answers a dead credential and a refused action with the same 403
 * (the first configured authenticator offers no WWW-Authenticate):
 * `authentication_failed` / `not_authenticated` say the credential is gone,
 * `permission_denied` says the session is valid but may not do this.
 */
const authErrorCode = (error: unknown): string | undefined => {
  const withBody = error as {
    body?: { errors?: { code?: string }[] }
    response?: { data?: { errors?: { code?: string }[] } }
  }
  return withBody?.body?.errors?.[0]?.code
    ?? withBody?.response?.data?.errors?.[0]?.code
}

export const setSession = (props: AuthSession | undefined) => {
  if (props === undefined) {
    localStorage.removeItem(AUTH_SESSION_LOCAL_STORAGE_NAME)
  } else {
    localStorage.setItem(AUTH_SESSION_LOCAL_STORAGE_NAME, JSON.stringify(props))
  }
}


/**
 * The browser's authentication (#835, accepted decision Q8=B).
 *
 * There is no client-held credential any more. A login turns the credentials
 * the user typed into a Django session whose cookie the browser attaches on its
 * own (`credentials: 'include'` everywhere, `HttpOnly` on the response), state
 * changing requests carry the CSRF header beside it, and a logout flushes the
 * session server-side. What a script on this page can therefore read is the
 * user's name and the CSRF value - neither of which is a credential. The
 * machine clients (scripts, CLI) keep the token endpoint of
 * `docs/source/administration/authentication.md`; they are not this provider's
 * business.
 */
const sessionAuthProvider = (
    sessionUrl = `${API_BASE_URL}/api/auth/session`,
    legacyLogoutUrl = `${API_BASE_URL}/api/auth/logout`,
    identityUrl = `${API_BASE_URL}/api/accounts/who-am-i/`,
): AuthProvider => {
  // One permission snapshot per session, held in this closure (#836). react-admin
  // asks canAccess whenever a menu entry or a list mounts; answering it is pure
  // table lookup here, never a fetch. Everything that ends or invalidates the
  // session - logout, a 401 from any endpoint, a refused write - drops it,
  // which is also how a revoked role stops being honoured client-side. The
  // backend stays authoritative either way.
  let snapshotCache: Promise<PermissionSnapshot> | undefined
  const resetSnapshotCache = () => { snapshotCache = undefined }
  /** Whether *this page load* learned from the backend that its cookie
   * authenticates. Not persisted: a reload asks the server again instead of
   * trusting a marker the server may have outlived (#835). */
  let sessionConfirmed = false
  /**
   * Ends the session everywhere it is remembered: the marker, the permission
   * snapshot and - unlike a deliberate logout - the reason the login page will
   * show (#834).
   */
  const endSession = (reasonKey: string | undefined) => {
    sessionEndReason = reasonKey
    sessionConfirmed = false
    setSession(undefined)
    resetSnapshotCache()
  }
  const permissionSnapshot = (): Promise<PermissionSnapshot> => {
    if (snapshotCache) {
      return snapshotCache
    }
    snapshotCache = whoAmI(identityUrl)
      .then(result => result.permissions)
      // An unreachable who-am-i answers the empty snapshot: administration
      // hides, ordinary resources stay reachable as long as the session
      // itself holds, and the backend keeps enforcing every write. The cache
      // is dropped for that case, so the next check asks again.
      .catch(() => {
        snapshotCache = undefined
        return ANONYMOUS_SNAPSHOT
      })
    return snapshotCache
  }
  /**
   * `GET /api/auth/session`: whether this browser's cookie still
   * authenticates, answered by the backend instead of by a client-side notion
   * of expiry (#834 had one because the credential it held carried an
   * `expiry`; a session cookie carries none, and its age slides server-side).
   * The same request is where a fresh browser learns its CSRF cookie, which
   * Django only sends where somebody asks for it.
   */
  const confirmSession = async (): Promise<boolean> => {
    try {
      const response = await fetch(new Request(sessionUrl, {
        method: 'GET',
        credentials: 'include',
        headers: new Headers({'content-type': 'application/json'})
      }))
      if (!response.ok) {
        return false
      }
      return (await response.json() as {authenticated?: boolean}).authenticated === true
    } catch {
      // Unreachable backend: keep the session the browser believes in. The
      // data calls decide from here, and a refused one ends it with the
      // reason - guessing "ended" from a network outage would log users out
      // of a live session.
      return true
    }
  }
  // the rollout step of the credential the previous frontend left behind; it
  // runs once per page load, before any of the answers below can be asked
  void revokeLegacyBrowserToken(legacyLogoutUrl)
  // the #737 screens read the snapshot through this seam; like every other
  // path it answers nothing once the session is gone
  snapshotAccess = {
    current: () => getSession() ? permissionSnapshot() : undefined,
    invalidate: resetSnapshotCache,
  }
  return {
    login: async ({ username, password }: LoginParams) => {
      const request = new Request(sessionUrl, {
        method: 'POST',
        credentials: 'include',
        headers: new Headers({
          Authorization: 'Basic ' + btoa(username + ':' + password),
          ...csrfHeaders()
        })
      })
      const response = await fetch(request)
      if (response.ok) {
        const { identity: userIdentity, permissions } = await whoAmI(identityUrl)
        setSession({...userIdentity, openedAt: new Date().toISOString()})
        // a fresh login supersedes any earlier session end and needs no probe
        sessionEndReason = undefined
        sessionConfirmed = true
        // the who-am-i this login just made is the snapshot's first and only
        // fetch for this session
        snapshotCache = Promise.resolve(permissions)
        return true
      }
      if (response.headers.get('content-type') !== 'application/json') {
        throw new Error(response.statusText)
      }

      const json = await response.json()
      // the stack's json:api exception handler names the reason in its error
      // document (`errors[0].detail`); the plain `detail` and the serializer
      // shape are kept as fallbacks for answers which skip it
      const error = json.errors?.[0]?.detail
        ?? json.non_field_errors ?? json.detail
      throw new Error(error ?? response.statusText)
    },
    logout: async () => {
      // A forced logout from #834 runs exactly here - react-admin's
      // `useLogoutIfAccessDenied` ends the session through this method right
      // after `checkAuth`/`checkError` called `endSession` - so the reason
      // set that way must survive to the login page. Nothing is cleared on
      // purpose either: a deliberate logout only happens in a session whose
      // login already dropped any earlier reason.
      await closeSession(sessionUrl)
      // Revocation is best effort: an unreachable backend or a refused
      // request still ends the local session, which is what react-admin
      // needs in order to redirect to the login page.
      setSession(undefined)
      resetSnapshotCache()
      sessionConfirmed = false
    },
    checkAuth: () => {
      const stored = getSession()
      if (!stored) {
        return Promise.reject(new Error('not authenticated'))
      }
      if (sessionConfirmed) {
        return Promise.resolve()
      }
      // first answer of this page load: the server decides, not the marker
      return confirmSession().then(authenticated => {
        if (authenticated) {
          sessionConfirmed = true
          return
        }
        // The cookie this browser still carries is not accepted any more, so
        // the session is over and the login page says why. useCheckAuth turns
        // this message (a translation key) into the notification and lands the
        // user on /login.
        endSession('auth.sessionExpired')
        throw new Error('auth.sessionExpired')
      })
    },
    checkError: error => {
      const status = error?.status
      if (status !== 401 && status !== 403) {
        return Promise.resolve()
      }
      const stored = getSession()
      if (!stored) {
        // no session to keep and none to lose: leave react-admin's own
        // handling of an anonymous caller on a guarded route in place
        resetSnapshotCache()
        return Promise.reject(new Error('not authenticated'))
      }
      const code = authErrorCode(error)
      // The auth-vs-denied contract of #834 (documented in
      // docs/source/administration/authentication.md, pinned by
      // tests/django/accounts/test_browser_session.py): this stack answers a
      // dead session with a 403 too, so the JSON:API error code, not the
      // status, decides. Without a readable code the session is kept: a
      // session cookie has no client-side expiry to fall back on, so a guess
      // could only ever log out a caller who is still signed in.
      const credentialDead = status === 401
        || code === 'not_authenticated'
        || code === 'authentication_failed'
      if (credentialDead) {
        endSession('auth.sessionExpired')
        return Promise.reject(new Error('auth.sessionExpired'))
      }
      // A live session whose action was refused: keep the session, notify,
      // and force a revalidation - the next canAccess must not answer from
      // the table the login filled, and the mounted bridge drops the cached
      // access answers and refreshes the open screens.
      resetSnapshotCache()
      permissionLostListeners.forEach(listener => listener())
      // `logoutUser: false` tells react-admin's logoutIfAccessDenied to
      // notify this translation key without touching the session.
      return Promise.reject(
        Object.assign(new Error('auth.forbidden'), { logoutUser: false }),
      )
    },
    /* The permission checks of #836 live in canAccess below, which answers
      from the closure snapshot - no query, no per-render fetch. getPermissions
      stays unimplemented on purpose, and the old loop's open question is resolved to
      this documented constraint: in react-admin 5.15 the CoreAdminRoutes
      mounts LogoutOnMount on the catch-all "*" route, and useLogout only
      avoids the trap because it defers navigate plus queryClient.clear by one
      macrotask. A getPermissions resolving immediately (marmelab/react-admin
      #10769) re-runs the usePermissions query mid-navigation, remounting
      LogoutOnMount on the login page - the exact loop the previous comment
      warned about. Verified against the installed 5.15.6.
    */
    canAccess: async ({ action, resource, record }: {
      action: string
      resource: string
      record?: Record<string, unknown>
    }): Promise<boolean> => {
      if (!getSession()) {
        // a lost session also drops any snapshot it left behind
        resetSnapshotCache()
        return canAccessFromSnapshot({
          action, resource, record, authenticated: false, snapshot: ANONYMOUS_SNAPSHOT
        })
      }
      const snapshot = await permissionSnapshot()
      return canAccessFromSnapshot({ action, resource, record, authenticated: true, snapshot })
    },
    getIdentity: () => {
      const stored = getSession()
      const { id, fullName, avatar } = stored ?? {id: 0, fullName: 'anonymous'};
      return Promise.resolve({ id, fullName, avatar });
    },

  }
}

export default sessionAuthProvider
