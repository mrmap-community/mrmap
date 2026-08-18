import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { AxiosError, AxiosHeaders } from 'axios';
import OpenAPIClientAxios, { OpenAPIV3, OpenAPIV3_1 } from 'openapi-client-axios';

import { ReadyState } from 'react-use-websocket';
import { JsonApiMimeType } from '../jsonapi/types/jsonapi';

export enum HttpClientStatus {
  Idle = 'idle',
  DownloadingSchema = 'downloading-schema',
  InitializingClient = 'initializing-client',
  Ready = 'ready',
  Error = 'error',
}


export interface HttpClientContextType {
  api?: OpenAPIClientAxios
  init: (locale: string) => void
  isPending: boolean
  status: HttpClientStatus
  error: any
  realtimeIsReady: ReadyState
  setRealtimeIsReady: (readyState: ReadyState) => void
}


const { VITE_API_SCHEMA, VITE_API_BASE_URL, VITE_API_PORT } = import.meta.env;

export const API_BASE_URL = `${VITE_API_SCHEMA}://${VITE_API_BASE_URL}:${VITE_API_PORT}`


const AXIOS_DEFAULTS = {
  baseURL: API_BASE_URL,  
  headers: new AxiosHeaders(
    {
      Accept: JsonApiMimeType,
      'Content-Type': JsonApiMimeType,
    }
  )
}



export const HttpClientContext = createContext<HttpClientContextType|undefined>(undefined)


export const HttpClientBase = ({ children }: any): ReactNode => {
  const [api, setApi] = useState<OpenAPIClientAxios>()
  const [document, setDocument] = useState<OpenAPIV3.Document | OpenAPIV3_1.Document>()
  const [error, setError] = useState<AxiosError>();
  const [isPending, setIsPending] = useState<boolean>(false)
  const [realtimeIsReady, setRealtimeIsReady] = useState<ReadyState>(ReadyState.UNINSTANTIATED)
  const [status, setStatus] = useState<HttpClientStatus>(HttpClientStatus.Idle)

  useEffect(()=>{
    setDocument(undefined)
  },[])

  const initialize = useCallback((locale: string = "en")=>{
    setIsPending(true)
    setStatus(HttpClientStatus.DownloadingSchema)
    const cfg = JSON.parse(JSON.stringify({
      headers: new AxiosHeaders(
      {
        'Accept-Language': locale,
      }
    )
    }))   
    const httpClient = new OpenAPIClientAxios({ 
      definition: `${API_BASE_URL}/api/schema`, 
      axiosConfigDefaults: cfg
    })

    httpClient
    .init()
    .then((client) => {
      setDocument(client.api.document)
    }).catch((error) => { 
      setError(error); 
      setStatus(HttpClientStatus.Error)
    
      console.error(
        "errror during initialize axios openapi client", 
        error
      )
    })
  },[setError, setDocument])

  useEffect(() => {
    if (document === undefined && error === undefined) {     
      initialize()
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
    if (document === undefined) {
      return
    }

    setIsPending(true)
    setStatus(HttpClientStatus.InitializingClient)

    new OpenAPIClientAxios({ 
      definition: document, 
      axiosConfigDefaults: AXIOS_DEFAULTS
    })
    .init()
    .then((client) => {
        setApi(client.api)
        setStatus(HttpClientStatus.Ready)
    })
    .catch((error) => {
      setError(error);
      setStatus(HttpClientStatus.Error)
      console.error(
        "errror during initialize axios openapi client", 
        error
      )
    })
    .finally(() => setIsPending(false))
    
  },[document])

  const value = useMemo<HttpClientContextType>(() => ({
    api,
    init: initialize,
    isPending,
    status,
    error,
    realtimeIsReady,
    setRealtimeIsReady,
  }), [
    api,
    isPending,
    status,
    error,
    realtimeIsReady,
    initialize,
  ])

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
