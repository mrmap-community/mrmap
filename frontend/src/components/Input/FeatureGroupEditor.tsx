import type { GeoJSON as GeoJSONType, MultiPolygon } from 'geojson';

import { Fragment, type ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslate } from 'react-admin';
import { useMap } from 'react-leaflet';

import { Alert } from '@mui/material';
// Geoman extends the Leaflet global during module initialization.
import L from 'leaflet';

import { GeomanControl } from '../GeomanControl';
import Events from '../GeomanControl/Events';
import { normalizeGeoJson } from './normalizeGeoJson';

import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";

export interface GeoEditorProps {
  geoJson?: GeoJSONType | string
  geoJsonCallback?: (multiPolygon: MultiPolygon) => void
  editable?: boolean
}



const FeatureGroupEditor = ({
  geoJson,
  geoJsonCallback,
  editable = true,
}: GeoEditorProps): ReactNode => {
  const map = useMap()
  const translate = useTranslate()
  const geoJsonLayerRef = useRef<L.GeoJSON | null>(null)
  // Only a value that reached the map with drawable bounds keeps the card
  // free of the hint; absent or unusable values ask for it explicitly, so an
  // empty map is never just an empty map.
  const [showNoGeometryHint, setShowNoGeometryHint] = useState(false)

  const updateGeoJson = useCallback(() => {
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
    // whatever the user left on the map is what the card shows: the hint is
    // only for a card without anything drawable, so it follows the drawing
    setShowNoGeometryHint(multiPolygon.coordinates.length === 0)
  }, [map, geoJsonCallback])

  useEffect(() => {
    const geometry = normalizeGeoJson(geoJson)
    if (geometry === undefined) {
      if (geoJson !== undefined && geoJson !== null && geoJson !== '') {
        console.error('Error adding GeoJSON layer: value has no usable GeoJSON type:', {
          typeof: typeof geoJson,
          type: (geoJson as { type?: unknown })?.type ?? null,
        })
      }
      setShowNoGeometryHint(true)
      return
    }
    try {
      const geoJSONLayer = L.geoJSON(geometry)
      geoJsonLayerRef.current = geoJSONLayer
      map.addLayer(geoJSONLayer)
      const bounds = geoJSONLayer.getBounds()
      if (bounds.isValid()) {
        map.flyToBounds(bounds, { duration: 0.3 })
        setShowNoGeometryHint(false)
      } else {
        // valid GeoJSON without a single position (empty collection, null
        // geometry): nothing to show, so say so instead of staying silent
        setShowNoGeometryHint(true)
      }
    } catch (error) {
      console.error('Error adding GeoJSON layer:', error, {
        typeof: typeof geoJson,
        type: (geoJson as { type?: unknown })?.type ?? null,
      })
      setShowNoGeometryHint(true)
    }

    // ✅ Cleanup on unmount
    return () => {
      if (geoJsonLayerRef.current) {
        map.removeLayer(geoJsonLayerRef.current)
        geoJsonLayerRef.current = null
      }
    }
  }, [map, geoJson])

  // TODO: on unmount, the geoJson shall be removed from the map.

  return (
    <Fragment>
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
      {showNoGeometryHint ? (
        // the map is a control-less card here, so the hint rides on top of it
        // the same way the explorer's search-area button does; it is words
        // only, so it must never swallow the clicks of the controls it covers
        <Alert
          severity="info"
          sx={{
            position: 'absolute',
            zIndex: 1000,
            top: 12,
            left: 12,
            maxWidth: '80%',
            pointerEvents: 'none',
          }}
        >
          {translate('datasetExplorer.missingCoverage')}
        </Alert>
      ) : null}
      
    </Fragment>
    
  )
}

export default FeatureGroupEditor
