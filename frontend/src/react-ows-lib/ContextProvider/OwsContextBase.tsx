import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren, type ReactNode } from 'react'


import { RaRecord } from 'react-admin'
import { OWSContext, OWSResource } from '../../ows-lib/OwsContext/core'
import { Position } from '../../ows-lib/OwsContext/enums'

export type OwsContextLoadingStatus = 'idle' | 'fetching' | 'reading' | 'parsing' | 'ready' | 'error'

export type OwsContextLoadingTimings = Partial<{
  performFetch: number
  responseText: number
  fromPlainObject: number
  appendWms: number
  beforeSetHook: number
  jsonParse: number
  initialize: number
  total: number
}>

export interface OwsContextBaseType {
  owsContext: OWSContext
  setOwsContext: (owsContext: OWSContext) => void
  updateOwsContext: (owsContext: OWSContext) => void
  isLoading: boolean
  isFetching: boolean
  isReading: boolean
  isParsing: boolean
  loadingStatus: OwsContextLoadingStatus
  loadingMessage?: string
  loadingTimings: OwsContextLoadingTimings
  errorMessage?: string
  currentRequest: Request | undefined
  resetContext: () => void
  addWMSByRecord: (record: RaRecord) => void
  addWMSByUrl: (url: string, headers?: Headers, beforeSetHook?: (context: OWSContext, treeId: number) => OWSContext) => void
  initialFromOwsContext: (url: string, headers?: Headers) => void
  trees: OWSResource[]
  activeFeatures: OWSResource[]
  setFeatureActive: (folder: string, active: boolean) => void
  moveFeature: (source: OWSResource, target: OWSResource, position: Position) => void
}

export const context = createContext<OwsContextBaseType | undefined>(undefined)

const getOgcServiceExceptionMessage = (responseText: string): string | undefined => {
  if (!responseText || !responseText.trim().startsWith('<')) {
    return undefined
  }

  try {
    const parser = new DOMParser()
    const document = parser.parseFromString(responseText, 'application/xml')
    const parserError = document.querySelector('parsererror')
    if (parserError) {
      return undefined
    }

    const exceptionNodes = Array.from(document.getElementsByTagName('*')).filter((element) => {
      return element.localName === 'ServiceException'
    })

    if (exceptionNodes.length === 0) {
      return undefined
    }

    const firstException = exceptionNodes[0]
    const code = firstException.getAttribute('code')
    const message = firstException.textContent?.trim()

    if (code && message) {
      return `${code}: ${message}`
    }

    if (message) {
      return message
    }

    return 'OGC service exception'
  } catch {
    return undefined
  }
}

export interface OwsContextBaseProps extends PropsWithChildren {
  initialFeatures?: OWSResource[]
}


