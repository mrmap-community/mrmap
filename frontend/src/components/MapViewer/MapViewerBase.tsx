import { createContext, Dispatch, PropsWithChildren, ReactNode, SetStateAction, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { Map } from "leaflet";

import { getUnsupportedReasons, isRequestedByActivation } from "../../ows-lib/OwsContext/capabilities";
import { OptimizedUrlsMap, OWSResource } from "../../ows-lib/OwsContext/core";
import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase";
import { boundsToExtent, boundsToGeoJSON, extentBounds, featuresToCollection, latLngToGeoJSON, validExtent } from './utils';

export interface CRS {
  stringRepresentation: string
  isXyOrder: boolean
  wkt: string
}
type SetMapRef = (instance: Map | null) => void

export type MapLoadingStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface MapLoadingError {
  message: string
  features?: OWSResource[]
}

export interface MapLoadingState {
  status: MapLoadingStatus
  loaded: number
  total: number
  errors: MapLoadingError[]
  timings: Record<string, number>
  failedFeatures: OWSResource[]
}

export interface MapRequest {
  status: MapLoadingStatus
  error?: MapLoadingError
  timing?: number
}

export interface MapViewerBaseType {
  map?: Map
  setMap: SetMapRef
  selectedCrs: CRS
  setSelectedCrs: Dispatch<SetStateAction<CRS>>
  featureCollection: string | undefined
  atomicGetMapUrls: OptimizedUrlsMap[]
  atomicGetFeatureInfoUrls: OptimizedUrlsMap[]
  /**
   * The resources the document asks to render but this viewer cannot: they are kept visible by
   * name while the supported resources keep rendering, so that a partially rendered map is not
   * mistaken for the complete context.
   */
  unsupportedFeatures: OWSResource[]
  mapLoading: MapLoadingState
  reportMapLoading: (id: string, status: MapLoadingStatus, error?: MapLoadingError, timing?: number) => void
  removeMapLoading: (id: string) => void
}

export const context = createContext<MapViewerBaseType | undefined>(undefined)


export interface MapViewerBaseProps extends PropsWithChildren {
  /**
   * The area of interest the navigation asks the viewer to show, e.g. the viewport a live preview
   * was left at. It is the more recent request and applied before the area of interest stored in
   * the document, until the viewer publishes the viewport the user chose in the map itself.
   */
  previewExtent?: number[] | null
}

export const MapViewerBase = ({children, previewExtent}: MapViewerBaseProps): ReactNode => {
  const { owsContext, documentRevision, setContextBbox } = useOwsContextBase()

  const [map, setMapState] = useState<Map>()
  const [position, setPosition] = useState(() => map?.getCenter())
  const [bounds, setBounds] = useState(() => map?.getBounds())
  const [mapRequests, setMapRequests] = useState<Record<string, MapRequest>>({})
  const [selectedCrs, setSelectedCrs] = useState<CRS>({stringRepresentation: 'EPSG:4326', isXyOrder: false, wkt: 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]'})

  const setMap: SetMapRef = useCallback((instance) => {
    setMapState(instance ?? undefined)
  }, [])


  const positionGeoJSON = useMemo(()=>{
    return position ? latLngToGeoJSON(position): undefined
  },[position])

  const boundsGeoJSON = useMemo(()=>{
    return bounds ? boundsToGeoJSON(bounds): undefined
  },[bounds])

  const featureCollection = useMemo(()=>{
    const features = []
    // if (crsBbox !== undefined){
    //   features.push(polygonToFeature(crsBbox, "crs bbox"))
    // }
    if (positionGeoJSON !== undefined){
      features.push(positionGeoJSON)
    }
    if (boundsGeoJSON !== undefined){
      features.push(boundsGeoJSON)
    }
      
    return featuresToCollection(features)
  }, [position, bounds])

  const mapLoading = useMemo<MapLoadingState>(() => {
    const requests = Object.entries(mapRequests)
    const timings: Record<string, number> = {}

    const errors = requests.map((([, request]) => request.error)).filter(error => error !== undefined)

    const loaded = requests.filter(([, request]) => request.status === 'ready').length
    const hasLoading = requests.some(([, request]) => request.status === 'loading')
    const hasError = errors.length > 0
    
    const status: MapLoadingStatus = hasLoading
      ? 'loading'
      : hasError
        ? 'error'
        : requests.length > 0 && loaded === requests.length
          ? 'ready'
          : 'idle'

    const failedFeatures = requests.filter(([, request]) => request.error !== undefined).flatMap(([, request]) => request.error?.features || [])


    return { status, loaded, total: requests.length, errors, timings, failedFeatures }
  }, [mapRequests])

  const reportMapLoading = useCallback((id: string, status: MapLoadingStatus, error?: MapLoadingError, timing?: number) => {
    const nextRequest: MapRequest  = {
      status:status,
      timing: timing,
      error: error
    }

    setMapRequests((previous) => {
      const previousRequest = previous[id]
      if (
        previousRequest?.status === nextRequest.status &&
        previousRequest.error === nextRequest.error &&
        previousRequest.timing === nextRequest.timing
      ) {
        return previous
      }

      return {
        ...previous,
        [id]: nextRequest
      }
    })
  }, [])

  const removeMapLoading = useCallback((id: string) => {
    setMapRequests((previous) => {
      const next = { ...previous }
      delete next[id]
      return next
    })
  }, [])
     
  const atomicGetMapUrls = useMemo(()=>{
    return owsContext.getOptimizedUrlsByCode(
      "GetMap",
      (feature) => (
        feature.getWmsOperationByCode("GetMap")?.active === true
      )
    )
  }, [owsContext])

  const atomicGetFeatureInfoUrls = useMemo(()=>{
    return owsContext.getOptimizedUrlsByCode(
      "GetFeatureInfo",
      (feature) => (
        feature.getWmsOperationByCode("GetFeatureInfo")?.active === true
      )
    )
  }, [owsContext])

  // the resources the document asks to render but the request building skips in silence: an
  // unsupported offering, method or content. Group nodes answer through their children and are
  // asked by activation alone, so only childless resources are named here
  const unsupportedFeatures = useMemo(() => owsContext.features.filter(feature => {
    const folder = feature.properties.folder
    if (folder !== undefined && owsContext.features.some(other => other.getParentFolder() === folder)) {
      return false
    }
    return getUnsupportedReasons(feature).length > 0 && isRequestedByActivation(feature)
  }), [owsContext])

  const onMove = useCallback(() => {
    if (map !== undefined) {
      setPosition(map.getCenter())
      setBounds(map.getBounds())
    }
  }, [map])

  // the document whose area of interest was applied and the view the map shows of it; both keep the
  // two directions of the extent apart that would otherwise answer each other: applying an area of
  // interest would publish the wider view the fit chose back into the document, and a viewport the
  // user panned to would be pulled back to the area of interest that is stored in it
  const appliedRevision = useRef<string | undefined>(undefined)
  const fittedView = useRef<string | undefined>(undefined)
  const fitting = useRef(false)
  const publishedViewport = useRef(false)

  useEffect(() => {
    if (map === undefined) {
      return
    }
    const revision = `${documentRevision}:${previewExtent?.join(',') ?? ''}`
    if (appliedRevision.current === revision) {
      return
    }
    // the extent the navigation handed over is the newer request and outranks the one the document
    // carries, until the user chose a viewport in the map itself
    const extent = !publishedViewport.current && validExtent(previewExtent)
      ? previewExtent
      : owsContext.bbox
    // a document without a usable area of interest leaves the view the map started with
    if (!validExtent(extent)) {
      return
    }
    appliedRevision.current = revision
    // the viewport event a fit ends with is not the map answering the document: the view a fit
    // chose is wider than the area of interest it was asked for and publishing it would grow that
    // area on every load; leaflet ends a fit without animation synchronously
    fitting.current = true
    try {
      map.fitBounds(extentBounds(extent), { animate: false })
      fittedView.current = boundsToExtent(map.getBounds()).join(',')
    } finally {
      fitting.current = false
    }
  }, [map, documentRevision, previewExtent, owsContext])

  // the map answers the document it was given with the viewport the user sees: publishing it when a
  // zoom or pan ended keeps a later export or reload of the document at the same view
  const publishExtent = useCallback(() => {
    if (map === undefined || fitting.current) {
      return
    }
    const extent = boundsToExtent(map.getBounds())
    // the view a fit chose is the same answer as the viewport event of that fit
    if (extent.join(',') === fittedView.current) {
      return
    }
    // a viewport that is not an area of interest, e.g. one panned beyond a pole, leaves the area of
    // interest of the document as it is
    if (!validExtent(extent)) {
      return
    }
    publishedViewport.current = true
    setContextBbox(extent)
  }, [map, setContextBbox])

  const value = useMemo<MapViewerBaseType>(() => {
    return {
      map,
      setMap,
      selectedCrs,
      setSelectedCrs,
      featureCollection,
      atomicGetMapUrls,
      atomicGetFeatureInfoUrls,
      unsupportedFeatures,
      mapLoading,
      reportMapLoading,
      removeMapLoading
    }
  }, [
    map,
    setMap,
    selectedCrs,
    setSelectedCrs,
    featureCollection,
    atomicGetMapUrls,
    atomicGetFeatureInfoUrls,
    unsupportedFeatures,
    mapLoading,
    reportMapLoading,
    removeMapLoading
  ])

  useEffect(() => {
    if (map !== undefined) {
      map.on('move', onMove)
      map.on('moveend', publishExtent)
      return () => {
        map.off('move', onMove)
        map.off('moveend', publishExtent)
      }
    }
  }, [map, onMove, publishExtent])


  return (
    <context.Provider
      value={value}
    >
      {children}
    </context.Provider>
  )

};

export const useMapViewerBase = (): MapViewerBaseType => {
  const ctx = useContext(context)

  if (ctx === undefined) {
    throw new Error('useMapViewerBase must be inside a MapViewerBase')
  }
  return ctx
};
