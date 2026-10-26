import type { PropsWithChildren } from "react";
import { useTranslate } from "react-admin";

import CloseIcon from "@mui/icons-material/Close";
import { IconButton, Stack, Typography } from "@mui/material";

import { useOptionalDialogContextBase } from "./DialogContextBase";

/**
 * The headline of a dialog with an accessible close button.
 *
 * Inside a `DialogBase` the button closes that base; a controlled caller
 * hands its own dismissal to `onClose`.
 */
const DialogHeader = ({
  children,
  onClose,
}: PropsWithChildren<{ onClose?: () => void }>) => {
  const dialogContext = useOptionalDialogContextBase();
  const translate = useTranslate();
  const close = onClose ?? dialogContext?.close ?? (() => undefined);
  return (
    <Stack
      direction="row"
      sx={{ justifyContent: "space-between", alignItems: "center" }}
    >
      <Typography component="span" variant="h5">
        {children}
      </Typography>
      <IconButton onClick={close} aria-label={translate("ra.action.close")}>
        <CloseIcon />
      </IconButton>
    </Stack>
  );
};

export default DialogHeader;
