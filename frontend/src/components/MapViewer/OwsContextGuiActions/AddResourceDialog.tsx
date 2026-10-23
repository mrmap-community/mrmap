import { useState, type ReactNode } from 'react';
import { useTranslate } from 'react-admin';

import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';

import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';


export interface AddResourceDialogProps {
    open: boolean
    setOpen: (open: boolean) => void
}


const AddResourceDialog = ({open, setOpen}: AddResourceDialogProps): ReactNode => {
  const { addWMSByUrl, addWFSByUrl } = useOwsContextBase()
  const [protocol, setProtocol] = useState('WMS');
  const translate = useTranslate();

  return (
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        slotProps={{ paper: {
          component: 'form',
          onSubmit: (event: React.FormEvent<HTMLDivElement>) => {
            event.preventDefault();
            const formData = new FormData(event.currentTarget as unknown as HTMLFormElement);
            const formJson = Object.fromEntries(formData.entries());
            const getCapabilitiesUrl = String(formJson.getCapabilitiesUrl ?? "");
            const username = formJson.username;
            const password = formJson.password;

            let headers: Headers | undefined = undefined;

            if (username && password) {
              headers = new Headers();
              const basicAuth = btoa(`${username}:${password}`);
              headers.set('Authorization', `Basic ${basicAuth}`);
            }

            const addService = protocol === 'WFS' ? addWFSByUrl : addWMSByUrl;
            addService(getCapabilitiesUrl, headers)
            setOpen(false)
          },
        } }}
      >
        <DialogTitle>{translate('viewerAdd.title')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {translate('viewerAdd.description')}
          </DialogContentText>
          <TextField
            select
            fullWidth
            margin="dense"
            label={translate('viewerAdd.protocol')}
            value={protocol}
            onChange={(event) => setProtocol(event.target.value)}
          >
            <MenuItem value="WMS">WMS</MenuItem>
            <MenuItem value="WFS">WFS</MenuItem>
          </TextField>
          <TextField
            autoFocus
            required
            margin="dense"
            id="getCapabilitiesUrl"
            name="getCapabilitiesUrl"
            label={translate('viewerAdd.url')}
            type="url"
            fullWidth
            variant="standard"
          />
          <TextField
            margin="dense"
            id="username"
            name="username"
            label={translate('viewerAdd.username')}
            fullWidth
            variant="standard"
          />
          <TextField
            margin="dense"
            id="password"
            name="password"
            label={translate('viewerAdd.password')}
            type="password"
            fullWidth
            variant="standard"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={()=>setOpen(false)}>{translate('ra.action.cancel')}</Button>
          <Button type="submit" color='primary'>{translate('ra.action.add')}</Button>
        </DialogActions>
      </Dialog>
  );
}

export default AddResourceDialog
