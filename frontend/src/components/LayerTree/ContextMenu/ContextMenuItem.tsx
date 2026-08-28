import MenuItem from "@mui/material/MenuItem";
import { MouseEventHandler, ReactElement } from "react";


export interface ContextMenuItemProps {
  onClick?: MouseEventHandler
  icon?: ReactElement
  label?: string
}


const ContextMenuItem = ({
  onClick,
  icon,
  label
}: ContextMenuItemProps) => {
  return (
    <MenuItem
      onClick={onClick}
    >
      {icon}
      {label}
    </MenuItem>
  )
}


export default ContextMenuItem