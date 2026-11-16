import {
  BasenameContextProvider,
  type RaRecord,
  RecordContext,
  ShowButton,
  SimpleList,
  useResourceContext,
} from "react-admin";

import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import { Box } from "@mui/material";

import UpdateJobChangeSummary from "../../../../WebMapServiceUpdateJob/UpdateJobChangeSummary";
import { formatMonitoringRun } from "../MonitoringRuns/formatMonitoringRun";

/** the bullet an update job row carries: review-required jobs warn */
const updateJobIcon = (record: RaRecord) => (
  <FiberManualRecordIcon
    color={record.statusCode === 2 ? "warning" : "success"}
  />
);

/** the way to a job's own page, without the surrounding screen's basename */
const updateJobShowAction = (resource?: string) => {
  const showAction = (record: RaRecord) => (
      <BasenameContextProvider basename="">
        <ShowButton
          record={record}
          resource={resource}
          label="ra.action.show"
          variant="contained"
          color={record.statusCode === 2 ? "warning" : "primary"}
          icon={false}
        />
      </BasenameContextProvider>
  );
  return showAction;
};

/** what a run did, told from its mappings: the question a job row answers */
const describeChanges = (record: RaRecord): string => {
    const changes = [];
    const layersChanged = (record.mappings ?? []).filter(
      (mapping: RaRecord) => mapping.delta?.length > 0,
    );
    const newLayers = (record.mappings ?? []).filter(
      (mapping: RaRecord) =>
        mapping.newLayer !== undefined && mapping.oldLayer === undefined,
    );
    const deletedLayers = (record.mappings ?? []).filter(
      (mapping: RaRecord) =>
        mapping.newLayer === undefined && mapping.oldLayer !== undefined,
    );

    layersChanged.length > 0 &&
      changes.push(`${layersChanged.length || 0} layer(s) changed`);
    deletedLayers.length > 0 &&
      changes.push(`${deletedLayers.length} layer(s) are marked for deletion`);
    newLayers.length > 0 &&
      changes.push(`${newLayers.length || 0} new layer(s)`);

    return changes.join(" · ");
};

/** the line under a job: its status, what it changed and where to look closer */
const updateJobSecondaryText = (resource?: string) => {
  const secondaryText = (record: RaRecord) => (
      <Box
        component="span"
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          flexWrap: "wrap",
        }}
      >
        <span>
          {[record.status, describeChanges(record)].filter(Boolean).join(" · ")}
        </span>
        {resource === "WebMapServiceUpdateJob" &&
          record.doneAt &&
          record.service?.id && (
            <RecordContext value={record}>
              <UpdateJobChangeSummary
                compact
              />
            </RecordContext>
          )}
      </Box>
  );
  return secondaryText;
};

const UpdateJobsList = () => {
  const resource = useResourceContext();

  return (
    <SimpleList
      dense
      disablePadding
      sx={{
        "& .MuiListItem-root": { py: 0.25 },
        "& .MuiListItemText-root": { my: 0 },
      }}
      leftIcon={updateJobIcon}
      rightIcon={updateJobShowAction(resource)}
      primaryText={(record) =>
        formatMonitoringRun(record.doneAt ?? record.dateCreated)
      }
      secondaryText={updateJobSecondaryText(resource)}
      rowClick={false}
    />
  );
};

export default UpdateJobsList;
