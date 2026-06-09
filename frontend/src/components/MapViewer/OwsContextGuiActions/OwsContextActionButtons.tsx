import { useState } from 'react';

import AddIcon from '@mui/icons-material/Add';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import EditIcon from '@mui/icons-material/Edit';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import Fab from '@mui/material/Fab';
import Tooltip from '@mui/material/Tooltip';

import VpnKeyIcon from '@mui/icons-material/VpnKey';
import { Loading } from 'react-admin';
import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';
import AddResourceDialog from './AddResourceDialog';
import EditAuthenticationsDialog from './EditAuthenticationsDialog';
import EditOwsContextDialog from './EditOwsContextDialog';
import InitialFromOwsContextDialog from './InitialFromOwsContextDialog';


export const OwsContextActionButtons = () => {
    const [openAddResourceDialog, setOpenAddResourceDialog] = useState(false)
    const handleOpenAddResourceDialog = () => setOpenAddResourceDialog(true)
  
    const [openInitialDialog, setOpenInitialDialog] = useState(false)
    const handleOpenInitialDialog = () => setOpenInitialDialog(true)

    const [openOwsContextEditor, setOpenOwsContextEditor] = useState(false)
    const handleOpenOwsContextEditor = () => setOpenOwsContextEditor(true)

    const [openAuthenticationsEditor, setOpenAuthenticationsEditor] = useState(false)
    const handleOpenAuthenticationsEditor = () => setOpenAuthenticationsEditor(true)


    const { isLoading, currentRequest } = useOwsContextBase()
  
    return (
    <>
        <Box  sx={{ '& > :not(style)': { m: 1 } }}>
            <Tooltip title="Initial">
                <Fab color="primary" aria-label="add" size="small" onClick={handleOpenInitialDialog} disabled={isLoading}>
                    <AutoFixHighIcon />
                </Fab>
            </Tooltip>
            <InitialFromOwsContextDialog open={openInitialDialog} setOpen={setOpenInitialDialog}/>
      
            <Tooltip title="Add Resource">
                <Fab color="primary" aria-label="add" size="small" onClick={handleOpenAddResourceDialog} disabled={isLoading}>
                    <AddIcon />
                </Fab>
            </Tooltip>
            <AddResourceDialog open={openAddResourceDialog} setOpen={setOpenAddResourceDialog}/>
      
            <Tooltip title="Edit OWS Context">
                <Fab color="secondary" aria-label="edit" size="small" disabled={isLoading} onClick={handleOpenOwsContextEditor}>
                    <EditIcon />
                </Fab>
            </Tooltip>
            <EditOwsContextDialog open={openOwsContextEditor} setOpen={setOpenOwsContextEditor}/>

            <Tooltip title="Manage Authentications">
                <Fab color="secondary" aria-label="authentications" size="small" disabled={isLoading} onClick={handleOpenAuthenticationsEditor}>
                    <VpnKeyIcon />
                </Fab>
            </Tooltip>
            <EditAuthenticationsDialog open={openAuthenticationsEditor} setOpen={setOpenAuthenticationsEditor}/>
            {isLoading && <Loading loadingSecondary={currentRequest?.url} />}
            <Divider/>
        </Box>
        
       
        
    </>
    )
}