import { useState } from 'react';
import { RecordContextProvider } from 'react-admin';

import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import MenuList from '@mui/material/MenuList';

import EditAuthenticationsDialog from '../../MapViewer/OwsContextGuiActions/EditAuthenticationsDialog';
import ActivateLayerItem from './ActivateLayerItem';
import { useContextMenuBase } from "./ContextMenuBase";
import ManageAuthenticationItem from './ManageAuthenticationItem';
import StyleLegendItem from './StyleLegendItem';
import ZoomToLayerItem from './ZoomToLayerItem';


const MenuItems = ({ onManage }: { onManage: (folder?: string) => void }) => {
  const { node } = useContextMenuBase()

  if (node === undefined ) return null
  
  return (
    <MenuList
    >
      {
        !node?.isRootNode() ? 
          <MenuItem
            onClick={() => {
              console.log("move up:", node );
            }}
          >
            <ArrowUpwardIcon fontSize="small"/> move up
          </MenuItem> : 
          null
      }
      {
        ( !node?.isRootNode() && (node?.children?.length ?? 0 > 0)) ? 
          <MenuItem
            onClick={() => {
              console.log("move down:", node );
            }}
          >
            <ArrowDownwardIcon fontSize="small"/> move down
          </MenuItem> : 
          null
      }
      <StyleLegendItem/>
      <ManageAuthenticationItem onManage={onManage}/>
      <ZoomToLayerItem/>
      <ActivateLayerItem/>
    </MenuList>
  )
}


const ContextMenu = () => {
  const {isOpen, close, mouseX, mouseY, record} = useContextMenuBase()
  
  const [authenticationEditor, setAuthenticationEditor] = useState<{ folder?: string }>();

  // Only render Menu if we have valid coordinates
  if (!isOpen || mouseX === undefined || mouseY === undefined) {
    if (!authenticationEditor) return null
  }
  
  return (
    <RecordContextProvider
      value={record}
    >
      <EditAuthenticationsDialog open={Boolean(authenticationEditor)} folder={authenticationEditor?.folder} setOpen={open => { if (!open) setAuthenticationEditor(undefined); }} />
      <Menu
        open={isOpen}
        onClose={close}
        anchorReference="anchorPosition"
        anchorPosition={{ top: mouseY ?? 0, left: mouseX ?? 0 }}
        anchorOrigin={{
          vertical: "top",
          horizontal: "left",
        }}
        transformOrigin={{
          vertical: "top",
          horizontal: "left",
        }}
      >
        <MenuItems onManage={folder => { setAuthenticationEditor({ folder }); close(); }} />
      </Menu>
    </RecordContextProvider>
  )
}

export default ContextMenu