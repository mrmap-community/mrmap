import CloseIcon from '@mui/icons-material/Close';
import { Box, IconButton } from '@mui/material';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import { createElement, useCallback, useMemo } from 'react';
import { Create, CreateProps, Form, RaRecord, SaveButton, useNotify, useResourceContext, useTranslate } from 'react-admin';
import { useFieldsForOperation } from '../../jsonapi/hooks/useFieldsForOperation';
import { FieldDefinition } from '../../jsonapi/utils';

export interface CreateDialogProps extends Partial<CreateProps>{
  isOpen?: boolean
  setIsOpen?: (open: boolean) => void
  onClose?: () => void
  onCreate?: (data: any) => void
  onCancel?: () => void
  updateFieldDefinitions?: FieldDefinition[];

}

const CreateDialog = (
 {
  isOpen=false,
  setIsOpen,
  onClose,
  onCreate,
  onCancel,
  updateFieldDefinitions,
  defaultValue,
  ...rest
 }: CreateDialogProps
) => {
  const translate = useTranslate();
  const notify = useNotify();
  const resource = useResourceContext({resource: rest?.resource})

  const fieldDefinitions = useFieldsForOperation(`create_${resource}`)
  const fields = useMemo(
    ()=> 
      fieldDefinitions.filter(fieldDefinition => !fieldDefinition.props.disabled ).map(
        (fieldDefinition, index) => {

          const update = updateFieldDefinitions?.find(def => def.props.source === fieldDefinition.props.source)
        
          return createElement(
            update?.component || fieldDefinition.component, 
            {
              ...fieldDefinition.props, 
              key:`create-${resource}-${index}`,
              ...update?.props
            }
          )
        })
    ,[fieldDefinitions]
  )

  const onCreateSuccess = useCallback((data: RaRecord)=>{
    notify(`resources.${resource}.notifications.created`, {
      type: 'info',
      messageArgs: {
          smart_count: 1,
          _: translate('ra.notification.created', {
              smart_count: 1,
          })
      },
      undoable: false,
    });
    onCreate && onCreate(data)
    setIsOpen && setIsOpen(false)
  },[resource])

  /* Create and Form component needed to be outside the Dialog component. 
  Otherwise the scroll feature is broken.
  See: https://github.com/mui/material-ui/issues/13253 
  */
  return (
      <Create
        resource={resource}
        redirect={false}
        mutationOptions={{onSuccess: onCreateSuccess}}
        sx={{
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}
        
        {...rest}
      >
        <Form
          defaultValues={defaultValue as any}
            
        >
          <Dialog 
            open={isOpen}
            onClose={() => {onClose && onClose();  setIsOpen && setIsOpen(false); onCancel && onCancel()}}
            scroll={'paper'}
            aria-labelledby="scroll-dialog-title"
            aria-describedby="scroll-dialog-description"
          >
            <DialogTitle id="scroll-dialog-title">
              <Box display="flex" alignItems="center">
                <Box flexGrow={1} >
                  Create new {resource}
                </Box>
                <Box>
                  <IconButton onClick={() => {onClose && onClose(); setIsOpen && setIsOpen(false);onCancel &&  onCancel()}}>
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
                  <SaveButton mutationOptions={{onSuccess: onCreateSuccess}} type='button'/>
            </DialogActions>
          
          </Dialog>
        </Form>
      </Create>
  )
}

export default CreateDialog