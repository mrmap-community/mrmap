import { ReactNode, useEffect, useState } from 'react';

import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';

import { Editor } from '@monaco-editor/react';
import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';

export interface EditOwsContextDialogProps {
    open: boolean
    setOpen: (open: boolean) => void
}


const EditOwsContextDialog = ({open, setOpen}: EditOwsContextDialogProps): ReactNode => {
  const { owsContext, updateOwsContext } = useOwsContextBase() 
  const [text, setText] = useState(
    JSON.stringify(owsContext, null, 2)
  );
  const [error, setError] = useState("");

  const handleSave = () => {
    console.log("Saving OWS Context:", text);
    try {
      const parsed = JSON.parse(text);
      
      // TODO: validate that it is a valid OWSContext/GeoJSON

      updateOwsContext(parsed);

      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      if (!error) {
        setOpen(false);
      }
  };
}

  useEffect(() => {
    setText(JSON.stringify(owsContext, null, 2))
  }, [owsContext])

  return (
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        slotProps={{paper: {
          component: 'form',
          onSubmit: (e) => {
            e.preventDefault()
            handleSave()
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
          <Editor
            height="80vh"
            defaultLanguage="json"
            value={text}
            onChange={(value) => setText(value || "")}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button type="submit" color='primary'>Save</Button>
        </DialogActions>
      </Dialog>
  );
}

export default EditOwsContextDialog;