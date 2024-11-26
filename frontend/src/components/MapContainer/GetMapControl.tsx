import { ReactNode, useEffect, useMemo, useState } from 'react'
import { ImageOverlay, useMap } from 'react-leaflet'
import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase"

import proj4 from 'proj4'

import { getOptimizedGetMapUrls, updateOrAppendSearchParam } from '../../ows-lib/OwsContext/utils'
import { useMapViewerBase } from '../MapViewer/MapViewerBase'


export interface Tile {
  leafletTile: ReactNode
  getMapUrl?: URL
  getFeatureinfoUrl?: URL
}


const WebMapServiceControl = () => {

  const { trees } = useOwsContextBase()
  
  const atomicGetMapUrls = useMemo(()=>{
    return getOptimizedGetMapUrls(trees)
  }, [trees])

  const map = useMap()

  const [bounds, setBounds] = useState(map?.getBounds())
  const [size, setSize] = useState(map?.getSize())

  const { selectedCrs } = useMapViewerBase()

  const tiles = useMemo(() => {
    const _tiles: Tile[] = []

    if (bounds === undefined || size === undefined) {
      return _tiles
    }
    const sw = bounds.getSouthWest()
    const ne = bounds.getNorthEast()
    let minXy = {x: sw.lng, y: sw.lat}
    let maxXy = {x: ne.lng, y: ne.lat}

    const getMapUrls = [...atomicGetMapUrls].reverse()

    if (selectedCrs.stringRepresentation !== 'EPSG:4326') {
      const proj = proj4('EPSG:4326', selectedCrs.wkt)
      minXy = proj.forward(minXy)
      maxXy = proj.forward(maxXy)
    }

    getMapUrls.forEach((atomicGetMapUrl, index) => {
      const params = atomicGetMapUrl.searchParams
      const version = params.get('version') ?? params.get('VERSION')

      if (version === '1.3.0') {
        if (selectedCrs.isXyOrder) {
          // no axis order correction needed.
          updateOrAppendSearchParam(params, 'BBOX', `${minXy.x},${minXy.y},${maxXy.x},${maxXy.y}`)
        } else {
          updateOrAppendSearchParam(params, 'BBOX',  `${minXy.y},${minXy.x},${maxXy.y},${maxXy.x}`)
        }
        updateOrAppendSearchParam(params, 'CRS',  selectedCrs.stringRepresentation)

      } else {
        // always minx,miny,maxx,maxy (minLng,minLat,maxLng,maxLat)
        updateOrAppendSearchParam(params, 'BBOX', `${minXy.x},${minXy.y},${maxXy.x},${maxXy.y}`)
        updateOrAppendSearchParam(params, 'SRS',  selectedCrs.stringRepresentation)
      }
      updateOrAppendSearchParam(params, 'WIDTH', size.x.toString())
      updateOrAppendSearchParam(params, 'HEIGHT', size.y.toString())
      updateOrAppendSearchParam(params, 'STYLES', '') // todo: shall be configureable
      _tiles.push(
        {
          leafletTile: <ImageOverlay
            key={(Math.random() + 1).toString(36).substring(7)}
            bounds={bounds}
            interactive={true}
            url={atomicGetMapUrl.href}
          />,
          getMapUrl: atomicGetMapUrl,
          getFeatureinfoUrl: undefined
        }
      )
    })
    
    return _tiles
  }, [map?.getBounds(), map?.getSize(), atomicGetMapUrls, selectedCrs])
  


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



  return tiles.map(tile => tile.leafletTile)

}


export default WebMapServiceControl