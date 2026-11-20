import { type ReactNode } from "react";
import { useTranslate } from "react-admin";

import NotificationImportantIcon from "@mui/icons-material/NotificationImportant";
import { type Theme, useMediaQuery } from "@mui/material";
import Badge from "@mui/material/Badge";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";

import { useIncidentCenter } from "./IncidentCenterContext";

/**
 * The incident control of the app bar (#1321).
 *
 * One control which tells, without opening anything, how many active
 * incidents ask for the attention of this user - and opens the Incident
 * Center. The number is the `total` of the permitted active window, the same
 * query the drawer's rows and its tab label read, so indicator and list
 * cannot disagree and a private incident contributes to neither.
 *
 * It appears and disappears with its message, like the alert chip of
 * AttentionIndicator does: while nothing has been answered, while the read
 * is pending, while nothing is active - and while the read failed, which it
 * may for a transient reason and never becomes a hint: silence is also the
 * privacy answer.
 *
 * On narrow screens the words give way to a badge over the icon, the split
 * JobCenterIndicator established.
 */
const IncidentCenterIndicator = (): ReactNode => {
  const { active, setOpen } = useIncidentCenter();
  const translate = useTranslate();
  const isWideEnough = useMediaQuery<Theme>((theme) =>
    theme.breakpoints.up("sm"),
  );

  if (active.error || active.isPending || !active.total) {
    return null;
  }

  const label = translate("incidentCenter.activeCount", {
    smart_count: active.total,
  });
  const hasError = (active.data ?? []).some(
    (record) => record.severity === "error",
  );

  if (isWideEnough) {
    return (
      <Button
        color="inherit"
        size="small"
        startIcon={<NotificationImportantIcon />}
        onClick={() => setOpen(true)}
        aria-label={label}
        sx={{
          textTransform: "none",
          border: 1,
          borderColor: "action.disabledBackground",
          borderRadius: 2,
          gap: 0.5,
        }}
      >
        <Typography
          component="span"
          variant="body2"
          color={hasError ? "error.light" : "warning.light"}
        >
          {active.total}
        </Typography>
        <Typography component="span" variant="body2">
          {translate("incidentCenter.title")}
        </Typography>
      </Button>
    );
  }

  return (
    <Badge
      badgeContent={active.total}
      color={hasError ? "error" : "warning"}
      sx={{ alignSelf: "center", mx: 0.5 }}
    >
      <IconButton
        color="inherit"
        onClick={() => setOpen(true)}
        aria-label={label}
      >
        <NotificationImportantIcon />
      </IconButton>
    </Badge>
  );
};

export default IncidentCenterIndicator;
