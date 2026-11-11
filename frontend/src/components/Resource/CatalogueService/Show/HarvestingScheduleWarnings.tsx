import { type Identifier, useRecordContext, useTranslate } from "react-admin";

import { Alert, Stack } from "@mui/material";

import useServiceAlerts from "../../ServiceAlert/useServiceAlerts";

/** the states of a catalogue's schedules which ask for an administrator: the
 *  schedule which fires more often than a harvest takes (#693) and the
 *  schedule which did not fire when its crontab said (#1086); the alerts api
 *  answers several categories with one comma separated value */
const SCHEDULE_STATES = "harvest_overdue,harvest_schedule_too_tight";

interface ScheduleWarningsProps {
  /** the catalogue whose harvesting schedules are asked about */
  serviceId: Identifier;
}

const ScheduleWarnings = ({ serviceId }: ScheduleWarningsProps) => {
  const { data = [] } = useServiceAlerts({
    service: serviceId,
    category: SCHEDULE_STATES,
  });
  const translate = useTranslate();
  if (data.length === 0) return null;
  return (
    <Stack spacing={1} sx={{ mb: 2 }}>
      {data.map((alert) => (
        <Alert key={alert.id} severity="warning">
          {/* the message of a too tight schedule is a full sentence which
              names the crontab and the measured duration; an alert whose
              message is only the name of its state is answered by the
              translation of the category, as the list of the alerts does */}
          {alert.message === alert.category
            ? translate(`serviceAlerts.categories.${alert.category}`)
            : alert.message}
        </Alert>
      ))}
    </Stack>
  );
};

/**
 * The schedules of the shown catalogue which did not keep their time.
 *
 * Whether a schedule keeps up with the harvest it schedules and whether it
 * fired when its crontab said is decided in python, so neither is an attribute
 * of the catalogue but one of the alerts of the cross-service attention - both
 * are asked for with the filters the api of the alerts answers (#693, #1086).
 * The message of a too tight alert names the schedule and how long the
 * harvests of this catalogue measured, in the language of the request, so
 * nothing of it is translated here a second time.
 */
const HarvestingScheduleWarnings = () => {
  const service = useRecordContext();
  if (!service) return null;
  return <ScheduleWarnings serviceId={service.id} />;
};

export default HarvestingScheduleWarnings;
