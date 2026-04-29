import AddIcon from '@mui/icons-material/Add';
import { ButtonOwnProps } from '@mui/material';
import { useState } from "react";
import { Button, useRecordContext } from "react-admin";
import EditDialog, { EditDialogProps } from './EditDialog';

export interface EditDialogButtonProps {
  buttonProps?: ButtonOwnProps
  editDialogProps?: EditDialogProps
}

const EditDialogButton = ({
  buttonProps,
  editDialogProps
}: EditDialogButtonProps) => {

  const [dialogOpen, setDialogOpen] = useState<boolean>(false);
  const record = useRecordContext();

  if (record === undefined) {
    return null
  }
  return (
    <>
      <Button label="Edit" onClick={()=>setDialogOpen(true)} {...buttonProps}>
        <AddIcon />
      </Button>
      <EditDialog id={record?.id} isOpen={dialogOpen} setIsOpen={setDialogOpen} onClose={()=>setDialogOpen(false)}{...editDialogProps} />
    </>
  )
}



export default EditDialogButton;