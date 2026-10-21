import { useMemo } from "react";
import { useTranslate } from 'react-admin';

import DeleteIcon from '@mui/icons-material/Delete';
import VpnKeyIcon from '@mui/icons-material/VpnKey';
import { IconButton, List, ListItem } from '@mui/material';

import { Authentication } from '../../../ows-lib/OwsContext/contrib';
import { useOwsContextBase } from "../../../react-ows-lib/ContextProvider/OwsContextBase";
import { useDialogContextBase } from '../../Dialog/DialogContextBase';
import { useContextMenuBase } from "./ContextMenuBase";
import ContextMenuItem from './ContextMenuItem';


const ManageAuthenticationItem = () => {
  const { owsContext } = useOwsContextBase()
  const { open } = useDialogContextBase()
  const { close } = useContextMenuBase()
  const translate = useTranslate();




  const authHeaders: Authentication[] = Array.isArray(owsContext.authenticationHeaders) 
      ? owsContext.authenticationHeaders
      : []

  const content = useMemo(()=>{
    return (
      <List>
        {authHeaders?.map((authenticationHeader) => {
          return <ListItem key={String(authenticationHeader.id)}
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
     <ContextMenuItem
      onClick={() => {
        open("huuhuu", content, "hio")
        close()
      }}
      icon={<VpnKeyIcon fontSize="small"/>}
      label={translate('LayerTree.ContextMenu.manageAuthenticion')}
    />

  )
}


export default ManageAuthenticationItem