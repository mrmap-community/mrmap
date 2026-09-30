import CloseIcon from '@mui/icons-material/Close';
import EditIcon from '@mui/icons-material/Edit';
import { ButtonOwnProps, IconButton, Stack, Typography } from '@mui/material';
import { Fragment, useCallback } from "react";
import { Button, DeleteButton, EditProps, RecordRepresentation, SaveButton, useListContext, useNotify, useRecordContext, useResourceContext, useResourceDefinition, useTranslate } from "react-admin";
import EditGuesser, { EditGuesserProps } from '../../jsonapi/components/EditGuesser';
import { FieldDefinition } from '../../jsonapi/utils';
import ContextBasedDialog from './Dialog';
import { DialogBase, useDialogContextBase } from './DialogContextBase';


export interface EditDialogProps extends Partial<EditProps>{
  isOpen?: boolean
  onClose?: () => void
  updateFieldDefinitions?: FieldDefinition[];
}

export interface EditDialogButtonProps {
  buttonProps?: ButtonOwnProps
  guesserProps?: EditGuesserProps
}


const DefaultTitle = () => {
  const translate = useTranslate();
  const {close} = useDialogContextBase();

  return (
    <Stack 
      direction="row"
      sx={{
        justifyContent: "space-between"
      }}
    >
      <Typography variant='h5'>{translate('ra.action.edit')} <RecordRepresentation /></Typography>
      <IconButton onClick={close}>
        <CloseIcon />
      </IconButton>
    </Stack>
  )
}

const DefaultActions = () => {
  const translate = useTranslate();
  const { refetch } = useListContext()
  const resource = useResourceContext();
  const notify = useNotify();
  const {close} = useDialogContextBase();
  const onEditSuccess = useCallback(()=>{
      refetch()
      close()
      
      notify(`resources.${resource}.notifications.updated`, {
        type: 'success',
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
      refetch()
      close()
      
      notify(`resources.${resource}.notifications.deleted`, {
        type: 'success',
        messageArgs: {
            smart_count: 1,
            _: translate('ra.notification.deleted', {
                smart_count: 1,
            })
        },
        undoable: false,
    });
    },[resource])
  return (
    <Fragment>
      <SaveButton mutationOptions={{onSuccess: onEditSuccess}} type='button' alwaysEnable/>
      <DeleteButton redirect={false} mutationOptions={{onSuccess: onDeleteSuccess}}/>
    </Fragment>
  )
}

const EditDialogButtonCore = ({
  buttonProps,
  guesserProps
}: EditDialogButtonProps) => {
const record = useRecordContext();
const {open} = useDialogContextBase();

  return (
    <Fragment>
      <Button label="Edit" onClick={() => open(<DefaultTitle/>, null, <DefaultActions/>)} {...buttonProps}>
        <EditIcon />
      </Button>
      <EditGuesser
        id={record?.id}
        redirect={false}
        sx={{
          // otherwise the EditGuesser div will create some spacing behind the edit button...
          display: 'none !important'
        }}
        simpleFormProps={{
          component: ContextBasedDialog,
          children: null,
          toolbar: false
          
        }}
        
        {...guesserProps}
      >
      </EditGuesser>
    </Fragment>
  )
}


const EditDialogButton = ({
  ...rest
}: EditDialogButtonProps) => {

  const record = useRecordContext();
  const {hasEdit} = useResourceDefinition();

  if (!hasEdit || record === undefined) {
    return null
  }

  return (
    <DialogBase>
      <EditDialogButtonCore {...rest}/>
    </DialogBase>
  )
}



export default EditDialogButton;