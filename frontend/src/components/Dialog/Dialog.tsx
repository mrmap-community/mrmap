import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import { useDialogContextBase } from './DialogContextBase';



const ContextBasedDialog = () => {
  const {isOpen, close, title, content, actions} = useDialogContextBase()
  
  /* Edit and Form component needed to be outside the Dialog component. 
  Otherwise the scroll feature is broken.
  See: https://github.com/mui/material-ui/issues/13253 
  */
  return (
    <Dialog 
      open={isOpen}
      onClose={close}
      scroll={'paper'}
      aria-labelledby="scroll-dialog-title"
      aria-describedby="scroll-dialog-description"
    >
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
    
    </Dialog>
  )
}

export default ContextBasedDialog