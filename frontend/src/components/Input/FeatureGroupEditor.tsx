import type { GeoJSON as GeoJSONType, MultiPolygon } from 'geojson';

import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import { type ReactNode, useCallback, useEffect, useRef } from 'react';



import L from 'leaflet';
import { useMap } from 'react-leaflet';
import { GeomanControl } from '../GeomanControl';
import Events from '../GeomanControl/Events';

export interface GeoEditorProps {
  geoJson?: GeoJSONType
  geoJsonCallback?: (multiPolygon: MultiPolygon) => void
  editable?: boolean
}



const FeatureGroupEditor = ({
  geoJson,
  geoJsonCallback,
  editable = true,
}: GeoEditorProps): ReactNode => {
  const map = useMap()
  const initializeRef = useRef(false)
  
  const updateGeoJson = useCallback((event: any) => {
    const multiPolygon: MultiPolygon = {
      type: 'MultiPolygon',
      coordinates: []
    }

    map.eachLayer((layer) => {
      if (layer instanceof L.Polygon) {
        const geometry = layer.toGeoJSON().geometry
        if (geometry.type === 'MultiPolygon'){
          multiPolygon.coordinates.push(...geometry.coordinates)
        } else {
          multiPolygon.coordinates.push(geometry.coordinates)
        }
      }
    })
    geoJsonCallback && geoJsonCallback(multiPolygon)
  }, [map])

  useEffect(() => {
    if (geoJson && !initializeRef.current) {
      initializeRef.current = true
      
      try {
        const geoJSONLayer = L.geoJSON(geoJson)
        map.addLayer(geoJSONLayer)
        const bounds = geoJSONLayer.getBounds()
        if (Object.keys(bounds).length > 1) {
          map.flyToBounds(bounds, { duration: 0.3 })
        }
      } catch (error) {
        console.error('Error adding GeoJSON layer:', error)
      }    
    }
  }, [map, geoJson])

  return (
    <>
    {editable ? 
      <GeomanControl 
        position="topright" 
        drawCircle={false}
        drawCircleMarker={false}
        drawMarker={false}
        drawText={false}
        drawPolyline={false}
        oneBlock={false}
        rotateMode={false}
      />
        
      : null}
      {editable ?
        <Events 
        onCreate={updateGeoJson}
        onUpdate={updateGeoJson}
        onRemove={updateGeoJson}
      />: null}
      
    </>
    
  )
}

export default FeatureGroupEditor
