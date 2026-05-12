import { ReactNode } from 'react';

import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import TextField from '@mui/material/TextField';

import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';


export interface AddResourceDialogProps {
    open: boolean
    setOpen: (open: boolean) => void
}


const AddResourceDialog = ({open, setOpen}: AddResourceDialogProps): ReactNode => {
  const { addWMSByUrl } = useOwsContextBase() 

  return (
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        PaperProps={{
          component: 'form',
          onSubmit: (event: React.FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            const formData = new FormData(event.currentTarget);
            const formJson = Object.fromEntries((formData as any).entries());
            const getCapabilitiesUrl = formJson.getCapabilitiesUrl;
            const username = formJson.username;
            const password = formJson.password;

            let headers: Headers | undefined = undefined;

            if (username && password) {
              headers = new Headers();
              const basicAuth = btoa(`${username}:${password}`);
              headers.set('Authorization', `Basic ${basicAuth}`);
            }

            addWMSByUrl(getCapabilitiesUrl, headers)
            setOpen(false)
          },
        }}
      >
        <DialogTitle>Append Web Map Service</DialogTitle>
        <DialogContent>
          <DialogContentText>
            To add a Web Map Service to the current OWS Context, please enter a valid GetCapabilitiesUrl.
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
          <Button onClick={()=>setOpen(false)}>Cancel</Button>
          <Button type="submit" color='primary'>Add</Button>
        </DialogActions>
      </Dialog>
  );
}

export default AddResourceDialog