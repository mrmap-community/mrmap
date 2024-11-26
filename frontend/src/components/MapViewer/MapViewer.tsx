import { useId, useState, type PropsWithChildren, type ReactNode } from 'react'
import { type SimpleShowLayoutProps } from 'react-admin'
import { MapContainer, ScaleControl } from 'react-leaflet'

import { Box } from '@mui/material'
import { CRS, type Map } from 'leaflet'

import ListGuesser from '../../jsonapi/components/ListGuesser'
import { OwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase'
import BottomDrawer from '../Drawer/BottomDrawer'
import { DrawerBase } from '../Drawer/DrawerContext'
import RightDrawer from '../Drawer/RightDrawer'
import LayerTree from '../LayerTree/LayerTree'
import FeatureInfoControl from '../MapContainer/FeatureInfoControl'
import WebMapServiceControl from '../MapContainer/GetMapControl'
import OwsContextControl from '../MapContainer/OwsContextControl'
import { TabListBase } from '../Tab/TabListContext'
import { Tabs } from '../Tab/Tabs'
import MapSettingsEditor from './MapSettings'
import { MapViewerBase } from './MapViewerBase'
import { OwsContextActionButtons } from './OwsContextGuiActions/OwsContextActionButtons'
const style = {
  position: 'relative',
  //  display: 'flex',
  width: '100%',
  height: 'calc(100vh - 50px)'
  // maxHeight: 'calc(100vh - 50px !important)'
}

export interface WMSLayerTreeProps extends Partial<SimpleShowLayoutProps> {

}

export interface Tile {
  leafletTile: ReactNode
  getMapUrl?: URL
  getFeatureinfoUrl?: URL
}

const MapViewerCore = (): ReactNode => {
  const containerId = useId()
  const [map, setMap] = useState<Map>()
 
  return (
      <DrawerBase>
        <TabListBase>
          <Box id={containerId} sx={{ ...style }}>
            <MapContainer
              ref={setMap}
              center={[51.505, -0.09]}
              zoom={2}
              crs={CRS.EPSG4326}
              maxZoom={20}
              minZoom={0}
              maxBoundsViscosity={0.8}
              continuousWorld={true}
              scrollWheelZoom={true}
              style={{
                flex: 1, height: '100%', width: '100%', position: 'relative'
              }}
            >
              <OwsContextControl />
              <WebMapServiceControl />
              <FeatureInfoControl/>
              <ScaleControl position="topleft" />
            </MapContainer>
          </Box>
          <RightDrawer
            leftComponentId={containerId}
            callback={() => map?.invalidateSize()}
          >
            <OwsContextActionButtons />
            <LayerTree/>
          </RightDrawer>
          <BottomDrawer
            aboveComponentId={containerId}
            callback={() => map?.invalidateSize()}
          >
            <Tabs
              defaultTabs={
                [{
                  tab: { label: 'Map Settings' },
                  tabPanel: {
                    children: <MapSettingsEditor/>
                  },
                  closeable: false
                }, {
                  tab: { label: 'WMS List' },
                  tabPanel: {
                    children: <ListGuesser
                      resource='WebMapService'
                      onRowClick={(resource) => {
                        console.log('clicked: ',resource)
                      }}
                    />
                  },
                  closeable: false
                }]
              }
            />
          </BottomDrawer>
        </TabListBase>
      </DrawerBase>
  )
}

const MapViewer = ({ children }: PropsWithChildren): ReactNode => {
  return (
    <OwsContextBase>
      <MapViewerBase>
        <MapViewerCore />
        {children}
      </MapViewerBase>
    </OwsContextBase>

  )
}

export default MapViewer
