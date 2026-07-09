import { ReactNode, useEffect, useMemo, useState } from 'react'
import { Marker, Popup, Tooltip, useMap, useMapEvent } from 'react-leaflet'
import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase"

import proj4 from 'proj4'

import { point, type LatLng } from 'leaflet'
import { Link } from 'react-admin'
import { updateOrAppendSearchParam } from '../../ows-lib/OwsContext/utils'
import { useMapViewerBase } from '../MapViewer/MapViewerBase'
import { AuthImageOverlay } from './AuthImageOverlay'


export interface Tile {
  leafletTile: ReactNode
  getMapUrl?: URL
  getFeatureinfoUrl?: URL
}


const WebMapServiceControl = () => {
  
  const { owsContext } = useOwsContextBase()
  const [position, setPosition] = useState<LatLng | null>(null)
  const [layerPoint, setLayerPoint] = useState<{x: number, y: number} | null>(null) 
   
  const atomicGetMapUrls = useMemo(()=>{
    return owsContext.getOptimizedUrlsByCode(
      "GetMap",
      (feature)=>(
        feature.getWmsOperationByCode("GetMap")?.active === true
      )
    )
  }, [owsContext])

  const atomicGetFeatureInfoUrls = useMemo(()=>{
    return owsContext.getOptimizedUrlsByCode(
      "GetFeatureInfo",
      (feature)=>(
        feature.getWmsOperationByCode("GetFeatureInfo")?.active === true
      )
    )
  }, [owsContext])

  const map = useMap()

  const [bounds, setBounds] = useState(map?.getBounds())
  const [size, setSize] = useState(map?.getSize())
  const { selectedCrs } = useMapViewerBase()

  const bbox = useMemo<[number, number,number, number]>(()=>{

    const sw = bounds?.getSouthWest()
    const ne = bounds?.getNorthEast()
    let minXy = point(sw.lng, sw.lat)
    let maxXy = point(ne.lng, ne.lat)

    if (selectedCrs.stringRepresentation !== 'EPSG:4326') {
      const proj = proj4('EPSG:4326', selectedCrs.wkt)
      minXy = proj.forward(minXy)
      maxXy = proj.forward(maxXy)
    }

    return [minXy.x, minXy.y, maxXy.x, maxXy.y]

  }, [bounds, selectedCrs])

  // Helper function to get auth headers for a GetMap URL
  const getAuthForGetMapUrl = (getMapUrl: string) => {
    const getMapUrlObj = new URL(getMapUrl)
    const getMapBase = `${getMapUrlObj.origin}${getMapUrlObj.pathname}`

    // Find the feature that contains this GetMap URL
    const feature = owsContext.features.find(f => {
      const wmsMeta = f.getWmsOperationByCode("GetMap")
      if (wmsMeta?.href) {
        const wmsUrlObj = new URL(wmsMeta.href)
        const wmsBase = `${wmsUrlObj.origin}${wmsUrlObj.pathname}`
        return wmsBase === getMapBase
      }
      return false
    })

    return undefined
  }

  const tiles = useMemo(() => {
    const _tiles: Tile[] = []

    if (bounds === undefined || size === undefined) {
      return _tiles
    }

    const getMapUrls = [...atomicGetMapUrls].reverse()

  
    getMapUrls.forEach((atomicGetMapUrl, index) => {
      const params = atomicGetMapUrl.searchParams
      const version = params.get('version') ?? params.get('VERSION')

      if (version === '1.3.0') {
        if (selectedCrs.isXyOrder) {
          // no axis order correction needed.
          updateOrAppendSearchParam(params, 'BBOX', `${bbox[0]},${bbox[1]},${bbox[2]},${bbox[3]}`)
        } else {
          updateOrAppendSearchParam(params, 'BBOX',  `${bbox[1]},${bbox[0]},${bbox[3]},${bbox[2]}`)
        }
        updateOrAppendSearchParam(params, 'CRS',  selectedCrs.stringRepresentation)

      } else {
        // always minx,miny,maxx,maxy (minLng,minLat,maxLng,maxLat)
        updateOrAppendSearchParam(params, 'BBOX', `${bbox[0]},${bbox[1]},${bbox[2]},${bbox[3]}`)
        updateOrAppendSearchParam(params, 'SRS',  selectedCrs.stringRepresentation)
      }
      updateOrAppendSearchParam(params, 'WIDTH', size.x.toString())
      updateOrAppendSearchParam(params, 'HEIGHT', size.y.toString())
      updateOrAppendSearchParam(params, 'STYLES', '') // todo: shall be configureable
      _tiles.push(
        {
          leafletTile: <AuthImageOverlay
            key={atomicGetMapUrl.href}
            bounds={bounds}
            interactive={true}
            url={atomicGetMapUrl.href}
            auth={getAuthForGetMapUrl(atomicGetMapUrl.href)}            
          />,
          getMapUrl: atomicGetMapUrl,
          getFeatureinfoUrl: undefined
        }
      )
    })
    
    return _tiles
  }, [bounds, size, atomicGetMapUrls, selectedCrs])
  
  const getFeatureInfoUrls = useMemo(() => {
    if (layerPoint && position && atomicGetFeatureInfoUrls.length > 0) {
      
      const getFeatureInfoUrls = [...atomicGetFeatureInfoUrls].reverse()
      getFeatureInfoUrls.forEach((atomicGetFeatureInfoUrl, index) => {
        const params = atomicGetFeatureInfoUrl.searchParams
        updateOrAppendSearchParam(params, 'I', layerPoint.x.toFixed(0).toString())
        updateOrAppendSearchParam(params, 'J', layerPoint.y.toFixed(0).toString())
        updateOrAppendSearchParam(params, 'X', layerPoint.x.toFixed(0).toString())
        updateOrAppendSearchParam(params, 'Y', layerPoint.y.toFixed(0).toString())
        updateOrAppendSearchParam(params, 'WIDTH', size.x.toString())
        updateOrAppendSearchParam(params, 'HEIGHT', size.y.toString())
        updateOrAppendSearchParam(params, 'LAYERS', params.get('QUERY_LAYERS') ?? params.get('query_layers') ?? '')
        updateOrAppendSearchParam(params, 'INFO_FORMAT', params.get('INFO_FORMAT') ?? params.get('info_format') ?? 'application/json')
        updateOrAppendSearchParam(params, 'FEATURE_COUNT', params.get('FEATURE_COUNT') ?? params.get('feature_count') ?? '10')
        updateOrAppendSearchParam(params, 'STYLES', '') // todo: shall be configureable
        
        const version = params.get('version') ?? params.get('VERSION')

        if (version === '1.3.0') {
          if (selectedCrs.isXyOrder) {
            // no axis order correction needed.
            updateOrAppendSearchParam(params, 'BBOX', `${bbox[0]},${bbox[1]},${bbox[2]},${bbox[3]}`)
          } else {
            updateOrAppendSearchParam(params, 'BBOX',  `${bbox[1]},${bbox[0]},${bbox[3]},${bbox[2]}`)
          }
          updateOrAppendSearchParam(params, 'CRS',  selectedCrs.stringRepresentation)

        } else {
          // always minx,miny,maxx,maxy (minLng,minLat,maxLng,maxLat)
          updateOrAppendSearchParam(params, 'BBOX', `${bbox[0]},${bbox[1]},${bbox[2]},${bbox[3]}`)
          updateOrAppendSearchParam(params, 'SRS',  selectedCrs.stringRepresentation)
        }
        
      })
      return getFeatureInfoUrls
    }
  },[layerPoint, atomicGetFeatureInfoUrls, size, bbox])


  useEffect(() => {
    if (!map) return

    const updateBounds = () => {
      setBounds(map.getBounds())
      setSize(map.getSize())
    }

    updateBounds()
    map.on('resize moveend zoomend', updateBounds)
    return () => {
      map.off('resize moveend zoomend', updateBounds)
    }
  }, [map])

  useMapEvent('contextmenu', (event) => {
    if (atomicGetFeatureInfoUrls.length > 0) {
      setPosition(event.latlng)
      setLayerPoint(event.containerPoint)
    } else {
      setPosition(null)
      setLayerPoint(null)
    }
  })

  return (
    <div>
      {tiles.map(tile => tile.leafletTile)}
      {position && <Marker position={position} >
        <Popup>
          {getFeatureInfoUrls?.map((url, index) => (
              <Link to={url.href} target="_blank" rel="noopener noreferrer" key={index}>
                {url.searchParams.get('QUERY_LAYERS') ?? url.searchParams.get('query_layers') ?? 'Feature Info'}
              </Link>
          ))}
        </Popup>
        <Tooltip direction="top">Click on the marker to see feature info</Tooltip>
      </Marker>  
      }
    </div>
  )

}


export default WebMapServiceControl