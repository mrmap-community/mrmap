import { createContext, Dispatch, PropsWithChildren, ReactNode, SetStateAction, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { Map } from "leaflet";

import { getUnsupportedReasons, isRequestedByActivation } from "../../ows-lib/OwsContext/capabilities";
import { OptimizedUrlsMap, OWSResource } from "../../ows-lib/OwsContext/core";
import { isWithinScaleLimits, scaleDenominatorForMap } from "../../ows-lib/OwsContext/scales";
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
  /**
   * The GetFeatureInfo requests of the queryable layers, one per queried layer: a service may spend
   * the FEATURE_COUNT of a request naming several layers on its first layers and leave the rest
   * empty, so every layer is asked on its own while the map stays batched.
   */
  atomicGetFeatureInfoUrls: OptimizedUrlsMap[]
  /**
   * The resources the document asks to render but this viewer cannot: they are kept visible by
   * name while the supported resources keep rendering, so that a partially rendered map is not
   * mistaken for the complete context.
   */
  unsupportedFeatures: OWSResource[]
  /**
   * The scale denominator of the current view, measured with the 0.28 mm pixel convention the WMS
   * scale type is stated in, or undefined while the map cannot answer its view. Layers advertise
   * their scale limits with it.
   */
  scaleDenominator: number | undefined
  mapLoading: MapLoadingState
  reportMapLoading: (id: string, status: MapLoadingStatus, error?: MapLoadingError, timing?: number) => void
  removeMapLoading: (id: string) => void
  /**
   * The opacity a user gave the layers of this viewer session, keyed by the folder of the resource
   * and bounded to 0..1. A layer without a value is fully opaque, which keeps the image transparency
   * or the vector styling it comes with; the values are not part of the OWS context.
   */
  layerOpacity: Record<string, number>
  /** the opacity the given resources render with, which is one value shared by a map request */
  opacityOf: (features: OWSResource[]) => number
  /** gives a layer its opacity, bounded to 0..1; a layer not asked for stays fully opaque */
  setLayerOpacity: (folder: string, opacity: number) => void
  /**
   * The timestamp the image drawn on the map answers for, keyed by the folder of a time-enabled
   * layer: the empty string for a server-default image which carries no time, and no entry for a
   * layer whose overlay draws nothing. While a newly selected frame is still on its way, the map
   * keeps showing the previous one; this answers which observation the user actually sees.
   */
  displayedTimes: Record<string, string>
  /** reports which timestamp the image of a layer shows; undefined takes the answer back */
  setDisplayedTime: (folder: string, time: string | undefined) => void
  /**
   * The timelines open in this viewer session, counted by the folder of their layer: the settings panel of
   * a layer and its pinned timeline both work through its times. Only the frames of those layers are
   * buffered — a viewer works with one layer at a time, and images fetched ahead for the layers nobody is
   * working with would cost bandwidth and memory on every pan of the map (#705).
   */
  timelines: Record<string, number>
  /** a mounted timeline claims the frames of its layer; giving the claim back releases them */
  claimTimeline: (folder: string, claimed: boolean) => void
  /**
   * The timeline animation of the viewer session: the layer whose advertised times playback
   * advances through, with its frames per second and whether it loops at the end of the range.
   * One animation plays at a time, and only one selected or pinned layer is animated (#705).
   */
  animation: TimelineAnimation | undefined
  /** starts animating the given layer, or stops the animation when it is given undefined */
  setAnimation: (animation: TimelineAnimation | undefined) => void
}

export interface TimelineAnimation {
  folder: string
  fps: number
  loop: boolean
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

  const [scaleDenominator, setScaleDenominator] = useState<number>()

  // the scale limits of a layer are measured against the scale of the current view, so every zoom,
  // pan and resize answers which active layers are rendered and which of them are out of scale
  useEffect(() => {
    if (map === undefined) {
      return
    }
    const updateScaleDenominator = () => {
      setScaleDenominator(scaleDenominatorForMap(map))
    }
    updateScaleDenominator()
    map.on('zoomend resize moveend', updateScaleDenominator)
    return () => {
      map.off('zoomend resize moveend', updateScaleDenominator)
    }
  }, [map])


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

  // while a newly selected time frame is still arriving, the map keeps showing the previous
  // image; controls and identify ask this record which observation the user actually sees (#705)
  const [displayedTimes, setDisplayedTimes] = useState<Record<string, string>>({})

