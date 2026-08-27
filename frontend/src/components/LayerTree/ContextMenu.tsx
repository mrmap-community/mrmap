import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import VpnKeyIcon from '@mui/icons-material/VpnKey';

import DeleteIcon from '@mui/icons-material/Delete';
import SearchIcon from '@mui/icons-material/Search';
import { IconButton, List, ListItem } from '@mui/material';
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import MenuList from '@mui/material/MenuList';
import proj4 from 'proj4';
import { useMemo } from "react";
import { Authentication } from '../../ows-lib/OwsContext/contrib';
import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase";
import { useDialogContextBase } from '../Dialog/DialogContextBase';
import { useMapViewerBase } from '../MapViewer/MapViewerBase';
import { useContextMenuBase } from "./ContextMenuBase";


const ManageAuthenticationItem = () => {
  const { owsContext } = useOwsContextBase()
  const { open } = useDialogContextBase()
  const { node } = useContextMenuBase()

  const feature = useMemo(()=> {
    return owsContext.features.find(feature => feature.id === node.id)
  },[node, owsContext])

  feature?.getWmsOperationByCode("GetCapabilities")?.authenticationId
  feature?.getWmsOperationByCode("GetMap")?.authenticationId

  const authHeaders: Authentication[] = Array.isArray(owsContext.authenticationHeaders) 
      ? owsContext.authenticationHeaders
      : []

  const content = useMemo(()=>{
    return (
      <List>
        {
        
        authHeaders?.map((authenticationHeader) => {
          return <ListItem
            secondaryAction={
              <IconButton edge="end" aria-label="delete">
                <DeleteIcon />
              </IconButton>
            }
            >
              {authenticationHeader.id}
              {authenticationHeader.name}
              {authenticationHeader.value}
            </ListItem>
        })}
      </List>
    )

  },[owsContext])

  if (authHeaders.length < 1)
    {return}

  return (
    <MenuItem
      onClick={() => {
        open("huuhuu", content, "hio")
      }}
    >
      <VpnKeyIcon fontSize="small"/> manage authentication
    </MenuItem>
  )
}


const ZoomToLayerItem = () => {
  const { owsContext } = useOwsContextBase()
  const { map } = useMapViewerBase()
  const { node, close } = useContextMenuBase()

  const feature = node?.properties?.folder
    ? owsContext.findResourceByFolder(node.properties.folder)
    : undefined

  if (!feature?.bbox || feature.bbox.length !== 4) {
    return null
  }

  return (
    <MenuItem
      onClick={() => {
        const [minX, minY, maxX, maxY] = feature.bbox as [
          number,
          number,
          number,
          number
        ]

        const layerCrs = 'EPSG:4326' // feature.properties.referenceSystems?.[0] ?? referenceSystems per layer are not implemented yet

        let sw: [number, number]
        let ne: [number, number]

        if (layerCrs === 'EPSG:4326') {
          sw = [minY, minX]
          ne = [maxY, maxX]
        } else {
          const projection = proj4(layerCrs, 'EPSG:4326')

          const [swLng, swLat] = projection.forward([minX, minY])
          const [neLng, neLat] = projection.forward([maxX, maxY])

          sw = [swLat, swLng]
          ne = [neLat, neLng]
        }
        map?.flyToBounds(
          [sw, ne],
          {
            padding: [20, 20],
            maxZoom: 12,
            duration: 1,
            animate: false,

          }
        )

        close()
      }}
    >
      <SearchIcon fontSize="small" />
      Zoom to layer
    </MenuItem>
  )
}

const MenuItems = () => {
  const { owsContext } = useOwsContextBase()
  const { node } = useContextMenuBase()

  const feature = useMemo(()=> {
    return owsContext.features.find(feature => feature.id === node.id)
  },[node, owsContext])

  if (node === undefined || feature === undefined) return null

  return (
    <MenuList
    >
      {!feature?.isRootNode() ? <MenuItem
        onClick={() => {
          console.log("move up:", node );
        }}
      >
        <ArrowUpwardIcon fontSize="small"/> move up
      </MenuItem> : null}
      {node?.children?.length ?? 0 > 0 ? <MenuItem
        onClick={() => {
          console.log("move down:", node );
        }}
      >
        <ArrowDownwardIcon fontSize="small"/> move down
      </MenuItem> : null}
      <ManageAuthenticationItem/>
      <ZoomToLayerItem/>
    </MenuList>
  )
}


const ContextMenu = () => {
  const {isOpen, close, mouseX, mouseY} = useContextMenuBase()
  
  // Only render Menu if we have valid coordinates
  if (!isOpen || mouseX === undefined || mouseY === undefined) {
    return null
  }
  
  return (
    <Menu
        open={true}
        onClose={close}
        anchorReference="anchorPosition"
        anchorPosition={{ top: mouseY, left: mouseX }}
        anchorOrigin={{
          vertical: "top",
          horizontal: "left",
        }}
        transformOrigin={{
          vertical: "top",
          horizontal: "left",
        }}
      >
        <MenuItems />
      </Menu>
  )
}

export default ContextMenu