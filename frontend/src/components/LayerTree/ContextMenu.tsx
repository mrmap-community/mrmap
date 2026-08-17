import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import VpnKeyIcon from '@mui/icons-material/VpnKey';

import DeleteIcon from '@mui/icons-material/Delete';
import { IconButton, List, ListItem } from '@mui/material';
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import { useMemo } from "react";
import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase";
import { useDialogContextBase } from '../Dialog/DialogContextBase';
import { useContextMenuBase } from "./ContextMenuBase";


const ManageAuthenticationItem = () => {
  const { owsContext } = useOwsContextBase()
  const { open, close } = useDialogContextBase()
  const { node } = useContextMenuBase()

  const feature = useMemo(()=> {
    return owsContext.features.find(feature => feature.id === node.id)
  },[node, owsContext])

  feature?.getWmsOperationByCode("GetCapabilities")?.authenticationId
  feature?.getWmsOperationByCode("GetMap")?.authenticationId

  const content = useMemo(()=>{
    return (
      <List>
        {owsContext.authentications.map(authentication => {
          return <ListItem
            secondaryAction={
              <IconButton edge="end" aria-label="delete">
                <DeleteIcon />
              </IconButton>
            }
            >
              {authentication.id}
              {authentication.type}
            </ListItem>
        })}
      </List>
    )

  },[owsContext])

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


const MenuItems = () => {
  const { owsContext, moveFeature } = useOwsContextBase()
  
  const { node } = useContextMenuBase()

  const feature = useMemo(()=> {
    return owsContext.features.find(feature => feature.id === node.id)
  },[node, owsContext])

  if (node === undefined || feature === undefined) return null

  return (
    <div>
      {!feature?.isRootNode() ? <MenuItem
        onClick={() => {
          console.log("move up:", node );
          
        }}
      >
        <ArrowUpwardIcon fontSize="small"/> move up
      </MenuItem> : <div></div>}
      {node?.children.length > 0 ? <MenuItem
        onClick={() => {
          console.log("move down:", node );
          
        }}
      >
        <ArrowDownwardIcon fontSize="small"/> move down
      </MenuItem> : <div></div>}
      <ManageAuthenticationItem/>
    </div>
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