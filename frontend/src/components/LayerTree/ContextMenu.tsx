import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import { useContextMenuBase } from "./ContextMenuBase";
const ContextMenu = () => {
  const {isOpen, close, itemId, mouseX, mouseY} = useContextMenuBase()
  
  console.log("render context menu", {isOpen, itemId, mouseX, mouseY})
  
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
        slotProps={{
          paper: {
            sx: {},
          },
        }}
      >
        <MenuItem
          onClick={() => {
            console.log("Rename:", itemId );
            
          }}
        >
          Rename
        </MenuItem>

        <MenuItem
          onClick={() => {
            console.log("Duplicate:", itemId);
          }}
        >
          Duplicate
        </MenuItem>

        <MenuItem
          onClick={() => {
            console.log("Delete:", itemId);
          }}
        >
          Delete
        </MenuItem>
      </Menu>
  )
}

export default ContextMenu