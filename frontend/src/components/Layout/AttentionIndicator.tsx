import { useCreatePath, useRedirect, useTranslate } from "react-admin";

import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Chip, Tooltip } from "@mui/material";

import useServiceAlerts from "../Resource/ServiceAlert/useServiceAlerts";

const AttentionIndicator = () => {
  const { data, total, error, isPending } = useServiceAlerts();
  const translate = useTranslate();
  const redirect = useRedirect();
  const createPath = useCreatePath();
  if (error || isPending || !total) return null;
  const label = translate("serviceAlerts.count", { smart_count: total });
  return (
    <Tooltip title={label}>
      <Chip
        component="button"
        type="button"
        size="small"
        clickable
        icon={<WarningAmberIcon />}
        color={
          data?.some((record) => record.severity === "error")
            ? "error"
            : "warning"
        }
        label={total}
        aria-label={label}
        onClick={() =>
          redirect(createPath({ resource: "ServiceAlert", type: "list" }))
        }
        sx={{ alignSelf: "center", mx: 0.5 }}
      />
    </Tooltip>
  );
};

export default AttentionIndicator;
