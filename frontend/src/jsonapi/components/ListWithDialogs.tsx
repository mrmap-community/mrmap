import { Dialog } from "@mui/material";
import { EditButton } from "react-admin";
import { Fragment } from "react/jsx-runtime";
import { DialogBase, useDialogContextBase } from "../../components/Dialog/DialogContextBase";
import EditGuesser from "./EditGuesser";
import ListGuesser from "./ListGuesser";

const WmsShowActions = () => {
    const {open,} = useDialogContextBase()

  return (
    <EditButton
      onClick={()=>open('huhu', '','')}
    />
  )
};

const ListWithDialogsCore = () => {

  const {isOpen, close,} = useDialogContextBase()



  return (
    <Fragment>
        <ListGuesser
          rowActions={<WmsShowActions/>}
        />
        <Dialog 
          open={isOpen}
          onClose={close}
          scroll={'paper'}
          maxWidth={'xl'}
          fullWidth
          aria-labelledby="scroll-dialog-title"
          aria-describedby="scroll-dialog-description"
        >
          <EditGuesser
            redirect={false}
          />
      </Dialog>
    </Fragment>
  )

}


const ListWithDialogs = () => {
  return (
    <Fragment>
      <DialogBase>
        <ListWithDialogsCore/>
      </DialogBase>
    </Fragment>

  )
}

export default ListWithDialogs;