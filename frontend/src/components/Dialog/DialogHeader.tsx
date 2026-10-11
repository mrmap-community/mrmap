import CloseIcon from "@mui/icons-material/Close";
import { IconButton, Stack, Typography } from "@mui/material";
import type { PropsWithChildren } from "react";
import { useTranslate } from "react-admin";
import { useDialogContextBase } from "./DialogContextBase";

const DialogHeader = ({ children }: PropsWithChildren) => {
  const { close } = useDialogContextBase();
  const translate = useTranslate();
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
