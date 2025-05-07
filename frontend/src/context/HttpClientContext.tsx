import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import useWebSocket from 'react-use-websocket';

import { useLocalStorage } from "@uidotdev/usehooks";
import { AxiosHeaders, AxiosRequestConfig } from 'axios';
import { isEqual } from 'lodash';
import OpenAPIClientAxios, { OpenAPIV3, OpenAPIV3_1 } from 'openapi-client-axios';
import { WebSocketLike } from 'react-use-websocket/dist/lib/types';

import { JsonApiMimeType } from '../jsonapi/types/jsonapi';
import { AuthToken } from '../providers/authProvider';

export interface HttpClientContextType {
  locale?: string
  api?: OpenAPIClientAxios
  authToken: AuthToken | undefined
  setAuthToken: (authToken: AuthToken | undefined) => void
  updateLocale: (locale: string) => void
  readyState: ReadyState
  getWebSocket: () => WebSocketLike | null
}


const { VITE_API_SCHEMA, VITE_API_BASE_URL } = import.meta.env;

export const AUTH_TOKEN_LOCAL_STORAGE_NAME = "mrmap.auth"
export const LOCALE_STORAGE_NAME = "RaStore.locale"

const AXIOS_DEFAULTS = {
  baseURL: `${VITE_API_SCHEMA}://${VITE_API_BASE_URL}`,  
  headers: new AxiosHeaders(
    {
      Accept: JsonApiMimeType,
      'Content-Type': JsonApiMimeType,
    }
  )
}

export const HttpClientContext = createContext<HttpClientContextType|undefined>(undefined)


export const HttpClientBase = ({ children }: any): ReactNode => {
  const [storedAuthToken, setStoredAuthToken] = useLocalStorage<AuthToken| undefined>(AUTH_TOKEN_LOCAL_STORAGE_NAME);
  const [storedLocale] = useLocalStorage<string>(LOCALE_STORAGE_NAME, 'en');
  const [locale, setLocale] = useState<string>(storedLocale);

  const [authToken, setAuthToken] = useState<AuthToken| undefined>(undefined);

  const [api, setApi] = useState<OpenAPIClientAxios>()
  const [document, setDocument] = useState<OpenAPIV3.Document | OpenAPIV3_1.Document>()
  
  const { readyState, getWebSocket } = useWebSocket(
    `${VITE_API_SCHEMA === "https" ? "wss": "ws"}://${VITE_API_BASE_URL}/ws/default/?token=${authToken?.token}`,
    {
      shouldReconnect: () => true,
      reconnectAttempts: 10,
      //attemptNumber will be 0 the first time it attempts to reconnect, so this equation results in a reconnect pattern of 1 second, 2 seconds, 4 seconds, 8 seconds, and then caps at 10 seconds until the maximum number of attempts is reached
      reconnectInterval: (attemptNumber) => Math.min(Math.pow(2, attemptNumber) * 1000, 10000)
    },
    !!authToken
  );
  const defaultConf = useMemo<AxiosRequestConfig>(()=>{
    const conf = {...AXIOS_DEFAULTS}
    authToken?.token && conf?.headers?.setAuthorization(`Token ${authToken?.token}`)
    conf?.headers?.set("Accept-Language", locale || "en")
    return conf

  }, [locale, authToken])

  // we need to memo the localstorage value by our self.... see issue: https://github.com/uidotdev/usehooks/pull/304
  useEffect(()=>{
    if (isEqual(authToken, storedAuthToken) === false){
      setAuthToken(storedAuthToken)
    }
  },[storedAuthToken])

  useEffect(()=>{
    setDocument(undefined)
  },[locale])

  useEffect(() => {
    if (document === undefined) {     
      const cfg = JSON.parse(JSON.stringify({
        headers: new AxiosHeaders(
        {
          'Accept-Language': locale || "en",
        }
      )
      }))
      const httpClient = new OpenAPIClientAxios({ definition: `${VITE_API_SCHEMA}://${VITE_API_BASE_URL}/api/schema`, axiosConfigDefaults: cfg})
      httpClient.init().then((client) => {
        setDocument(client.api.document)
      }).catch((error) => { console.error("errror during initialize axios openapi client", error)})
    }
  }, [document])

  useEffect(()=>{
    if (document !== undefined){
      new OpenAPIClientAxios({ definition: document, axiosConfigDefaults: defaultConf})
      .init()
      .then((client) => {
          setApi(client.api)
      })
      .catch((error) => { console.error("errror during initialize axios openapi client", error)})
    }
  },[document, defaultConf])

  const value = useMemo<HttpClientContextType>(()=>({ 
      api: api, 
      authToken: authToken, 
      setAuthToken: setStoredAuthToken,
      updateLocale: setLocale,
      readyState: readyState,
      getWebSocket: getWebSocket
  }), [api, authToken, setStoredAuthToken, getWebSocket, readyState])

  return (
    <HttpClientContext.Provider value={value}>
      {children}
    </HttpClientContext.Provider>
  )
}

export const  useHttpClientContext = (): HttpClientContextType => {
  const context = useContext(HttpClientContext)
  if (context === undefined) {
    throw new Error('HttpClientContext must be inside a HttpClientBase')
  }
  return context
}
