import { Fragment, ReactNode } from 'react';

import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';

import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';
import ContextBasedDialog from '../../Dialog/Dialog';
import DialogHeader from '../../Dialog/DialogHeader';


export interface InitialFromOwsContextDialogProps {
    open: boolean
    setOpen: (open: boolean) => void
}


const InitialFromOwsContextDialog = ({open, setOpen}: InitialFromOwsContextDialogProps): ReactNode => {
  const { initialFromOwsContext } = useOwsContextBase() 

  const dismiss = () => setOpen(false)

  return (
      <ContextBasedDialog
        open={open}
        onClose={dismiss}
        contentDividers={false}
        title={<DialogHeader onClose={dismiss}>Initial</DialogHeader>}
        description="To add a Web Map Service to the current OWS Context, please enter a valid GetCapabilitiesUrl."
        actions={<Fragment>
          <Button onClick={dismiss}>Cancel</Button>
          <Button type="submit" color='primary'>Add</Button>
        </Fragment>}
        actionsAlign="flex-end"
        slotProps={{ paper: {
          component: 'form',
          onSubmit: (event: React.FormEvent<HTMLDivElement>) => {
            event.preventDefault();
            const formData = new FormData(event.currentTarget as unknown as HTMLFormElement);
            const formJson = Object.fromEntries(formData.entries());
            const getCapabilitiesUrl = String(formJson.getCapabilitiesUrl ?? "");
            initialFromOwsContext(getCapabilitiesUrl)
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
            label="Get Capabilities Url"
            type="url"
            fullWidth
            variant="standard"
          />
        </Fragment>
      </ContextBasedDialog>
  );
}

export default InitialFromOwsContextDialog