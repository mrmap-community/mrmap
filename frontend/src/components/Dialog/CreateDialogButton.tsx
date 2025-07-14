import AddIcon from '@mui/icons-material/Add';
import { ButtonOwnProps } from '@mui/material';
import { useState } from "react";
import { Button } from "react-admin";
import CreateDialog, { CreateDialogProps } from "./CreateDialog";

export interface CreateDialogButtonProps extends CreateDialogProps {
  buttonProps?: ButtonOwnProps
}

const CreateDialogButton = ({
  buttonProps,
  ...props
}: CreateDialogButtonProps) => {

  const [dialogOpen, setDialogOpen] = useState<boolean>(false);

  return (
    <>
      <Button label="Create" onClick={()=>setDialogOpen(true)} {...buttonProps}>
        <AddIcon />
      </Button>
      <CreateDialog isOpen={dialogOpen} setIsOpen={setDialogOpen} {...props} />
    </>
  )
}



export default CreateDialogButton;