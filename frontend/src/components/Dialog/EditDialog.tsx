import CloseIcon from '@mui/icons-material/Close';
import { Box, IconButton } from '@mui/material';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import { createElement, useCallback, useMemo } from 'react';
import { DeleteButton, Edit, EditProps, Form, RecordRepresentation, SaveButton, useNotify, useTranslate } from 'react-admin';
import { useFieldsForOperation } from '../../jsonapi/hooks/useFieldsForOperation';

export interface EditDialogProps extends EditProps{
  isOpen?: boolean
  onClose?: () => void
}

const EditDialog = (
 {
  id,
  resource,
  isOpen=false,
  onClose,
  ...rest
 }: EditDialogProps
) => {
  
  const translate = useTranslate();
  const notify = useNotify();

  const fieldDefinitions = useFieldsForOperation(`partial_update_${resource}`)
  const fields = useMemo(()=> fieldDefinitions.map(def => createElement(def.component, def.props)),[fieldDefinitions])

  const onEditSuccess = useCallback(()=>{
    notify(`resources.${resource}.notifications.updated`, {
      type: 'info',
      messageArgs: {
          smart_count: 1,
          _: translate('ra.notification.updated', {
              smart_count: 1,
          })
      },
      undoable: false,
  });
  },[resource])

  const onDeleteSuccess = useCallback(()=>{
    notify(`resources.${resource}.notifications.deleted`, {
      type: 'info',
      messageArgs: {
          smart_count: 1,
          _: translate('ra.notification.deleted', {
              smart_count: 1,
          })
      },
      undoable: false,
  });
  },[resource])

  /* Edit and Form component needed to be outside the Dialog component. 
  Otherwise the scroll feature is broken.
  See: https://github.com/mui/material-ui/issues/13253 
  */
  return (
      <Edit
        mutationMode='pessimistic'
        resource={resource}
        id={id}
        redirect={false}
        mutationOptions={{onSuccess: onEditSuccess}}
        sx={{
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}
        {...rest}
      >
        <Form>
          <Dialog 
            open={isOpen}
            onClose={onClose}
            scroll={'paper'}
            aria-labelledby="scroll-dialog-title"
            aria-describedby="scroll-dialog-description"
          >
            <DialogTitle id="scroll-dialog-title">
              <Box display="flex" alignItems="center">
                <Box flexGrow={1} >
                  <RecordRepresentation/>
                </Box>
                <Box>
                  <IconButton onClick={onClose}>
                    <CloseIcon />
                  </IconButton>
                </Box>
              </Box>
              
            </DialogTitle>

            <DialogContent 
              dividers={true} 
              id="scroll-dialog-description"
            >
              {fields}
            </DialogContent>

            <DialogActions style={{ justifyContent: "space-between" }}>
                  <SaveButton mutationOptions={{onSuccess: onEditSuccess}} type='button'/>
                  <DeleteButton redirect={false} mutationOptions={{onSuccess: onDeleteSuccess}}/>
            </DialogActions>
          
          </Dialog>
        </Form>
      </Edit>
  )
}

export default EditDialog