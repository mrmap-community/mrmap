import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import { SimpleList } from "react-admin";
import { formatMonitoringRun, getDuration } from "./formatMonitoringRun";

const MonitoringRunsList = () => {
  return (
    <SimpleList
      leftIcon={(record) => (
        <FiberManualRecordIcon color={record.success ? "success" : "warning"} />
      )}
      rightIcon={(record) =>
        `${record?.getMapProbeResults?.length + record?.getCapabilititesProbeResults?.length} checks, in ${getDuration(record?.dateCreated, record?.dateDone)?.toFixed(2)} s`
      }
      primaryText={(record) => `${formatMonitoringRun(record?.dateDone)}`}
      rowClick={false}
      sx={{
        p: 0,

        "& .MuiListItem-root": {
          px: 0,
          py: 0.5,
          minHeight: 32,
        },

        "& .MuiListItemText-root": {
          m: 0,
        },

        "& .MuiListItemButton-root": {
          py: 0,
        },
      }}
    />
  );
};

export default MonitoringRunsList;
