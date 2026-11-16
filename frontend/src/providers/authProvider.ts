import { UserIdentity, type AuthProvider } from 'ra-core';

import { API_BASE_URL } from '../context/HttpClientContext';
import {
  ANONYMOUS_SNAPSHOT,
  canAccessFromSnapshot,
  permissionSnapshotFromWhoAmI,
  type PermissionSnapshot,
} from './permissions';




export interface LoginParams {
  username: string
  password: string
}


export interface AuthToken extends UserIdentity {
  token: string
  expiry: string
}


interface WhoAmIResult {
  identity: UserIdentity
  permissions: PermissionSnapshot
}

const whoAmI = async (url: string, authToken: string): Promise<WhoAmIResult> => {

  const request = new Request(url, {
    method: 'GET',
    headers:  new Headers({
      'content-type': 'application/vnd.api+json',
      ...authToken && {Authorization: `Token ${authToken}`}
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
    return { identity: userIdentity, permissions: permissionSnapshotFromWhoAmI(responseJson) }
  }
  return { identity: {id: 0}, permissions: ANONYMOUS_SNAPSHOT }
}
/**
 * Asks the backend to revoke the presented token (#832).
 *
 * knox's LogoutView deletes the ``AuthToken`` row the ``Authorization`` header
 * it authenticates hashes to, so a credential copied out of this browser
 * before the logout - by XSS, a shared browser or leaked JS state - stops
 * answering anything. The view implements ``post`` only, so that is the verb
 * the endpoint at ``logoutUrl`` speaks; a ``DELETE`` is answered with 405 and
 * revokes nothing, which ``tests/django/accounts/test_logout_revokes_token.py``
 * pins.
 *
 * Neither a rejected request nor an unreachable backend is reported: the
 * caller clears the local state either way, because a logout which depends on
 * the server would leave the user signed in with a token their browser no
 * longer carries.
 */
const revokeToken = async (logoutUrl: string, token: string) => {
  const request = new Request(logoutUrl, {
    method: 'POST',
    headers: new Headers({ Authorization: `Token ${token}` })
  })

  try {
    await fetch(request)
  } catch {
    // offline: the local logout below is all that can happen
  }
}

export const AUTH_TOKEN_LOCAL_STORAGE_NAME = "mrmap.auth"

export const getAuthToken = (): AuthToken | undefined => {
  const storedToken = localStorage.getItem(AUTH_TOKEN_LOCAL_STORAGE_NAME)
  if (storedToken === undefined || storedToken === null){
    return undefined
  } else {
    return JSON.parse(storedToken) 
  }
}

export const setAuthToken = (props: AuthToken | undefined) => {
  if (props === undefined) {
    localStorage.removeItem(AUTH_TOKEN_LOCAL_STORAGE_NAME)
  } else {
    localStorage.setItem(AUTH_TOKEN_LOCAL_STORAGE_NAME, JSON.stringify(props))
  }
}


const tokenAuthProvider = (
    loginUrl = `${API_BASE_URL}/api/auth/login`,
    logoutUrl = `${API_BASE_URL}/api/auth/logout`,
    identityUrl = `${API_BASE_URL}/api/accounts/who-am-i/`,
): AuthProvider => {
  // One permission snapshot per login, held in this closure (#836). react-admin
  // asks canAccess whenever a menu entry or a list mounts; answering it is pure
  // table lookup here, never a fetch. The entry is keyed by token so a token
  // swap can never inherit the previous user's roles, and everything that
  // ends or invalidates the session - logout, an expired checkAuth, a 401 from
  // any endpoint - drops it, which is also how a revoked role stops being
  // honoured client-side. The backend stays authoritative either way.
  let snapshotCache: { token: string, permissions: Promise<PermissionSnapshot> } | undefined
  const resetSnapshotCache = () => { snapshotCache = undefined }
  const permissionSnapshot = (token: string): Promise<PermissionSnapshot> => {
    if (snapshotCache?.token === token) {
      return snapshotCache.permissions
    }
    snapshotCache = {
      token,
      // An unreachable who-am-i answers the empty snapshot: administration
      // hides, ordinary resources stay reachable as long as the session
      // itself holds, and the backend keeps enforcing every write.
      permissions: whoAmI(identityUrl, token)
        .then(result => result.permissions)
        .catch(() => ANONYMOUS_SNAPSHOT),
    }
    return snapshotCache.permissions
  }
  return {
    login: async ({ username, password }: LoginParams) => {
      const request = new Request(loginUrl, {
        method: 'POST',
        headers: new Headers({ Authorization: 'Basic ' + btoa(username + ':' + password) })
      })
      const response = await fetch(request)
      if (response.ok) {
        const token = await response.json()
        const { identity: userIdentity, permissions } = await whoAmI(identityUrl, token?.token)
        setAuthToken({...token, ...userIdentity})
        // the who-am-i this login just made is the snapshot's first and only
        // fetch for this session
        snapshotCache = token?.token
          ? { token: token.token, permissions: Promise.resolve(permissions) }
          : undefined
        return true
      }
      if (response.headers.get('content-type') !== 'application/json') {
        throw new Error(response.statusText)
      }

      const json = await response.json()
      const error = json.non_field_errors
      throw new Error(error ?? response.statusText)
    },
    logout: async () => {
      const storedToken = getAuthToken()
      if (storedToken?.token) {
        await revokeToken(logoutUrl, storedToken.token)
      }
      // Revocation is best effort: an unreachable backend or a refused
      // request still ends the local session, which is what react-admin
      // needs in order to redirect to the login page.
      setAuthToken(undefined)
      resetSnapshotCache()
    },
    checkAuth: async () => {
      const storedToken = getAuthToken()
      if (!storedToken) {
        throw new Error('not authenticated')
      }
      const expired = new Date(storedToken.expiry) < new Date()
      if (expired ){
        resetSnapshotCache()
        throw new Error(('your session has expired'))
      }
    },
    checkError: async error => {
      const status = error.status
      if (status === 401) {
        setAuthToken(undefined)
        resetSnapshotCache()
        throw new Error('unauthorized')
      }
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
      const storedToken = getAuthToken()
      const authenticated = !!storedToken?.token && new Date(storedToken.expiry) >= new Date()
      if (!authenticated) {
        // a lapsed or absent session also drops any snapshot it left behind
        resetSnapshotCache()
        return canAccessFromSnapshot({
          action, resource, record, authenticated: false, snapshot: ANONYMOUS_SNAPSHOT
        })
      }
      const snapshot = await permissionSnapshot(storedToken.token)
      return canAccessFromSnapshot({ action, resource, record, authenticated: true, snapshot })
    },
    getIdentity: async () => {
      const storedToken = getAuthToken()
      const { id, fullName, avatar } = storedToken ?? {id: 0, fullName: 'anonymous'};
      return { id, fullName, avatar };
    },
    
  }
}

export default tokenAuthProvider
