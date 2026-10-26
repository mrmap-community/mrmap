import { useCallback, useId, type PropsWithChildren, type ReactNode } from 'react'
import { useTranslate, type SimpleShowLayoutProps } from 'react-admin'
import { MapContainer, ScaleControl } from 'react-leaflet'
import { useLocation } from 'react-router-dom'

import { Box, Divider, Stack } from '@mui/material'
import { CRS } from 'leaflet'

import ListGuesser from '../../jsonapi/components/ListGuesser'
import Drawer from '../Drawer/Drawer'
import { DrawerBase, type DrawerState, useDrawerContext } from '../Drawer/DrawerContext'
import { ContextMenuBase } from '../LayerTree/ContextMenu/ContextMenuBase'
import LayerTree, { LayerControlsPanel } from '../LayerTree/LayerTree'
import WebFeatureServiceControl from '../MapContainer/GetFeatureControl'
import WebMapServiceControl from '../MapContainer/GetMapControl'
import { TabListBase, useTabListContext } from '../Tab/TabListContext'
import { Tabs } from '../Tab/Tabs'
import MapSettingsEditor from './MapSettings'
import { MapViewerBase, useMapViewerBase } from './MapViewerBase'
import { OwsContextActionButtons } from './OwsContextGuiActions/OwsContextActionButtons'
import StatusBar from './StatusBar'


const style = {
  height: '100%',
}

/** The map viewer's two drawers keep the store keys and defaults they had
 *  before the consolidation, so persisted settings survive the update. */
const RIGHT_DRAWER_DEFAULTS: DrawerState = { isOpen: false, height: 'calc(100vh - 50px)', width: '20vw' }
const BOTTOM_DRAWER_DEFAULTS: DrawerState = { isOpen: false, height: '30vh', width: '100vw' }

export type WMSLayerTreeProps = Partial<SimpleShowLayoutProps>;

export interface Tile {
  leafletTile: ReactNode
  getMapUrl?: URL
  getFeatureinfoUrl?: URL
}

const ViewerLayerControls = ({ children }: PropsWithChildren) => {
  const { openDrawer } = useDrawerContext();
  const { setTabList } = useTabListContext();
  const open = useCallback(() => {
    openDrawer('bottomdrawer', true);
    setTabList(previous => ({ ...previous, activeTab: '2' }));
  }, [openDrawer, setTabList]);
  return <ContextMenuBase onOpenControls={open}>{children}</ContextMenuBase>;
};

export const MapViewerCore = (): ReactNode => {
  const containerId = useId()
  const {map, setMap} = useMapViewerBase()
  const translate = useTranslate()

  return (
      <DrawerBase>
        <TabListBase>
          <ViewerLayerControls>
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
              <WebFeatureServiceControl />
              <ScaleControl position="topleft" />
            </MapContainer>
          </Box>
          <Drawer
            anchor="right"
            instanceKey="rightdrawer"
            defaults={RIGHT_DRAWER_DEFAULTS}
            targetId={containerId}
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
          </Drawer>
          <Drawer
            anchor="bottom"
            instanceKey="bottomdrawer"
            defaults={BOTTOM_DRAWER_DEFAULTS}
            targetId={containerId}
            callback={() => map?.invalidateSize()}
          >
            <Box sx={{ '& .MuiTabPanel-root': { p: 1.5 } }}>
            <Tabs scrollable
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
                }, {
                  tab: { label: translate('viewerControls.title') },
                  tabPanel: { value: 'layer-settings', children: <LayerControlsPanel /> },
                  closeable: false
                }]
              }
            />
            </Box>
          </Drawer>
          </ViewerLayerControls>
        </TabListBase>
      </DrawerBase>
  )
}

const MapViewer = ({ children }: PropsWithChildren): ReactNode => {
  const location = useLocation()
  return (
      <MapViewerBase previewExtent={location.state?.previewExtent}>
        <MapViewerCore />
        {children}
      </MapViewerBase>
  )
}

export default MapViewer
