import { Fragment, ReactNode } from 'react';
import { useTranslate } from 'react-admin';

import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';

import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';
import ContextBasedDialog from '../../Dialog/Dialog';
import DialogHeader from '../../Dialog/DialogHeader';


export interface AddResourceDialogProps {
    open: boolean
    setOpen: (open: boolean) => void
}


const AddResourceDialog = ({open, setOpen}: AddResourceDialogProps): ReactNode => {
  const { addWMSByUrl, addWFSByUrl, addServiceByUrl } = useOwsContextBase()
  const translate = useTranslate()
  const t = (key: string) => translate(`addResource.${key}`)

  const dismiss = () => setOpen(false)

  return (
      <ContextBasedDialog
        open={open}
        onClose={dismiss}
        contentDividers={false}
        title={<DialogHeader onClose={dismiss}>{t('title')}</DialogHeader>}
        description={t('description')}
        actions={<Fragment>
          <Button onClick={dismiss}>{translate('ra.action.cancel')}</Button>
          <Button type="submit" color='primary'>{translate('ra.action.add')}</Button>
        </Fragment>}
        actionsAlign="flex-end"
        slotProps={{ paper: {
          component: 'form',
          onSubmit: (event: React.FormEvent<HTMLDivElement>) => {
            event.preventDefault();
            const formData = new FormData(event.currentTarget as unknown as HTMLFormElement);
            const formJson = Object.fromEntries(formData.entries());
            const getCapabilitiesUrl = String(formJson.getCapabilitiesUrl ?? "");
            const protocol = String(formJson.protocol ?? "");
            const username = formJson.username;
            const password = formJson.password;

            let headers: Headers | undefined = undefined;

            if (username && password) {
              headers = new Headers();
              const basicAuth = btoa(`${username}:${password}`);
              headers.set('Authorization', `Basic ${basicAuth}`);
            }

            // the protocols the document cannot decide for itself are fixed here; the async
            // loading, parsing and error reporting of the context answer the rest visibly
            if (protocol === 'WMS')
              addWMSByUrl(getCapabilitiesUrl, headers)
            else if (protocol === 'WFS')
              addWFSByUrl(getCapabilitiesUrl, headers)
            else
              addServiceByUrl(getCapabilitiesUrl, headers)
            setOpen(false)
          },
        } }}
      >
        <Fragment>
          <TextField
            autoFocus
            required
            margin="dense"
            id="getCapabilitiesUrl"
            name="getCapabilitiesUrl"
            label={t('url')}
            type="url"
            fullWidth
            variant="standard"
          />
          <TextField
            margin="dense"
            select
            id="protocol"
            name="protocol"
            label={t('protocol')}
            defaultValue=""
            fullWidth
            variant="standard"
          >
            <MenuItem value="">{t('protocolAuto')}</MenuItem>
            <MenuItem value="WMS">WMS</MenuItem>
            <MenuItem value="WFS">WFS</MenuItem>
          </TextField>
          <TextField
            margin="dense"
            id="username"
            name="username"
            label={t('username')}
            fullWidth
            variant="standard"
          />
          <TextField
            margin="dense"
            id="password"
            name="password"
            label={t('password')}
            type="password"
            fullWidth
            variant="standard"
          />
        </Fragment>
      </ContextBasedDialog>
  );
}

export default AddResourceDialog