  const setDisplayedTime = useCallback((folder: string, time?: string) => {
    setDisplayedTimes((previous) => {
      if (time === undefined) {
        if (!(folder in previous)) return previous
        const next = { ...previous }
        delete next[folder]
        return next
      }
      return previous[folder] === time ? previous : { ...previous, [folder]: time }
    })
  }, [])

  // playback belongs to one selected or pinned time-enabled layer at a time; the control which
  // offers it reads this state, so its buttons stay honest wherever it is opened (#705)
  const [animation, setAnimation] = useState<TimelineAnimation>()
  // which layers a viewer works the times of, i.e. whose timeline is open; several controls can show the
  // timeline of one layer, so the claims are counted and the frames are given back by the last of them
  const [timelines, setTimelines] = useState<Record<string, number>>({})

  const claimTimeline = useCallback((folder: string, claimed: boolean) => {
    setTimelines((previous) => {
      const claims = (previous[folder] ?? 0) + (claimed ? 1 : -1)
      if (claims > 0) return { ...previous, [folder]: claims }
      if (!(folder in previous)) return previous
      const next = { ...previous }
      delete next[folder]
      return next
    })
  }, [])

  // the transparency a user gives a layer belongs to the viewer session and not to the document:
  // an exported context keeps the layers as they were imported, while the viewer blends them the
  // way the user asked for (#750)
  const [layerOpacity, setLayerOpacityState] = useState<Record<string, number>>({})

  const setLayerOpacity = useCallback((folder: string, opacity: number) => {
    const bounded = Math.min(1, Math.max(0, opacity))
    setLayerOpacityState(previous =>
      previous[folder] === bounded ? previous : { ...previous, [folder]: bounded })
  }, [])

  // a map request answers the layers it names with one image, so the request carries one opacity
  // and every layer of it shares that value
  const opacityOf = useCallback((features: OWSResource[]) =>
    layerOpacity[features[0]?.properties.folder ?? ''] ?? 1, [layerOpacity])

  // a layer which is active but out of scale stays active: only its rendering is temporarily
  // suppressed, and the feature info of a layer answers independently of the scale limits its
  // rendering obeys (#606)
  const atomicGetMapUrls = useMemo(()=>{
    const blendingOf = (feature: OWSResource) =>
      layerOpacity[feature.properties.folder ?? ''] ?? 1
    const isRenderable = (feature: OWSResource) =>
      feature.getWmsOperationByCode("GetMap")?.active === true &&
      isWithinScaleLimits(feature.properties, scaleDenominator)
    const documentOrder: Record<string, number> = {}
    owsContext.features.forEach((feature, index) => {
      documentOrder[feature.properties.folder ?? ''] = index
    })
    // one image blends every layer it draws the same way, so each blending asks for map requests
    // of its own; the requests keep the order of the document, which is the order in which the map
    // draws the layers one above the other (#750)
    const blendings = Array.from(new Set(owsContext.features.filter(isRenderable).map(blendingOf)))
    return blendings
      .flatMap(blending => owsContext.getOptimizedUrlsByCode(
        "GetMap",
        feature => isRenderable(feature) && blendingOf(feature) === blending,
      ))
      .sort((first, second) =>
        (documentOrder[first.features[0]?.properties.folder ?? ''] ?? 0) -
        (documentOrder[second.features[0]?.properties.folder ?? ''] ?? 0))
  }, [owsContext, scaleDenominator, layerOpacity])

  // every queryable layer is queried on its own while the layers of one service stay batched into
  // one map request - see getFeatureInfoRequestsPerLayer for the reason (#700)
  const atomicGetFeatureInfoUrls = useMemo(()=>{
    return owsContext.getFeatureInfoRequestsPerLayer(
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
      scaleDenominator,
      mapLoading,
      reportMapLoading,
      removeMapLoading,
      layerOpacity,
      opacityOf,
      setLayerOpacity,
      displayedTimes,
      setDisplayedTime,
      timelines,
      claimTimeline,
      animation,
      setAnimation
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
    scaleDenominator,
    mapLoading,
    reportMapLoading,
    removeMapLoading,
    layerOpacity,
    opacityOf,
    setLayerOpacity,
    displayedTimes,
    setDisplayedTime,
    timelines,
    claimTimeline,
    animation,
    setAnimation
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
