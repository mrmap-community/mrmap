import { useCallback } from "react";
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

const UpdateJobsList = () => {
  const resource = useResourceContext();
  const changes = useCallback((record: RaRecord) => {
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
  }, []);

  return (
    <SimpleList
      dense
      disablePadding
      sx={{
        "& .MuiListItem-root": { py: 0.25 },
        "& .MuiListItemText-root": { my: 0 },
      }}
      leftIcon={(record) => (
        <FiberManualRecordIcon
          color={record.statusCode === 2 ? "warning" : "success"}
        />
      )}
      rightIcon={(record) => (
        <BasenameContextProvider basename="">
          <ShowButton
            record={record}
            resource="WebMapServiceUpdateJob"
            label="ra.action.show"
            variant="contained"
            color={record.statusCode === 2 ? "warning" : "primary"}
            icon={false}
          />
        </BasenameContextProvider>
      )}
      primaryText={(record) =>
        formatMonitoringRun(record.doneAt ?? record.dateCreated)
      }
      secondaryText={(record) => (
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
            {[record.status, changes(record)].filter(Boolean).join(" · ")}
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
      )}
      rowClick={false}
    />
  );
};

export default UpdateJobsList;
