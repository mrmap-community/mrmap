import { useCallback } from "react";
import {
  BasenameContextProvider,
  type RaRecord,
  ShowButton,
  SimpleList,
} from "react-admin";

import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";

import { formatMonitoringRun } from "../MonitoringRuns/formatMonitoringRun";

const UpdateJobsList = () => {
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
        "& .MuiListItem-root": { py: 0.5 },
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
      secondaryText={(record) =>
        [record.status, changes(record)].filter(Boolean).join(" · ")
      }
      rowClick={false}
    />
  );
};

export default UpdateJobsList;
