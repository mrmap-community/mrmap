import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { AxiosError, AxiosHeaders } from 'axios';
import OpenAPIClientAxios, { OpenAPIV3, OpenAPIV3_1 } from 'openapi-client-axios';

import { JsonApiMimeType } from '../jsonapi/types/jsonapi';

export interface HttpClientContextType {
  api?: OpenAPIClientAxios
  init: (locale: string) => void
  isPending: boolean
  error: any
}


const { VITE_API_SCHEMA, VITE_API_BASE_URL } = import.meta.env;


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
  const [api, setApi] = useState<OpenAPIClientAxios>()
  const [document, setDocument] = useState<OpenAPIV3.Document | OpenAPIV3_1.Document>()
  const [error, setError] = useState<AxiosError>();
  const [isPending, setIsPending] = useState<boolean>(false)

  useEffect(()=>{
    setDocument(undefined)
  },[])

  const initialize = useCallback((locale: string = "en")=>{
    setIsPending(true)
    const cfg = JSON.parse(JSON.stringify({
      headers: new AxiosHeaders(
      {
        'Accept-Language': locale,
      }
    )
    }))
    const httpClient = new OpenAPIClientAxios({ definition: `${VITE_API_SCHEMA}://${VITE_API_BASE_URL}/api/schema`, axiosConfigDefaults: cfg})
    httpClient.init().then((client) => {
      setDocument(client.api.document)
    }).catch((error) => { setError(error); console.error("errror during initialize axios openapi client", error)})
    .finally(() => setIsPending(false))
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
    if (document !== undefined){
      setIsPending(true)
      new OpenAPIClientAxios({ definition: document, axiosConfigDefaults: AXIOS_DEFAULTS})
      .init()
      .then((client) => {
          setApi(client.api)
      })
      .catch((error) => { console.error("errror during initialize axios openapi client", error)})
      .finally(() => setIsPending(false))
    }
  },[document])

  const value = useMemo<HttpClientContextType>(()=>({ 
      api: api, 
      init: (locale: string) => initialize(locale),
      isPending: isPending,
      error: error
  }), [api])

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
