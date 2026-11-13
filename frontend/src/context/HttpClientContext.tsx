import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ReadyState } from 'react-use-websocket';

import axios, { AxiosError, AxiosHeaders } from 'axios';
import OpenAPIClientAxios, { OpenAPIV3, OpenAPIV3_1 } from 'openapi-client-axios';

import { JsonApiMimeType } from '../jsonapi/types/jsonapi';
import { LOCALE_STORAGE_NAME } from '../providers/i18nProvider';

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
  error: AxiosError | undefined
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


const currentLocale = () => localStorage.getItem(LOCALE_STORAGE_NAME) ?? 'en'

// One document fetch per locale for the whole application, shared by every
// mount (including React StrictModes double invocation and the retry loop):
// the schema is megabytes and the boot must not multiply that download.
let documentFetch:
  | { locale: string, promise: Promise<OpenAPIV3.Document | OpenAPIV3_1.Document> }
  | undefined

const fetchSchemaDocument = (locale: string) => {
  if (documentFetch?.locale === locale) {
    return documentFetch.promise
  }
  // A plain GET so the browser cache answers within its max-age without
  // touching the network; the lang parameter keeps both the browser cache
  // and the backend generation cache keyed by the language.
  const promise = axios
    .get(`${API_BASE_URL}/api/schema`, {
      params: { lang: locale },
      headers: new AxiosHeaders({ 'Accept-Language': locale }),
      responseType: 'json',
    })
    .then((response) => response.data as OpenAPIV3.Document | OpenAPIV3_1.Document)
  documentFetch = { locale, promise }
  // a failed fetch must be retryable: drop the memo when it rejected
  promise.catch(() => {
    if (documentFetch?.promise === promise) {
      documentFetch = undefined
    }
  })
  return promise
}


export const HttpClientBase = ({ children }: import("react").PropsWithChildren): ReactNode => {
  const [api, setApi] = useState<OpenAPIClientAxios>()
  const [document, setDocument] = useState<OpenAPIV3.Document | OpenAPIV3_1.Document>()
  const [error, setError] = useState<AxiosError>();
  const [isPending, setIsPending] = useState<boolean>(false)
  const [realtimeIsReady, setRealtimeIsReady] = useState<ReadyState>(ReadyState.UNINSTANTIATED)
  const [status, setStatus] = useState<HttpClientStatus>(HttpClientStatus.Idle)
  const retryDelay = useRef(2000)

  useEffect(()=>{
    setDocument(undefined)
  },[])

  const initialize = useCallback((locale: string = currentLocale())=>{
    setIsPending(true)
    setStatus(HttpClientStatus.DownloadingSchema)
    fetchSchemaDocument(locale)
    .then((definition) => {
      setDocument(definition)
    }).catch((error) => { 
      setError(error); 
      setStatus(HttpClientStatus.Error)
    
      console.error(
        "errror during download of the openapi schema", 
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
    if(error?.code !== 'ERR_NETWORK'){
      // a reachable API resets the waiting ladder for the next outage
      retryDelay.current = 2000
      return
    }
    // while the backend is cold, every retry is a megabyte transfer (and
    // maybe a generation): wait progressively longer instead of hammering
    // the endpoint every two seconds
    const timeout = window.setTimeout(() => {
      retryDelay.current = Math.min(retryDelay.current * 2, 30000)
      setError(() => undefined);
    }, retryDelay.current);

    return () => window.clearTimeout(timeout);
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
