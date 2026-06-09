import { ReactNode, useMemo } from 'react';

import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';

import { TextField } from '@mui/material';
import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';

export interface EditAuthenticationsDialogProps {
    open: boolean
    setOpen: (open: boolean) => void
}


const EditAuthenticationsDialog = ({open, setOpen}: EditAuthenticationsDialogProps): ReactNode => {
  const { owsContext, updateOwsContext } = useOwsContextBase() 
  const authentications = useMemo(()=> owsContext.authentications ?? [], [owsContext])
  

  return (
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        slotProps={{paper: {
          component: 'form',
          onSubmit: (e) => {
            e.preventDefault()
            
          }
        }}}
        maxWidth="xl"
        fullWidth
      >
        <DialogTitle>Edit</DialogTitle>
        <DialogContent
          
        >
          <DialogContentText>
            To edit the current OWS Context, please enter a valid OWS Context document.
          </DialogContentText>
          <TextField
            autoFocus
            required
            margin="dense"
            id="getCapabilitiesUrl"
            name="getCapabilitiesUrl"
            label="Get Capabilities Url"
            type="url"
            fullWidth
            variant="standard"
          />
          <TextField
            margin="dense"
            id="username"
            name="username"
            label="Username (optional)"
            fullWidth
            variant="standard"
          />
          <TextField
            margin="dense"
            id="password"
            name="password"
            label="Password (optional)"
            type="password"
            fullWidth
            variant="standard"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button type="submit" color='primary'>Save</Button>
        </DialogActions>
      </Dialog>
  );
}

export default EditAuthenticationsDialog;