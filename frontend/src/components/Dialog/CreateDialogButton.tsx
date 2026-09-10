import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import { ButtonOwnProps, IconButton, Stack, Typography } from '@mui/material';
import { Fragment, useCallback } from "react";
import { Button, SaveButton, useListContext, useNotify, useResourceContext, useResourceDefinition, useTranslate } from "react-admin";
import CreateGuesser, { CreateGuesserProps } from '../../jsonapi/components/CreateGuesser';
import ContextBasedDialog from './Dialog';
import { DialogBase, useDialogContextBase } from './DialogContextBase';


export interface CreateDialogButtonProps {
  buttonProps?: ButtonOwnProps
  guesserProps?: CreateGuesserProps
}


const DefaultTitle = () => {
  const translate = useTranslate();
  const {close} = useDialogContextBase();
  const {name} = useResourceDefinition()
  return (
    <Stack 
      direction="row"
      sx={{
        justifyContent: "space-between"
      }}
    >
      <Typography variant='h5'>{translate('ra.action.create')} {name}</Typography>
      <IconButton onClick={close}>
        <CloseIcon />
      </IconButton>
    </Stack>
  )
}

const DefaultActions = (
) => {
  const translate = useTranslate();
  const { refetch } = useListContext()
  const resource = useResourceContext();
  const notify = useNotify();
  const {close} = useDialogContextBase();
  const onSuccess = useCallback(()=>{
      refetch()
      close()
      
      notify(`resources.${resource}.notifications.created`, {
        type: 'success',
        messageArgs: {
            smart_count: 1,
            _: translate('ra.notification.created', {
                smart_count: 1,
            })
        },
        undoable: false,
    });
    },[resource])
  
  return (
    <Fragment>
      <SaveButton mutationOptions={{onSuccess: onSuccess}} type='button' alwaysEnable/>
    </Fragment>
  )
}

const CreateDialogButtonCore = ({
  buttonProps,
  guesserProps

}: CreateDialogButtonProps) => {
  const {open} = useDialogContextBase();
  console.log(guesserProps)
  return (
    <Fragment>
      <Button label="ra.action.create" onClick={() => open(<DefaultTitle/>, null, <DefaultActions/>)} {...buttonProps}>
        <AddIcon/>
      </Button>
      <CreateGuesser
        redirect={false}
        sx={{
          // otherwise the EditGuesser div will create some spacing behind the edit button...
          display: 'none !important'
        }}
        simpleFormProps={{
          component: ContextBasedDialog,
          children: null,
          toolbar: false,
        }}
        referenceInputs={guesserProps?.referenceInputs}
        {...guesserProps}
      >
      </CreateGuesser>
    </Fragment>
  )
}


const CreateDialogButton = ({
  ...rest
}: CreateDialogButtonProps) => {

  const {hasCreate} = useResourceDefinition();

  if (!hasCreate) {
    return null
  }

  return (
    <DialogBase>
      <CreateDialogButtonCore {...rest}/>
    </DialogBase>
  )
}



export default CreateDialogButton;