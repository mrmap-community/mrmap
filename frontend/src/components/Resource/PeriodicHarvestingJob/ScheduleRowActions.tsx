import { Button, Link, useRecordContext } from "react-admin";

import FormatListBulletedIcon from "@mui/icons-material/FormatListBulleted";

import RunHarvestingButton from "../Generic/ServiceShow/RunHarvestingButton";

/**
 * The actions of one row of the schedules.
 *
 * A schedule is configured on the row itself (the edit button of the grid), but
 * the two questions an administrator asks *about* it are asked elsewhere: does
 * the harvest run now, and what did the runs of its catalogue do - which is the
 * answer to "did it fire last night" (#1087). Both are links to what already
 * exists: the mutation `RunHarvestingButton` sends and the runs of the
 * catalogue.
 *
 * The button hides itself for a user who may not create a harvest, which is why
 * a user who may only view the schedules sees the link and no action (#1082).
 */
const ScheduleRowActions = () => {
  const record = useRecordContext();
  // the relation of the row is answered as a related resource, with or without
  // the record of the catalogue riding on it
  const serviceId = record?.service?.id ?? record?.service;
  if (serviceId == null) return null;
  return (
    <>
      <RunHarvestingButton serviceId={serviceId} variant="text" />
      <Button
        component={Link}
        size="small"
        startIcon={<FormatListBulletedIcon />}
        to={`/CatalogueService/${serviceId}/show/HarvestingJob`}
        label="harvestingSchedules.runs"
      />
    </>
  );
};

export default ScheduleRowActions;
