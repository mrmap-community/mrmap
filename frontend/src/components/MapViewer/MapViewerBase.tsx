import { createContext, Dispatch, PropsWithChildren, ReactNode, SetStateAction, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { Map } from "leaflet";

import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase";
import { boundsToGeoJSON, featuresToCollection, latLngToGeoJSON } from './utils';

import { OptimizedUrlsMap, OWSResource } from "../../ows-lib/OwsContext/core";
import { Operation } from "../../ows-lib/OwsContext/types";
import { isOperationUrlEqual } from '../../ows-lib/OwsContext/utils';

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
  mapLoading: MapLoadingState
  reportMapLoading: (id: string, status: MapLoadingStatus, error?: MapLoadingError, timing?: number) => void
  removeMapLoading: (id: string) => void
}

const compareOfferingByAuth = (index: number, lastOperation: Operation, operation: Operation) => {

  if (index === 0) {
    return true
  }
  // Check if all offeringA.operations and offeringB.operations have the same "x-authentication-id" value
  const authIdsA = lastOperation['x-authentication-id']
  const authIdsB = operation['x-authentication-id']
  return authIdsA === authIdsB && isOperationUrlEqual(new URL(lastOperation.href), new URL(operation.href))
}


export const context = createContext<MapViewerBaseType | undefined>(undefined)


export const MapViewerBase = ({children}: PropsWithChildren): ReactNode => {
  const { owsContext } = useOwsContextBase()

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

    const errors = requests.map((([id, request]) => request.error)).filter(error => error !== undefined)

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

    const failedFeatures = requests.filter(([id, request]) => request.error !== undefined).flatMap(([id, request]) => request.error?.features || [])


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
      ),
      compareOfferingByAuth
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

  const onMove = useCallback(() => {
    if (map !== undefined) {
      setPosition(map.getCenter())
      setBounds(map.getBounds())
    }
  }, [map])

  const value = useMemo<MapViewerBaseType>(() => {
    return {
      map,
      setMap,
      selectedCrs,
      setSelectedCrs,
      featureCollection,
      atomicGetMapUrls,
      atomicGetFeatureInfoUrls,
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
    mapLoading,
    reportMapLoading,
    removeMapLoading
  ])

  useEffect(() => {
    if (map !== undefined) {
      map.on('move', onMove)
      return () => {
        map.off('move', onMove)
      }
    }
  }, [map, onMove])


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
