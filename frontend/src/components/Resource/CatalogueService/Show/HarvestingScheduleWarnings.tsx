import { type Identifier, useRecordContext } from "react-admin";

import { Alert, Stack } from "@mui/material";

import useServiceAlerts from "../../ServiceAlert/useServiceAlerts";

/** the state of a schedule which fires more often than a harvest takes (#693) */
const TIGHT_SCHEDULE = "harvest_schedule_too_tight";

interface ScheduleWarningsProps {
  /** the catalogue whose harvesting schedules are asked about */
  serviceId: Identifier;
}

const ScheduleWarnings = ({ serviceId }: ScheduleWarningsProps) => {
  const { data = [] } = useServiceAlerts({
    service: serviceId,
    category: TIGHT_SCHEDULE,
  });
  if (data.length === 0) return null;
  return (
    <Stack spacing={1} sx={{ mb: 2 }}>
      {data.map((alert) => (
        <Alert key={alert.id} severity="warning">
          {alert.message}
        </Alert>
      ))}
    </Stack>
  );
};

/**
 * The schedules of the shown catalogue which do not wait long enough.
 *
 * Whether a schedule keeps up with the harvest it schedules is decided in python,
 * so it is not an attribute of the catalogue but one of the alerts of the
 * cross-service attention - which is asked for with the filter the api of the
 * alerts answers (#693). The message of such an alert names the schedule and how
 * long the harvests of this catalogue measured, in the language of the request,
 * so nothing of it is translated here a second time.
 */
const HarvestingScheduleWarnings = () => {
  const service = useRecordContext();
  if (!service) return null;
  return <ScheduleWarnings serviceId={service.id} />;
};

export default HarvestingScheduleWarnings;
