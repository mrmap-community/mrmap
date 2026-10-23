import { MouseEventHandler, ReactElement } from "react";

import MenuItem from "@mui/material/MenuItem";


export interface ContextMenuItemProps {
  onClick?: MouseEventHandler
  icon?: ReactElement
  label?: string
  disabled?: boolean
}


const ContextMenuItem = ({
  onClick,
  icon,
  label,
  disabled = false
}: ContextMenuItemProps) => {
  return (
    <MenuItem
      onClick={onClick}
      disabled={disabled}
    >
      {icon}
      {label}
    </MenuItem>
  )
}


export default ContextMenuItem