export const OwsContextBase = ({ initialFeatures = [], children }: OwsContextBaseProps): ReactNode => {
  const [loadingStatus, setLoadingStatus] = useState<OwsContextLoadingStatus>('idle')
  const [loadingMessage, setLoadingMessage] = useState<string | undefined>(undefined)
  const [loadingTimings, setLoadingTimings] = useState<OwsContextLoadingTimings>({})
  const [errorMessage, setErrorMessage] = useState<string | undefined>(undefined)
  const [currentRequest, setCurrentRequest] = useState<Request | undefined>(undefined)
  const abortControllerRef = useRef<AbortController | null>(null)

  const isLoading = loadingStatus === 'fetching' || loadingStatus === 'reading' || loadingStatus === 'parsing'
  const isFetching = loadingStatus === 'fetching'
  const isReading = loadingStatus === 'reading'
  const isParsing = loadingStatus === 'parsing'

  const [owsContext, setOwsContext] = useState<OWSContext>(new OWSContext(undefined, initialFeatures, undefined, {
    lang: 'en',
    title: 'mrmap ows context',
    updated: new Date().toISOString(),
    display: {}
  }))
  
  const trees = useMemo(() => {
    return owsContext.treeify()
  }, [owsContext])

  const activeFeatures = useMemo(() => {
    return owsContext.getActiveFeatures()
  }, [owsContext])

  // Cleanup abort controller on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort()
    }
  }, [])

  const updateOwsContext = useCallback((newContext: OWSContext) => {
    setOwsContext(OWSContext.fromPlainObject(newContext))
  }, [])

  // Consolidated fetch logic with error handling and abort support
  const performFetch = useCallback(async (url: string, headers?: Headers) => {
    // Cancel any previous request
    abortControllerRef.current?.abort()
    
    const controller = new AbortController()
    abortControllerRef.current = controller

    try {
      const request = new Request(url, {
        method: 'GET',
        headers,
        signal: controller.signal
      })
      setCurrentRequest(request)
      setLoadingStatus('fetching')
      setLoadingMessage('Downloading data...')
      setLoadingTimings({})
      setErrorMessage(undefined)

      const response = await fetch(request)
      if (!response.ok) {
        const errorText = await response.text().catch(() => '')
        const serviceExceptionMessage = getOgcServiceExceptionMessage(errorText)
        if (serviceExceptionMessage) {
          throw new Error(serviceExceptionMessage)
        }
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      return response
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        setLoadingStatus('idle')
        setLoadingMessage(undefined)
        return null
      }
      const message = error instanceof Error ? error.message : String(error)
      setLoadingStatus('error')
      setLoadingMessage(message)
      setErrorMessage(message)
      throw error
    } finally {
      setCurrentRequest(undefined)
      setLoadingStatus((previous) => previous === 'fetching' ? 'idle' : previous)
      setLoadingMessage((previous) => previous === 'Downloading data...' ? undefined : previous)
    }
  }, [])

  const addWMSByUrl = useCallback(async (url: string, headers?: Headers, beforeSetHook?: (context: OWSContext, treeId: number) => OWSContext) => {
    const timings = {
      performFetch: 0,
      responseText: 0,
      fromPlainObject: 0,
      appendWms: 0,
      beforeSetHook: 0,
      total: 0
    }
    const totalStart = performance.now()

    try {
      setLoadingStatus('fetching')
      setLoadingMessage('Downloading WMS capabilities...')
      setLoadingTimings({
        performFetch: 0,
        responseText: 0,
        fromPlainObject: 0,
        appendWms: 0,
        beforeSetHook: 0,
        total: 0
      })
      setErrorMessage(undefined)

      const performFetchStart = performance.now()
      const response = await performFetch(url, headers)
      timings.performFetch = performance.now() - performFetchStart
      setLoadingTimings((previous) => ({ ...previous, performFetch: timings.performFetch }))

      if (response === null) {
        setLoadingStatus('idle')
        setLoadingMessage(undefined)
        return
      }

      setLoadingStatus('reading')
      setLoadingMessage('Reading WMS capabilities...')

      const responseTextStart = performance.now()
      const xmlString = await response.text()
      timings.responseText = performance.now() - responseTextStart
      setLoadingTimings((previous) => ({ ...previous, responseText: timings.responseText }))

      if (!xmlString) {
        throw new Error('Empty WMS response')
      }

      const serviceExceptionMessage = getOgcServiceExceptionMessage(xmlString)
      if (serviceExceptionMessage) {
        setLoadingStatus('error')
        setLoadingMessage(serviceExceptionMessage)
        setErrorMessage(serviceExceptionMessage)
        return
      }

      setLoadingStatus('parsing')
      setLoadingMessage('Parsing WMS capabilities...')

      let parseError: Error | undefined
      setOwsContext((prev) => {
        try {
          const fromPlainObjectStart = performance.now()
          let newContext = OWSContext.fromPlainObject(prev)
          timings.fromPlainObject = performance.now() - fromPlainObjectStart
          setLoadingTimings((previous) => ({ ...previous, fromPlainObject: timings.fromPlainObject }))

          const appendWmsStart = performance.now()
          const treeId = newContext.appendWms(url, xmlString)
          timings.appendWms = performance.now() - appendWmsStart
          setLoadingTimings((previous) => ({ ...previous, appendWms: timings.appendWms }))

          if (beforeSetHook !== undefined) {
            const beforeSetHookStart = performance.now()
            newContext = beforeSetHook(newContext, treeId)
            timings.beforeSetHook = performance.now() - beforeSetHookStart
            setLoadingTimings((previous) => ({ ...previous, beforeSetHook: timings.beforeSetHook }))
          }

          return newContext
        } catch (error) {
          parseError = error instanceof Error ? error : new Error(String(error))
          const message = parseError.message
          setLoadingStatus('error')
          setLoadingMessage(message)
          setErrorMessage(message)
          return prev
        }
      })

      if (parseError) {
        return
      }

      timings.total = performance.now() - totalStart
      setLoadingTimings((previous) => ({ ...previous, total: timings.total }))
      setLoadingStatus('ready')
      setLoadingMessage('WMS capabilities loaded')
    } catch (error) {
      
      const message = error instanceof Error ? error.message : String(error)
      setLoadingStatus('error')
      setLoadingMessage(message)
      setErrorMessage(message)
    }
  }, [performFetch])

  const initialFromOwsContext = useCallback(async (url: string, headers?: Headers) => {
    const totalStart = performance.now()
    const timings: OwsContextLoadingTimings = {
      performFetch: 0,
      jsonParse: 0,
      initialize: 0,
      total: 0
    }

    try {
      setLoadingStatus('fetching')
      setLoadingMessage('Downloading OWS context...')
      setLoadingTimings({
        performFetch: 0,
        jsonParse: 0,
        initialize: 0,
        total: 0
      })
      setErrorMessage(undefined)

      const performFetchStart = performance.now()
      const response = await performFetch(url, headers)
      timings.performFetch = performance.now() - performFetchStart
      setLoadingTimings((previous) => ({ ...previous, performFetch: timings.performFetch }))

      if (response === null) {
        setLoadingStatus('idle')
        setLoadingMessage(undefined)
        return
      }

      setLoadingStatus('reading')
      setLoadingMessage('Reading OWS context...')
      const jsonParseStart = performance.now()
      const responseText = await response.text()
      const serviceExceptionMessage = getOgcServiceExceptionMessage(responseText)
      if (serviceExceptionMessage) {
        throw new Error(serviceExceptionMessage)
      }

      const json = JSON.parse(responseText)
      timings.jsonParse = performance.now() - jsonParseStart
      setLoadingTimings((previous) => ({ ...previous, jsonParse: timings.jsonParse }))

      setLoadingStatus('parsing')
      setLoadingMessage('Parsing OWS context...')

      if (!json || !Array.isArray(json.features)) {
        throw new Error('Invalid OWSContext JSON structure: features array is required')
      }
      const newOwsContext = OWSContext.fromPlainObject(json)
      // initialize may not be typed on OWSContext in some builds; call if available
      if (typeof (newOwsContext as any).initialize === 'function') {
        const initializeStart = performance.now()
        await (newOwsContext as any).initialize()
        timings.initialize = performance.now() - initializeStart
        setLoadingTimings((previous) => ({ ...previous, initialize: timings.initialize }))
      }
      setOwsContext(newOwsContext)
      timings.total = performance.now() - totalStart
      setLoadingTimings((previous) => ({ ...previous, total: timings.total }))
      setLoadingStatus('ready')
      setLoadingMessage('OWS context ready')
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setLoadingStatus('error')
      setLoadingMessage(message)
      setErrorMessage(message)
    }
  }, [performFetch])

  const addWMSByRecord = useCallback((record: RaRecord) => {
    const url = (record.url ?? record.href ?? record.wmsUrl ?? record.serviceUrl) as string | undefined
    if (typeof url !== 'string' || url.length === 0) {
      return
    }
    addWMSByUrl(url)
  }, [addWMSByUrl])

  const resetContext = useCallback(() => {
    setOwsContext(new OWSContext())
    setLoadingStatus('idle')
    setLoadingMessage(undefined)
    setLoadingTimings({})
    setErrorMessage(undefined)
  }, [])

  const setFeatureActive = useCallback((folder: string, active: boolean) => {
    setOwsContext((prev) => {
      const newContext = OWSContext.fromPlainObject(prev)
      newContext.activateFeature(folder, active)
      return newContext
    })
  }, [])

  const moveFeature = useCallback((source: OWSResource, target: OWSResource, position: Position = Position.lastChild) => {
    setOwsContext((prev) => {
      const newContext = OWSContext.fromPlainObject(prev)
      newContext.moveFeature(source, target, position)
      return newContext
    })
  }, [])


  const value = useMemo<OwsContextBaseType>(() => {
    return {
      owsContext,
      setOwsContext,
      updateOwsContext,
      isLoading,
      isFetching,
      isReading,
      isParsing,
      loadingStatus,
      loadingMessage,
      loadingTimings,
      errorMessage,
      currentRequest,
      resetContext,
      addWMSByRecord,
      addWMSByUrl,
      initialFromOwsContext,
      trees,
      activeFeatures,
      setFeatureActive,
      moveFeature
    }
  }, [
    owsContext,
    setOwsContext,
    updateOwsContext,
    isLoading,
    isFetching,
    isReading,
    isParsing,
    loadingStatus,
    loadingMessage,
    loadingTimings,
    errorMessage,
    currentRequest,
    resetContext,
    addWMSByRecord,
    addWMSByUrl,
    initialFromOwsContext,
    trees,
    activeFeatures,
    setFeatureActive,
    moveFeature
  ])

  return (
    <context.Provider value={value}>
      {children}
    </context.Provider>
  )
}

export const useOwsContextBase = (): OwsContextBaseType => {
  const ctx = useContext(context)

  if (ctx === undefined) {
    throw new Error('useOwsContextBase must be inside a OwsContextBase')
  }
  return ctx
}
