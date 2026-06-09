import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren, type ReactNode } from 'react'


import { RaRecord } from 'react-admin'
import { OWSContext, OWSResource } from '../../ows-lib/OwsContext/core'
import { Position } from '../../ows-lib/OwsContext/enums'
import { TreeifiedOWSResource } from '../../ows-lib/OwsContext/types'
import { treeify } from '../../ows-lib/OwsContext/utils'

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
  setFeatureActive: (feature: OWSResource, active: boolean) => void
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

  // area of interest in crs 4326
  const [owsContext, setOwsContext] = useState<OWSContext>(new OWSContext(undefined, initialFeatures, undefined, {
    lang: 'en',
    title: 'mrmap ows context',
    updated: new Date().toISOString(),
    display: {}
  }))
  
  const trees = useMemo(() => {
    return treeify(owsContext.features)
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
    setOwsContext(
      new OWSContext(
        newContext.id,
        newContext.features,
        newContext.bbox,
        newContext.properties,
        newContext.capabilititesMap
      )
    )
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

  const addWMSByUrl = useCallback((url: string, headers?: Headers) => {
    performFetch(url, headers)
      .then((response) => {
        if (response === null) return
        return response.text()
      })
      .then((xmlString) => {
        if (!xmlString) return
        setOwsContext((prev) => {
          const newContext = new OWSContext(
            prev.id,
            [...prev.features],
            prev.bbox,
            prev.properties,
            prev.capabilititesMap
          )
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

        const newOwsContext = new OWSContext(
          json.id,
          json.features.map(
            (feature: any) =>
              new OWSResource(
                feature.properties,
                feature.id,
                feature.bbox,
                feature.geometry
              )
          ),
          json.bbox ?? undefined
        )

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

  const setFeatureActive = useCallback((feature: OWSResource, active: boolean) => {
    setOwsContext((prev) => {
      const newContext = new OWSContext(
        prev.id,
        [...prev.features],
        prev.bbox,
        prev.properties,
        prev.capabilititesMap
      )
      newContext.activateFeature(feature, active)
      return newContext
    })
  }, [])

  const moveFeature = useCallback((source: OWSResource, target: OWSResource, position: Position = Position.lastChild) => {
    setOwsContext((prev) => {
      const newContext = new OWSContext(
        prev.id,
        [...prev.features],
        prev.bbox,
        prev.properties,
        prev.capabilititesMap
      )
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
