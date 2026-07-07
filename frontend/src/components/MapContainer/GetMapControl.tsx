import { ReactNode, useEffect, useMemo, useState } from 'react'
import { Marker, useMap, useMapEvent } from 'react-leaflet'
import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase"

import proj4 from 'proj4'

import { point, type LatLng } from 'leaflet'
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
  
  // TODO: atomicGetMapUrls depends also on authorization.
  
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
    console.log('new bbox')

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

    if (feature) {
      const getCapOp = feature.getWmsOperationByCode("GetCapabilities")
      if (getCapOp?.href && owsContext.capabilititesMap[getCapOp.href]?.headers) {
        return owsContext.capabilititesMap[getCapOp.href].headers
      }
    }
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
            key={(Math.random() + 1).toString(36).substring(7)}
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
    if (!getFeatureInfoUrls?.length) {
      return
    }

    const fetchFeatureInfo = async () => {
      try {
        const responses = await Promise.all(
          getFeatureInfoUrls.map((url) => fetch(url.toString()))
        )
        console.log('responses: ', responses)
      } catch (error) {
        console.error('Error fetching GetFeatureInfo:', error)
      }
    }

    void fetchFeatureInfo()
  }, [getFeatureInfoUrls])

  useEffect(() => {
    if (map !== undefined && map !== null){
      setBounds(map.getBounds())
      setSize(map.getSize())
      map.addEventListener('resize moveend zoomend', (event) => {
        setBounds(map.getBounds())
        setSize(map.getSize())
      })
    }
  }, [map])

  useMapEvent('contextmenu', (event) => {

    if (atomicGetFeatureInfoUrls.length > 0) {
      setPosition(event.latlng)
      setLayerPoint(event.containerPoint)
      console.log(event.containerPoint, event.layerPoint)
      console.log('hoho')
    } else {
      console.log('haha')
      setPosition(null)
      setLayerPoint(null)
    }
  })

  return (
    <div>
      {tiles.map(tile => tile.leafletTile)}
      {position && <Marker position={position} />}
    </div>
  )

}


export default WebMapServiceControl