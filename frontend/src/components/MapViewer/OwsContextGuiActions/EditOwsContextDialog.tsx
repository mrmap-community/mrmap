import { ReactNode, useEffect, useState } from 'react';
import { Fragment } from 'react';
import { useTranslate } from 'react-admin';

import { Editor } from '@monaco-editor/react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';

import { serializeOwsContext } from '../../../ows-lib/OwsContext/authentication';
import { OwsContextIssue } from '../../../ows-lib/OwsContext/validation';
import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';
import ContextBasedDialog from '../../Dialog/Dialog';
import DialogHeader from '../../Dialog/DialogHeader';

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
  const translate = useTranslate();
  const { owsContext, updateOwsContext } = useOwsContextBase() 
  const [text, setText] = useState(
    serializeOwsContext(owsContext)
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
    // Keep session secrets when an unchanged redacted credential is edited locally.
    // Imported documents still go through the provider without restoring any secrets.
    if (parsed && typeof parsed === 'object' && 'authenticationHeaders' in parsed) {
      const document = parsed as { authenticationHeaders?: typeof owsContext.authenticationHeaders };
      if (Array.isArray(document.authenticationHeaders)) document.authenticationHeaders = document.authenticationHeaders.map(auth => {
        if (!auth || typeof auth !== 'object') return auth;
        const current = owsContext.authenticationHeaders?.find(entry => entry.id === auth.id && entry.name === auth.name && entry.origin === auth.origin);
        return current && auth.value === '' ? { ...auth, value: current.value } : auth;
      });
    }
    const result = updateOwsContext(parsed);
    setErrors(issueTexts(result.issues, 'error'));
    setWarnings(issueTexts(result.issues, 'warning'));

    // only an accepted document closes the dialog, otherwise the previous context stays in use
    if (!result.hasErrors) {
      setOpen(false);
    }
  }

  useEffect(() => {
    setText(serializeOwsContext(owsContext))
  }, [owsContext])

  useEffect(() => {
    if (open) {
      setErrors([])
      setWarnings([])
    }
  }, [open])

  const dismiss = () => setOpen(false)

  return (
      <ContextBasedDialog
        open={open}
        onClose={dismiss}
        contentDividers={false}
        maxWidth="xl"
        fullWidth
        title={<DialogHeader onClose={dismiss}>Edit</DialogHeader>}
        description="To edit the current OWS Context, please enter a valid OWS Context document."
        actions={<Fragment>
          <Button onClick={dismiss}>Cancel</Button>
          <Button type="submit" color='primary'>Save</Button>
        </Fragment>}
        actionsAlign="flex-end"
        slotProps={{paper: {
          component: 'form',
          onSubmit: (e: React.FormEvent<HTMLDivElement>) => {
            e.preventDefault()
            handleSave()
          }
        }}}
      >
        <Fragment>
          <Alert severity="info">{translate('viewerAuth.redacted')}</Alert>
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
        </Fragment>
      </ContextBasedDialog>
  );
}

export default EditOwsContextDialog;
