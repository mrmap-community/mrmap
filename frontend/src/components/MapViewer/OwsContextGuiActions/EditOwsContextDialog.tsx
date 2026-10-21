import { ReactNode, useEffect, useState } from 'react';

import { Editor } from '@monaco-editor/react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import Typography from '@mui/material/Typography';

import { OwsContextIssue } from '../../../ows-lib/OwsContext/validation';
import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';

export interface EditOwsContextDialogProps {
    open: boolean
    setOpen: (open: boolean) => void
}


const issueTexts = (issues: OwsContextIssue[], severity: OwsContextIssue['severity']): string[] => {
  return issues
    .filter(issue => issue.severity === severity)
    .map(issue => `${issue.path}: ${issue.message}`)
}

const EditOwsContextDialog = ({open, setOpen}: EditOwsContextDialogProps): ReactNode => {
  const { owsContext, updateOwsContext } = useOwsContextBase() 
  const [text, setText] = useState(
    JSON.stringify(owsContext, null, 2)
  );
  const [errors, setErrors] = useState<string[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);

  const handleSave = () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (parseError) {
      setErrors([`Invalid JSON: ${parseError instanceof Error ? parseError.message : String(parseError)}`]);
      setWarnings([]);
      return;
    }

    // the provider validates and normalizes the document, the very same way an url import is handled
    const result = updateOwsContext(parsed);
    setErrors(issueTexts(result.issues, 'error'));
    setWarnings(issueTexts(result.issues, 'warning'));

    // only an accepted document closes the dialog, otherwise the previous context stays in use
    if (!result.hasErrors) {
      setOpen(false);
    }
  }

  useEffect(() => {
    setText(JSON.stringify(owsContext, null, 2))
  }, [owsContext])

  useEffect(() => {
    if (open) {
      setErrors([])
      setWarnings([])
    }
  }, [open])

  return (
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        slotProps={{paper: {
          component: 'form',
          onSubmit: (e: React.FormEvent<HTMLDivElement>) => {
            e.preventDefault()
            handleSave()
          }
        }}}
        maxWidth="xl"
        fullWidth
      >
        <DialogTitle>Edit</DialogTitle>
        <DialogContent>
          <DialogContentText>
            To edit the current OWS Context, please enter a valid OWS Context document.
          </DialogContentText>
          {errors.length > 0 && (
            <Typography variant="body2" component="p" sx={{ mt: 1 }}>
              The document was not applied, the previous OWS Context is still in use:
            </Typography>
          )}
          {errors.map(error => (
            <Alert key={error} severity="error" variant="outlined" sx={{ mb: 0.5 }} data-testid="ows-context-error">
              {error}
            </Alert>
          ))}
          {warnings.map(warning => (
            <Alert key={warning} severity="warning" variant="outlined" sx={{ mb: 0.5 }} data-testid="ows-context-warning">
              {warning}
            </Alert>
          ))}
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
