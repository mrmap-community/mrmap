import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import useWebSocket from 'react-use-websocket';

import { useLocalStorage } from "@uidotdev/usehooks";
import { AxiosError, AxiosHeaders, AxiosRequestConfig } from 'axios';
import OpenAPIClientAxios, { OpenAPIV3, OpenAPIV3_1 } from 'openapi-client-axios';
import { WebSocketLike } from 'react-use-websocket/dist/lib/types';

import { useAuthState } from 'react-admin';
import { JsonApiMimeType } from '../jsonapi/types/jsonapi';
import { getAuthToken } from '../providers/authProvider';

export interface HttpClientContextType {
  locale?: string
  api?: OpenAPIClientAxios 
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
  const [storedLocale] = useLocalStorage<string>(LOCALE_STORAGE_NAME, 'en');
  const [locale, setLocale] = useState<string>(storedLocale);

  const { authenticated } = useAuthState();

  const [api, setApi] = useState<OpenAPIClientAxios>()
  const [document, setDocument] = useState<OpenAPIV3.Document | OpenAPIV3_1.Document>()
  const [error, setError] = useState<AxiosError>();

  const websocketUrl = useMemo(()=>{
    if (authenticated){
      const storedAuthToken = getAuthToken();
      return `${VITE_API_SCHEMA === "https" ? "wss": "ws"}://${VITE_API_BASE_URL}/ws/default/?token=${storedAuthToken?.token}`
    } else {
      return `${VITE_API_SCHEMA === "https" ? "wss": "ws"}://${VITE_API_BASE_URL}/ws/default/`
    }
  },[authenticated])

  const { readyState, getWebSocket } = useWebSocket(
    websocketUrl,
    {
      shouldReconnect: () => true,
      reconnectAttempts: 10,
      //attemptNumber will be 0 the first time it attempts to reconnect, so this equation results in a reconnect pattern of 1 second, 2 seconds, 4 seconds, 8 seconds, and then caps at 10 seconds until the maximum number of attempts is reached
      reconnectInterval: (attemptNumber) => Math.min(Math.pow(2, attemptNumber) * 1000, 10000)
    },
    !!authenticated
  );

  const defaultConf = useMemo<AxiosRequestConfig>(()=>{
    const conf = {...AXIOS_DEFAULTS}
    const storedAuthToken = getAuthToken();
    authenticated && storedAuthToken?.token && conf?.headers?.setAuthorization(`Token ${storedAuthToken?.token}`)
    conf?.headers?.set("Accept-Language", locale || "en")
    return conf

  }, [locale, authenticated])


  useEffect(()=>{
    setDocument(undefined)
  },[locale])

  useEffect(() => {
    if (document === undefined && error === undefined) {     
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
      }).catch((error) => { setError(error); console.error("errror during initialize axios openapi client", error)})
    }
  }, [document, error])

  useEffect(()=>{
    if(error?.code === 'ERR_NETWORK'){
      const interval = setInterval(() => {
        setError(() => undefined);
      }, 2000);

    return () => clearInterval(interval);
    }
  },[error])


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
      updateLocale: setLocale,
      readyState: readyState,
      getWebSocket: getWebSocket
  }), [api, getWebSocket, readyState])

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
