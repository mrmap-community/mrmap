import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren, type ReactNode } from 'react'


import { RaRecord } from 'react-admin'
import { OWSContext, OWSResource } from '../../ows-lib/OwsContext/core'
import { Position } from '../../ows-lib/OwsContext/enums'
import { TreeifiedOWSResource } from '../../ows-lib/OwsContext/types'


export interface OwsContextBaseType {
  // TODO: crs handling
  //crsIntersection: MrMapCRS[]
  //selectedCrs: MrMapCRS
  //setSelectedCrs: (crs: MrMapCRS) => void
  owsContext: OWSContext
  setOwsContext: (owsContext: OWSContext) => void
  updateOwsContext: (owsContext: OWSContext) => void
  isLoading: boolean
  currentRequest: Request | undefined
  resetContext: () => void
  addWMSByRecord: (record: RaRecord) => void
  addWMSByUrl: (url: string, headers?: Headers) => void
  initialFromOwsContext: (url: string, headers?: Headers) => void
  trees: TreeifiedOWSResource[]
  activeFeatures: OWSResource[]
  setFeatureActive: (folder: string, active: boolean) => void
  moveFeature: (source: OWSResource, target: OWSResource, position: Position) => void
}

export const context = createContext<OwsContextBaseType | undefined>(undefined)

export interface OwsContextBaseProps extends PropsWithChildren {
  initialFeatures?: OWSResource[]
}


export const OwsContextBase = ({ initialFeatures = [], children }: OwsContextBaseProps): ReactNode => {
  const [isLoading, setIsLoading] = useState(false)
  const [currentRequest, setCurrentRequest] = useState<Request | undefined>(undefined)
  const abortControllerRef = useRef<AbortController | null>(null)

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
      setIsLoading(true)

      const response = await fetch(request)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      return response
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        console.debug('Fetch request was aborted')
        return null
      }
      console.error('Fetch error:', error)
      throw error
    } finally {
      setIsLoading(false)
      setCurrentRequest(undefined)
    }
  }, [])

  const addWMSByRecord = useCallback((record: RaRecord) => {
    const url = record.operationUrls?.find(
      (opUrl: RaRecord) => {
        return (opUrl.method === 1 || opUrl.method === 'Get') && (opUrl.operation === 1 || opUrl.operation === 'GetCapabilities')
      }
    )?.url

    if (url) {
      addWMSByUrl(url)
    }
  }, [])

  const addWMSByUrl = useCallback((url: string, headers?: Headers, record?: RaRecord) => {
    performFetch(url, headers)
      .then((response) => {
        if (response === null) return
        return response.text()
      })
      .then((xmlString) => {
        if (!xmlString) return
        setOwsContext((prev) => {
          const newContext = OWSContext.fromPlainObject(prev)
          // TODO: how to pass record here, so the wms id and layer id's are present inside owscontext?
          // best would be if this happens without changing the core so it depends on react admin.
          newContext.appendWms(url, xmlString, headers)
          return newContext
        })
      })
      .catch((error) => {
        console.error('Failed to add WMS:', error)
      })
  }, [performFetch])

  const initialFromOwsContext = useCallback((url: string, headers?: Headers) => {
    performFetch(url, headers)
      .then((response) => {
        if (response === null) return
        return response.json()
      })
      .then(async (json: any) => {
        // Validate JSON structure
        if (!json || !Array.isArray(json.features)) {
          throw new Error('Invalid OWSContext JSON structure: features array is required')
        }
        const newOwsContext = OWSContext.fromPlainObject(json)
        await newOwsContext.initialize()
        setOwsContext(newOwsContext)
      })
      .catch((error) => {
        console.error('Failed to initialize from OWSContext:', error)
      })
  }, [performFetch])

  const resetContext = useCallback(() => {
    setOwsContext(new OWSContext())
  }, [])

  const setFeatureActive = useCallback((folder: string, active: boolean) => {
    setOwsContext((prev) => {
      
      const newContext = OWSContext.fromPlainObject(prev)
      const features = newContext.activateFeature(folder, active)
      console.log('setFeatureActive', features.filter(f=>f.properties.active===true))
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
