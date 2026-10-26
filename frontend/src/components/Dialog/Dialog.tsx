import type { PropsWithChildren, ReactNode } from "react";
import { useId } from "react";

import Dialog, { DialogProps } from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";

import { useOptionalDialogContextBase } from "./DialogContextBase";

/** The sections one dialog renders and how the content and actions look. */
export interface DialogSectionsProps {
  /** Headline of the dialog; the section is omitted when it answers nothing. */
  title?: ReactNode;
  /** Short description which is read as the aria description of the dialog.
   *  Without it the content answers the description, as it always did. */
  description?: ReactNode;
  /** Body of the dialog; `children` of the dialog win over this prop. */
  content?: ReactNode;
  /** Buttons of the actions row; the row is omitted when it answers nothing. */
  actions?: ReactNode;
  /** Divider around the content, as the shared dialog has always drawn it. */
  contentDividers?: boolean;
  /** Where the actions row gathers its buttons. */
  actionsAlign?: "flex-start" | "center" | "flex-end" | "space-between";
}

export interface ControlledDialogProps
  extends
    Omit<DialogProps, "open" | "onClose" | "children" | "title" | "content">,
    DialogSectionsProps {
  /** Controlled mode: the caller owns the open state. */
  open: boolean;
  onClose?: () => void;
  children?: ReactNode;
}

export type ContextBasedDialogProps =
  | ControlledDialogProps
  | (Omit<DialogProps, "open" | "onClose" | "children"> & {
      children?: ReactNode;
    });

interface ContextDialogProps {
  children?: ReactNode;
  context: NonNullable<ReturnType<typeof useOptionalDialogContextBase>>;
  dialogProps: Omit<DialogProps, "open" | "onClose" | "children">;
}

interface DialogShellProps extends PropsWithChildren {
  open: boolean;
  onClose?: () => void;
  title?: ReactNode;
  description?: ReactNode;
  content?: ReactNode;
  /** Whether an explicit content was answered, so `null` may hide content. */
  actions?: ReactNode;
  contentDividers?: boolean;
  actionsAlign?: "flex-start" | "center" | "flex-end" | "space-between";
  dialogProps: Omit<DialogProps, "open" | "onClose">;
}

const DialogShell = ({
  open,
  onClose,
  title,
  description,
  content,
  actions,
  contentDividers = true,
  actionsAlign = "space-between",
  children,
  dialogProps,
}: DialogShellProps) => {
  const id = useId();
  const titleId = `${id}-title`;
  const contentId = `${id}-content`;
  const descriptionId = `${id}-description`;

  /* Edit and Form component needed to be outside the Dialog component.
  Otherwise the scroll feature is broken.
  See: https://github.com/mui/material-ui/issues/13253
  */
  return (
    <Dialog
      open={open}
      onClose={onClose}
      scroll={"paper"}
      maxWidth={"xl"}
      fullWidth
      aria-labelledby={title != null ? titleId : undefined}
      aria-describedby={
        description != null
          ? descriptionId
          : content != null || children != null
            ? contentId
            : undefined
      }
      {...dialogProps}
    >
      {title != null && <DialogTitle id={titleId}>{title}</DialogTitle>}

      {description != null && (
        <DialogContentText id={descriptionId} sx={{ px: 3, pt: 2 }}>
          {description}
        </DialogContentText>
      )}

      {content != null && (
        <DialogContent dividers={contentDividers} id={contentId}>
          {children === undefined ? content : children}
        </DialogContent>
      )}

      {actions != null && (
        <DialogActions sx={{ justifyContent: actionsAlign }}>
          {actions}
        </DialogActions>
      )}
    </Dialog>
  );
};

/** The dialog whose title, content and actions come from the `DialogBase`. */
const ContextDialog = ({
  children,
  context,
  dialogProps,
}: ContextDialogProps) => {
  const { isOpen, close, title, content, actions } = context;
  return (
    <DialogShell
      open={isOpen}
      onClose={close}
      title={title}
      content={children === undefined ? content : children}
      actions={actions}
      dialogProps={dialogProps}
    />
  );
};

/** The dialog whose open state, sections and close behavior the caller owns. */
const ControlledDialog = ({
  open,
  onClose,
  title,
  description,
  content,
  actions,
  contentDividers,
  actionsAlign,
  children,
  ...dialogProps
}: ControlledDialogProps) => (
  <DialogShell
    open={open}
    onClose={onClose}
    title={title}
    description={description}
    content={children === undefined ? content : children}
    actions={actions}
    contentDividers={contentDividers}
    actionsAlign={actionsAlign}
    dialogProps={dialogProps}
  />
);

/**
 * The shared dialog shell of the frontend.
 *
 * Inside a `DialogBase` it answers the title, content and actions which
 * `open` handed to that base — the create, edit and history dialogs use this
 * mode. With an `open` prop it takes its sections and its close callback from
 * the caller instead — controlled, local state and route derived dialogs use
 * this mode. Both modes render the same sections, ids and scrolling.
 */
const ContextBasedDialog = ({
  children,
  ...props
}: ContextBasedDialogProps) => {
  const dialogContext = useOptionalDialogContextBase();
  const controlled =
    (props as ControlledDialogProps).open !== undefined ||
    dialogContext === undefined;
  if (controlled) {
    return (
      <ControlledDialog
        {...(props as ControlledDialogProps)}
        open={(props as ControlledDialogProps).open ?? false}
        {...(children !== undefined ? { children } : {})}
      />
    );
  }
  return (
    <ContextDialog
      context={dialogContext}
      dialogProps={props as ContextDialogProps["dialogProps"]}
    >
      {children}
    </ContextDialog>
  );
};

export default ContextBasedDialog;
