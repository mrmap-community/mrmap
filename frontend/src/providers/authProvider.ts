import { UserIdentity, type AuthProvider } from 'ra-core';
import { AUTH_TOKEN_LOCAL_STORAGE_NAME } from '../context/HttpClientContext';

const { VITE_API_SCHEMA, VITE_API_BASE_URL } = import.meta.env;

export interface LoginParams {
  username: string
  password: string
}


export interface AuthToken extends UserIdentity {
  token: string
  expiry: string
}

export const TOKENNAME = 'mrmap.token'


const whoAmI = async (url: string, authToken: string): Promise<UserIdentity> => {

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
    return userIdentity
  }
  return {id: 0}
}

export const getAuthToken = (): AuthToken | undefined => {
  const storedToken = localStorage.getItem(AUTH_TOKEN_LOCAL_STORAGE_NAME)
  console.log(storedToken)
  if (storedToken === undefined || storedToken === null){
    return undefined
  } else {
    return JSON.parse(storedToken ?? "{}") 
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
    loginUrl = `${VITE_API_SCHEMA}://${VITE_API_BASE_URL}/api/auth/login`,
    logoutUrl = `${VITE_API_SCHEMA}://${VITE_API_BASE_URL}/api/auth/logout`,
    identityUrl = `${VITE_API_SCHEMA}://${VITE_API_BASE_URL}/api/accounts/who-am-i/`,
): AuthProvider => {
  
  return {
    login: async ({ username, password }: LoginParams) => {
      const request = new Request(loginUrl, {
        method: 'POST',
        headers: new Headers({ Authorization: 'Basic ' + btoa(username + ':' + password) })
      })
      const response = await fetch(request)
      if (response.ok) {
        const token = await response.json()
        const userIdentity = await whoAmI(identityUrl, token?.token)
        setAuthToken({...token, ...userIdentity})
        return Promise.resolve(true)
      }
      if (response.headers.get('content-type') !== 'application/json') {
        throw new Error(response.statusText)
      }

      const json = await response.json()
      const error = json.non_field_errors
      throw new Error(error ?? response.statusText)
    },
    logout: async () => {
      // TODO: call logoutUrl with token
      console.log('logout called')
      setAuthToken(undefined)
      return Promise.resolve();
    },
    checkAuth: async (params) => {
      
      const storedToken = getAuthToken()
      console.log('checkAuth called', storedToken)


      if (!storedToken) {
        const isLoginPage = window.location.pathname === '/login';
        if (isLoginPage) return Promise.resolve();
        return Promise.reject(new Error('No auth token'));
      }
      const expired = new Date(storedToken.expiry) < new Date()
      if (expired ){
        return Promise.reject(new Error('Token expired'));
      }
      return Promise.resolve();
    },
    checkError: async error => {
      const status = error.status
      if (status === 401) {
        setAuthToken(undefined)
        return Promise.reject(new Error('unauthorized'));      }
      return Promise.resolve()
    },
    getPermissions: async () => {
      await Promise.resolve()
    },
    getIdentity: async () => {
      const storedToken = getAuthToken()
      if (!storedToken) return Promise.reject();
      const { id, fullName, avatar } = storedToken;
      return Promise.resolve({ id, fullName, avatar });
    },
    
  }
}

export default tokenAuthProvider
