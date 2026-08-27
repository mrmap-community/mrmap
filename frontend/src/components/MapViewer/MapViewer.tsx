import { useId, type PropsWithChildren, type ReactNode } from 'react'
import { type SimpleShowLayoutProps } from 'react-admin'
import { MapContainer, ScaleControl } from 'react-leaflet'

import { Box, Divider, Stack } from '@mui/material'
import { CRS } from 'leaflet'

import ListGuesser from '../../jsonapi/components/ListGuesser'
import BottomDrawer from '../Drawer/BottomDrawer'
import { DrawerBase } from '../Drawer/DrawerContext'
import RightDrawer from '../Drawer/RightDrawer'
import LayerTree from '../LayerTree/LayerTree'
import WebMapServiceControl from '../MapContainer/GetMapControl'
import { TabListBase } from '../Tab/TabListContext'
import { Tabs } from '../Tab/Tabs'
import MapSettingsEditor from './MapSettings'
import { MapViewerBase, useMapViewerBase } from './MapViewerBase'
import { OwsContextActionButtons } from './OwsContextGuiActions/OwsContextActionButtons'
import StatusBar from './StatusBar'


const style = {
  height: '100%',
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
  const {map, setMap} = useMapViewerBase()
  
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
              scrollWheelZoom={true}
              style={{
                flex: 1, height: '100%', width: '100%', position: 'relative'
              }}
            >
              <WebMapServiceControl />
              <ScaleControl position="topleft" />
            </MapContainer>
          </Box>
          <RightDrawer
            leftComponentId={containerId}
            callback={() => map?.invalidateSize()}
          >
            <Stack
              sx={{ 
                height: '100%',
                direction: "column",
                justifyContent: "space-between",
              }}
            >
              <Box>
                <OwsContextActionButtons />
                <Divider/>
              </Box>
              <Box sx={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
                <LayerTree />
              </Box>
              <Box>
                <Divider />
                <StatusBar />
              </Box>
            </Stack>
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
                    value: 'settings',
                    children: <MapSettingsEditor/>
                  },
                  closeable: false
                }, {
                  tab: { label: 'WMS List' },
                  tabPanel: {
                    value: 'wms-list',
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
      <MapViewerBase>
        <MapViewerCore />
        {children}
      </MapViewerBase>
  )
}

export default MapViewer
