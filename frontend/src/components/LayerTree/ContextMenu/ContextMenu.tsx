import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import MenuList from '@mui/material/MenuList';
import { RecordContextProvider } from 'react-admin';
import ActivateLayerItem from './ActivateLayerItem';
import { useContextMenuBase } from "./ContextMenuBase";
import ManageAuthenticationItem from './ManageAuthenticationItem';
import ZoomToLayerItem from './ZoomToLayerItem';


const MenuItems = () => {
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
      <ManageAuthenticationItem/>
      <ZoomToLayerItem/>
      <ActivateLayerItem/>
    </MenuList>
  )
}


const ContextMenu = () => {
  const {isOpen, close, mouseX, mouseY, record} = useContextMenuBase()
  
  // Only render Menu if we have valid coordinates
  if (!isOpen || mouseX === undefined || mouseY === undefined) {
    return null
  }
  
  return (
    <RecordContextProvider
      value={record}
    >
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
    </RecordContextProvider>
  )
}

export default ContextMenu