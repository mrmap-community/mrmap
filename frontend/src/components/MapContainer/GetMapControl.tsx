import { Fragment, ReactNode, useEffect, useMemo, useState } from 'react'
import { Link, useTranslate } from 'react-admin'
import { Marker, Popup, Tooltip, useMap, useMapEvent } from 'react-leaflet'

import { Alert, Stack, Typography } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { point, type LatLng } from 'leaflet'
import proj4 from 'proj4'

import { resolveOperationAuthentication } from '../../ows-lib/OwsContext/authentication'
import { OptimizedUrlsMap } from '../../ows-lib/OwsContext/core'
import { updateOrAppendSearchParam } from '../../ows-lib/OwsContext/utils'
import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase"
import { useMapViewerBase } from '../MapViewer/MapViewerBase'
import { FeatureInfoResult } from '../Resource/Generic/ServiceShow/LivePreview/LivePreview'
import { AuthImageOverlay } from './AuthImageOverlay'


const VIEWPORT_DEBOUNCE_MS = 300

export interface Tile {
  leafletTile: ReactNode
  getMapUrl?: URL
  getFeatureinfoUrl?: URL
}



const FeatureInfoRequest = ({ request }: { request: OptimizedUrlsMap }) => {
  const { owsContext } = useOwsContextBase();
  const translate = useTranslate();
  const { headers, error: authError } = resolveOperationAuthentication(owsContext, request.operations[0], request.url.href);
  const query = useQuery({
    queryKey: ['viewerFeatureInfo', request.url.href, headers ? Array.from(headers) : undefined, authError],
    enabled: !authError,
    retry: false,
    gcTime: 0,
    queryFn: async ({ signal }) => {
      const response = await fetch(request.url.href, { headers, signal, redirect: 'error', credentials: 'omit' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return { text: await response.text(), contentType: response.headers.get('content-type') ?? 'text/plain' };
    },
  });
  if (authError) return <Alert severity="error">{translate(`viewerAuth.${authError}`)}</Alert>;
  const layers = request.url.searchParams.get('QUERY_LAYERS') ?? request.url.searchParams.get('query_layers') ?? 'Feature Info';
  return <Stack spacing={0.5}>
    <Typography variant="subtitle2">{layers}</Typography>
    {query.isPending && translate('viewerFeatureInfo.loading')}
    {query.error && <Stack spacing={0.5}>
      <Alert severity="error">{translate('viewerFeatureInfo.error')}</Alert>
      <Link to={request.url.href} target="_blank" rel="noopener noreferrer">{translate('viewerFeatureInfo.raw')}</Link>
    </Stack>}
    {query.data && <FeatureInfoResult {...query.data} />}
  </Stack>;
};

const WebMapServiceControl = () => {
  const map = useMap()
  const translate = useTranslate()
  const [bounds, setBounds] = useState(map?.getBounds())
  const [size, setSize] = useState(map?.getSize())
  const { owsContext } = useOwsContextBase()
  const { selectedCrs, atomicGetMapUrls, atomicGetFeatureInfoUrls } = useMapViewerBase()
  const [position, setPosition] = useState<LatLng | null>(null)
  const [layerPoint, setLayerPoint] = useState<{x: number, y: number} | null>(null) 

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

  const tiles = useMemo(() => {
    const _tiles: Tile[] = []

    if (bounds === undefined || size === undefined) {
      return _tiles
    }

    const getMapUrls = [...atomicGetMapUrls].reverse()

  
    getMapUrls.forEach((atomicGetMapUrl) => {
      const params = atomicGetMapUrl.url.searchParams
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
      if (![...params.keys()].some(key => key.toUpperCase() === 'STYLES')) {
        updateOrAppendSearchParam(params, 'STYLES', '')
      }
      const authentication = resolveOperationAuthentication(owsContext, atomicGetMapUrl.operations[0], atomicGetMapUrl.url.href)
      _tiles.push(
        {
          leafletTile: <AuthImageOverlay
            key={atomicGetMapUrl.url.href}
            bounds={bounds}
            interactive={true}
            optimiuedUrl={atomicGetMapUrl}
            auth={authentication.headers}
            authenticationError={authentication.error}
          />,
          getMapUrl: atomicGetMapUrl.url,
          getFeatureinfoUrl: undefined
        }
      )
    })
    
    return _tiles
  }, [bounds, size, atomicGetMapUrls, selectedCrs, owsContext])
  
  const getFeatureInfoUrls = useMemo(() => {
    if (layerPoint && position && atomicGetFeatureInfoUrls.length > 0) {
      
      const getFeatureInfoUrls = [...atomicGetFeatureInfoUrls].reverse()
      getFeatureInfoUrls.forEach((atomicGetFeatureInfoUrl) => {
        const params = atomicGetFeatureInfoUrl.url.searchParams
        const version = params.get('version') ?? params.get('VERSION')
        // WMS 1.3.0 asks for the pixel through I/J, earlier versions through X/Y;
        // sending the foreign pair makes strict servers reject or misplace the query.
        if (version === '1.3.0') {
          updateOrAppendSearchParam(params, 'I', layerPoint.x.toFixed(0).toString())
          updateOrAppendSearchParam(params, 'J', layerPoint.y.toFixed(0).toString())
          params.delete('X')
          params.delete('Y')
        } else {
          updateOrAppendSearchParam(params, 'X', layerPoint.x.toFixed(0).toString())
          updateOrAppendSearchParam(params, 'Y', layerPoint.y.toFixed(0).toString())
          params.delete('I')
          params.delete('J')
        }
        updateOrAppendSearchParam(params, 'WIDTH', size.x.toString())
        updateOrAppendSearchParam(params, 'HEIGHT', size.y.toString())
        if (![...params.keys()].some(key => key.toUpperCase() === 'LAYERS')) {
          updateOrAppendSearchParam(params, 'LAYERS', params.get('QUERY_LAYERS') ?? params.get('query_layers') ?? '')
        }
        updateOrAppendSearchParam(params, 'INFO_FORMAT', params.get('INFO_FORMAT') ?? params.get('info_format') ?? 'application/json')
        updateOrAppendSearchParam(params, 'FEATURE_COUNT', params.get('FEATURE_COUNT') ?? params.get('feature_count') ?? '10')
        if (![...params.keys()].some(key => key.toUpperCase() === 'STYLES')) {
          updateOrAppendSearchParam(params, 'STYLES', '')
        }
        
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

    let viewportUpdateTimeout: ReturnType<typeof setTimeout> | undefined
    const scheduleViewportUpdate = () => {
      if (viewportUpdateTimeout) {
        clearTimeout(viewportUpdateTimeout)
      }
      viewportUpdateTimeout = setTimeout(updateBounds, VIEWPORT_DEBOUNCE_MS)
    }

    updateBounds()
    map.on('viewreset moveend zoomend', scheduleViewportUpdate)
    return () => {
      map.off('viewreset moveend zoomend', scheduleViewportUpdate)
      if (viewportUpdateTimeout) {
        clearTimeout(viewportUpdateTimeout)
      }
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
    <Fragment>
      {tiles.map(tile => tile.leafletTile)}
      {position && <Marker position={position} >
        <Popup>
          {getFeatureInfoUrls?.map((url) => (
              <FeatureInfoRequest request={url} key={url.url.href} />
          ))}
        </Popup>
        <Tooltip direction="top">{translate('viewerFeatureInfo.tooltip')}</Tooltip>
      </Marker>  
      }
    </Fragment>
  )

}


export default WebMapServiceControl