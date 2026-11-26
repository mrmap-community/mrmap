import { Link, useCreatePath, useTranslate } from "react-admin";

import { Alert, Chip, Stack, Typography } from "@mui/material";

import {
  systemComponents,
  useSystemStatus,
} from "../../../context/SystemStatusContext";

/** the states of a component the dashboard answers above the inventory, in the
 *  order it answers them; `healthy` answers nothing and an `unknown` state is
 *  answered by the unreadable status, which never reads as a healthy one */
const CRITICAL_STATES = ["down", "degraded"] as const;

/**
 * The critical problems of the deployment, above everything else the dashboard
 * answers.
 *
 * The states are read from the context of the system status the app bar already
 * polls (#833), so the dashboard answers them without a request of its own and
 * never disagrees with the indicator of the app bar. Nothing answers while the
 * deployment is healthy, because an administrator reads this screen by its
 * exceptions. A status which cannot be read - refused, stale or missing -
 * answers a warning instead, so an unreadable deployment is never displayed as
 * a healthy one; a caller who may not read the status at all sees nothing and
 * stays on the dashboard.
 *
 * The rows deep link to the system status screen, which is the authoritative
 * details view of these states and is deliberately not duplicated here.
 */
const CriticalAlerts = () => {
  const { data, isPending, forbidden, stale } = useSystemStatus();
  const translate = useTranslate();
  const createPath = useCreatePath();
  if (forbidden || isPending) return null;

  const detailsPath = createPath({ resource: "SystemInfo", type: "list" });
  const details = (
    <Typography component="span" variant="body2">
      <Link to={detailsPath}>{translate("systemStatus.viewDetails")}</Link>
    </Typography>
  );
  const row = (
    severity: "error" | "warning",
    body: string,
    names?: string[],
  ) => (
    <Alert key={body} severity={severity} sx={{ py: 0.5 }}>
      <Stack
        direction="row"
        spacing={1}
        sx={{ alignItems: "center", flexWrap: "wrap", rowGap: 0.5 }}
      >
        <Typography component="span" variant="body2">
          {body}
        </Typography>
        {names?.map((name) => (
          <Chip
            key={name}
            size="small"
            variant="outlined"
            color={severity === "error" ? "error" : "warning"}
            label={translate(`systemStatus.${name}`)}
          />
        ))}
        {details}
      </Stack>
    </Alert>
  );

  // a status which cannot be read answers itself, whatever the last
  // observation said about the components of the deployment
  if (stale) {
    return row("warning", translate("systemStatus.stale"));
  }

  const rows = CRITICAL_STATES.flatMap((state) => {
    const names = data
      ? systemComponents.filter(
          (name) => data.components[name]?.status === state,
        )
      : [];
    if (names.length === 0) return [];
    return [
      row(
        state === "down" ? "error" : "warning",
        translate(`dashboard.criticalAlerts.${state}`, {
          smart_count: names.length,
        }),
        names,
      ),
    ];
  });
  if (rows.length === 0) return null;

  return <Stack spacing={1}>{rows}</Stack>;
};

export default CriticalAlerts;
