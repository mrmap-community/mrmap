import { useFieldValue, useTranslate } from "react-admin";

import { Chip } from "@mui/material";

export interface ProcessStatusFieldProps {
  source?: string;
}

const STATUS_COLORS: Record<
  string,
  "default" | "info" | "success" | "error" | "warning"
> = {
  pending: "default",
  running: "info",
  completed: "success",
  failed: "error",
  aborted: "warning",
  // the words of the logical state contract (#1207), which this field also
  // renders when its source is `state`
  queued: "default",
  retrying: "warning",
};

/**
 * Shows the status of a background process as a chip.
 *
 * The api answers the status by the name of its choice, so the names of the
 * statuses are the keys of the translations of the background activity.
 */
const ProcessStatusField = ({ source = "status" }: ProcessStatusFieldProps) => {
  const status = useFieldValue({ source }) as string | undefined;
  const translate = useTranslate();

  if (!status) {
    return null;
  }

  return (
    <Chip
      size="small"
      color={STATUS_COLORS[status] ?? "default"}
      label={translate(`backgroundActivity.status.${status}`, { _: status })}
    />
  );
};

export default ProcessStatusField;
