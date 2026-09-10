import Dialog, { DialogProps } from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import { Fragment } from 'react/jsx-runtime';
import { useDialogContextBase } from './DialogContextBase';

export interface ContextBasedDialog extends Omit<DialogProps,'open'> {

}

const DefaultChildren = () => {
  const {title, content, actions} = useDialogContextBase()

  return (
    <Fragment>
      <DialogTitle id="scroll-dialog-title">
        {title}
      </DialogTitle>

      <DialogContent 
        dividers={true} 
        id="scroll-dialog-description"
      >
        {content}
      </DialogContent>

      <DialogActions style={{ justifyContent: "space-between" }}>
        {actions}
      </DialogActions>
    </Fragment>
  )
}


const ContextBasedDialog = (
{
  children = <DefaultChildren/>,
  ...rest
}: ContextBasedDialog
) => {
  const {isOpen, close, title, actions} = useDialogContextBase()
  
  /* Edit and Form component needed to be outside the Dialog component. 
  Otherwise the scroll feature is broken.
  See: https://github.com/mui/material-ui/issues/13253 
  */
  return (
    <Dialog 
      open={isOpen}
      onClose={close}
      scroll={'paper'}
      maxWidth={'xl'}
      fullWidth
      aria-labelledby="scroll-dialog-title"
      aria-describedby="scroll-dialog-description"
      {...rest}
    >
      <DialogTitle id="scroll-dialog-title">
        {title}
      </DialogTitle>

      <DialogContent 
        dividers={true} 
        id="scroll-dialog-description"
      >
        {children}
      </DialogContent>

      <DialogActions style={{ justifyContent: "space-between" }}>
        {actions}
      </DialogActions>
    </Dialog>
  )
}

export default ContextBasedDialog