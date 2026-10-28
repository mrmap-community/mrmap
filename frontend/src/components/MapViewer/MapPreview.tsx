import type { ReactNode } from 'react'
import { MapContainer, ScaleControl } from 'react-leaflet'

import { Box } from '@mui/material'
import { CRS } from 'leaflet'

import WebFeatureServiceControl from '../MapContainer/GetFeatureControl'
import WebMapServiceControl from '../MapContainer/GetMapControl'
import AutoResizeMapContainer from '../MapContainer/ResizeAbleMapContainer'
import { useMapViewerBase } from './MapViewerBase'

/**
 * The map of the viewer on its own: the same leaflet map in the same crs with the same controls
 * which ask every operation of the document for the current viewport, but without the drawers, the
 * layer tree and the settings of the full screen viewer.
 *
 * `MapViewerCore` is the viewer as a screen and needs the drawer and tab list contexts its tree
 * opens; `PreviewMap` of the live preview draws an image and the features one request handed it and
 * does not know the document at all. Neither of them is a map which renders an OWS context inside a
 * card, which is what a preview of a single element asks for, so the shell lives here and both the
 * viewer and the previews use the same controls to render.
 */
const MapPreview = ({ height = 380 }: { height?: number | string }): ReactNode => {
  const { setMap } = useMapViewerBase()

  return (
    <Box sx={{ height, width: '100%', position: 'relative' }}>
      <MapContainer
        ref={setMap}
        center={[51.505, -0.09]}
        zoom={2}
        // Fit the advertised extent without rounding out past a layer's maximum scale.
        zoomSnap={0}
        crs={CRS.EPSG4326}
        maxZoom={20}
        minZoom={0}
        maxBoundsViscosity={0.8}
        scrollWheelZoom={true}
        style={{
          flex: 1, height: '100%', width: '100%', position: 'relative'
        }}
      >
        <AutoResizeMapContainer />
        <WebMapServiceControl />
        <WebFeatureServiceControl />
        <ScaleControl position="topleft" />
      </MapContainer>
    </Box>
  )
}

export default MapPreview
