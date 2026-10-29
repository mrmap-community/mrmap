import { type ReactNode } from "react";
import {
  Button,
  Identifier,
  ListProps,
  ShowButton,
  useGetIdentity,
  useRecordContext,
  useResourceDefinition,
} from "react-admin";
import { Link } from "react-router-dom";

import { PlayArrow } from "@mui/icons-material";
import UpdateIcon from "@mui/icons-material/Update";

import { type ServiceListConfig } from "../Generic/ServiceList/config";
import ServiceList from "../Generic/ServiceList/ServiceList";
import RunHarvestingButton from "./Show/RunHarvestingButton";

export interface ShowRunningHarvestingJobButtonProps {
  id: Identifier;
}

const ShowRunningHarvestingJobButton = ({
  id,
}: ShowRunningHarvestingJobButtonProps): ReactNode => {
  return (
    <ShowButton
      resource="HarvestingJob"
      record={{ id: id }}
      label="harvestingSchedules.existing"
      icon={<PlayArrow />}
    />
  );
};

export const HarvestButton = (): ReactNode => {
  const record = useRecordContext();

  if (record?.runningHarvestingJob != null) {
    return (
      <ShowRunningHarvestingJobButton id={record.runningHarvestingJob.id} />
    );
  }
  return <RunHarvestingButton serviceId={record?.id} variant="text" />;
};

const CatalogueServiceActions = (): ReactNode => {
  const record = useRecordContext();
  const { hasCreate } = useResourceDefinition({ resource: "PeriodicHarvestingJob" });
  const { data: identity } = useGetIdentity();
  const hasSchedules = (record?.periodicHarvestingJobs?.length ?? 0) > 0;
  const path = `/CatalogueService/${record?.id}/show/PeriodicHarvestingJob`;

  return (
    <>
      <HarvestButton />
      {record && hasCreate && identity?.id && (
        <Button
          component={Link}
          to={hasSchedules ? path : `${path}/create`}
          label={hasSchedules ? "harvestingSchedules.configure" : "harvestingSchedules.create"}
          startIcon={<UpdateIcon />}
        />
      )}
    </>
  );
};

/**
 * The attributes the list of registered catalogues answers, as the api names
 * them in a sparse fieldset.
 *
 * The list shows a catalogue as a row and not as a table of every column, so it
 * asks only for what a row and the details panel of a selected catalogue show -
 * see the list of registered web map services for why the states of attention
 * and the count of the records are named apart from the columns a catalogue is
 * stored with (registry/querys/alerts.py and registry/querys/explorer.py). The
 * states of the harvesting and the running harvesting job are answered by a
 * catalogue only: the first shows the failures of the harvesting in the row,
 * the second answers which harvesting the row may open.
 */
export const CATALOGUE_SERVICE_LIST_FIELDS = [
  "id",
  "title",
  "abstract",
  "string_representation",
  "hits",
  "date_stamp",
  "created_at",
  "last_modified_at",
  "has_alert",
  "monitoring_failed",
  "monitoring_failed_at",
  "update_review_required",
  "update_review_required_at",
  "update_failed",
  "update_failed_at",
  "harvest_aborted",
  "harvest_incomplete",
  "harvest_failed_at",
  "element_count",
  "running_harvesting_job",
  "periodic_harvesting_jobs",
];

/** what the list of registered catalogues asks apart from the other kinds */
export const CATALOGUE_SERVICE_LIST_CONFIG: ServiceListConfig = {
  resource: "CatalogueService",
  protocol: "CSW",
  countLabelKey: "records",
  fields: CATALOGUE_SERVICE_LIST_FIELDS,
  // a catalogue answers the harvesting of a row in its actions, which the
  // screen of services renders inside the record context of the row
  RowAction: CatalogueServiceActions,
};

/**
 * The screen which lists the registered catalogues.
 *
 * The create and edit dialogs of the resource stay routed through the
 * ListWithDialogs, which renders the generic list with these props and the
 * routes of the dialogs beside it.
 */
const CatalogueServiceList = (props: Partial<ListProps>): ReactNode => (
  <ServiceList
    {...props}
    config={CATALOGUE_SERVICE_LIST_CONFIG}
  />
);

export default CatalogueServiceList;
