import AddIcon from '@mui/icons-material/Add';
import { ButtonOwnProps } from '@mui/material';
import { useState } from "react";
import { Button } from "react-admin";
import CreateDialog, { CreateDialogProps } from "./CreateDialog";

export interface CreateDialogButtonProps {
  buttonProps?: ButtonOwnProps
  createDialogProps?: CreateDialogProps
}

const CreateDialogButton = ({
  buttonProps,
  createDialogProps
}: CreateDialogButtonProps) => {

  const [dialogOpen, setDialogOpen] = useState<boolean>(false);

  return (
    <div>
      <Button label="Create" onClick={()=>setDialogOpen(true)} {...buttonProps}>
        <AddIcon />
      </Button>
      <CreateDialog isOpen={dialogOpen} setIsOpen={setDialogOpen} {...createDialogProps} />
    </div>
  )
}



export default CreateDialogButton;