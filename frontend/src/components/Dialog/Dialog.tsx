import Dialog, { DialogProps } from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import { useId } from "react";
import { useDialogContextBase } from "./DialogContextBase";

export interface ContextBasedDialogProps extends Omit<DialogProps, "open"> {}

const ContextBasedDialog = ({ children, ...rest }: ContextBasedDialogProps) => {
  const { isOpen, close, title, content, actions } = useDialogContextBase();
  const id = useId();
  const titleId = `${id}-title`;
  const contentId = `${id}-content`;

  /* Edit and Form component needed to be outside the Dialog component. 
  Otherwise the scroll feature is broken.
  See: https://github.com/mui/material-ui/issues/13253 
  */
  return (
    <Dialog
      open={isOpen}
      onClose={close}
      scroll={"paper"}
      maxWidth={"xl"}
      fullWidth
      aria-labelledby={titleId}
      aria-describedby={contentId}
      {...rest}
    >
      <DialogTitle id={titleId}>{title}</DialogTitle>

      <DialogContent dividers={true} id={contentId}>
        {children === undefined ? content : children}
      </DialogContent>

      <DialogActions style={{ justifyContent: "space-between" }}>
        {actions}
      </DialogActions>
    </Dialog>
  );
};

export default ContextBasedDialog;
