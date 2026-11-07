import { type Identifier, useRecordContext } from "react-admin";

import { Alert, Stack } from "@mui/material";

import useServiceAlerts from "../../ServiceAlert/useServiceAlerts";

interface ScheduleWarningsProps {
  /** the catalogue whose harvesting schedules are asked about */
  serviceId: Identifier;
}

const ScheduleWarnings = ({ serviceId }: ScheduleWarningsProps) => {
  // the api answers one exact category per request, and the hook paginates a
  // handful of rows: a single unfiltered request would hide a warning behind
  // the five most severe alerts of the catalogue, so each state is asked for
  // by itself
  const tight = useServiceAlerts({
    service: serviceId,
    category: "harvest_schedule_too_tight",
  });
  const overdue = useServiceAlerts({
    service: serviceId,
    category: "harvest_overdue",
  });
  const warnings = [...(tight.data ?? []), ...(overdue.data ?? [])];
  if (warnings.length === 0) return null;
  return (
    <Stack spacing={1} sx={{ mb: 2 }}>
      {warnings.map((alert) => (
        <Alert key={alert.id} severity={alert.severity}>
          {alert.message}
        </Alert>
      ))}
    </Stack>
  );
};

/**
 * The schedules of the shown catalogue which did not keep their promise.
 *
 * Whether a schedule keeps up with the harvest it schedules, and whether it ran
 * when it was expected, is decided in python, so neither is an attribute of the
 * catalogue but one of the alerts of the cross-service attention - which is asked
 * for with the filter the api of the alerts answers (#693). The message of such
 * an alert names the schedule and what was measured, in the language of the
 * request, so nothing of it is translated here a second time.
 */
const HarvestingScheduleWarnings = () => {
  const service = useRecordContext();
  if (!service) return null;
  return <ScheduleWarnings serviceId={service.id} />;
};

export default HarvestingScheduleWarnings;
