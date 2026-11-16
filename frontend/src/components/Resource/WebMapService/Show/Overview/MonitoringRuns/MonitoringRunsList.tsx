import {
  BasenameContextProvider,
  type RaRecord,
  ShowButton,
  SimpleList,
  useTranslate,
} from "react-admin";

import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";

import { formatMonitoringRun, getDuration } from "./formatMonitoringRun";

/** the bullet a run row carries: its outcome */
const runIcon = (record: RaRecord) => (
  <FiberManualRecordIcon color={record.success ? "success" : "error"} />
);

/** the way to a run's own page, without the surrounding screen's basename */
const runShowAction = (record: RaRecord) => (
  <BasenameContextProvider basename="">
    <ShowButton
      record={record}
      resource="WebMapServiceMonitoringRun"
      label="ra.action.show"
      variant="contained"
      icon={false}
    />
  </BasenameContextProvider>
);

const MonitoringRunsList = () => {
  const translate = useTranslate();
  return (
    <SimpleList
      dense
      disablePadding
      sx={{
        "& .MuiListItem-root": { py: 0.5 },
        "& .MuiListItemText-root": { my: 0 },
      }}
      leftIcon={runIcon}
      rightIcon={runShowAction}
      primaryText={(record) =>
        formatMonitoringRun(record.dateDone ?? record.dateCreated)
      }
      secondaryText={(record) => {
        const checks =
          (record.getMapProbeResults?.length ?? 0) +
          (record.getCapabilititesProbeResults?.length ?? 0);
        const duration = getDuration(record.dateCreated, record.dateDone);
        return [
          translate(
            `resources.WebMapServiceMonitoringRun.${record.success ? "passed" : "failed"}`,
          ),
          `${checks} checks`,
          duration !== undefined ? `${duration.toFixed(2)} s` : undefined,
        ]
          .filter(Boolean)
          .join(" · ");
      }}
      rowClick={false}
    />
  );
};

export default MonitoringRunsList;
