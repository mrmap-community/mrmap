import { Dispatch, PropsWithChildren, ReactNode, SetStateAction, createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { Map } from "leaflet";

import { boundsToGeoJSON, featuresToCollection, latLngToGeoJSON } from './utils';


export interface CRS {
  stringRepresentation: string
  isXyOrder: boolean
  wkt: string
}

export interface MapViewerBaseType {
  map: Map
  setMap: Dispatch<SetStateAction<Map>>
  selectedCrs: CRS
  setSelectedCrs: Dispatch<SetStateAction<CRS>>
  featureCollection: string
}

export const context = createContext<MapViewerBaseType | undefined>(undefined)


export const MapViewerBase = ({children}: PropsWithChildren): ReactNode => {

  const [map, setMap] = useState<Map>()
  const [position, setPosition] = useState(() => map?.getCenter())
  const [bounds, setBounds] = useState(() => map?.getBounds())

  const [selectedCrs, setSelectedCrs] = useState<CRS>({stringRepresentation: 'EPSG:4326', isXyOrder: false, wkt: 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]'})


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
      featureCollection
    }
  }, [
    map,
    setMap,
    selectedCrs,
    setSelectedCrs,
    featureCollection
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
