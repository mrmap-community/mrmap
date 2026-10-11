import { Alert, Box, Chip, Paper, Stack, Typography } from "@mui/material";
import {
  DateField,
  Show,
  type ShowProps,
  useRecordContext,
  useTranslate,
} from "react-admin";

import MonitoringProbeResults from "./MonitoringProbeResults";
import JsonApiReferenceField from "../../../jsonapi/components/ReferenceField";
import { getDuration } from "../WebMapService/Show/Overview/MonitoringRuns/formatMonitoringRun";

const MonitoringRunDetails = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  if (!record) return null;

  const completed = Boolean(record.dateDone);
  const status = !completed ? "running" : record.success ? "passed" : "failed";
  const severity = !completed ? "info" : record.success ? "success" : "error";
  const duration = getDuration(record.dateCreated, record.dateDone);

  return (
    <Stack spacing={3} sx={{ p: { xs: 1, md: 3 } }}>
      <Stack
        direction="row"
        spacing={2}
        sx={{ alignItems: "center", flexWrap: "wrap" }}
      >
        <Typography variant="h4" sx={{ fontWeight: 600 }}>
          {translate("monitoringRun.title")}
        </Typography>
        <Chip color={severity} label={translate(`monitoringRun.${status}`)} />
      </Stack>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ overflowWrap: "anywhere" }}
      >
        {translate("monitoringRun.run", { id: record.id })}
      </Typography>
      <Alert severity={severity}>
        {translate(`monitoringRun.${status}Message`)}
      </Alert>
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          {translate("monitoringRun.details")}
        </Typography>
        <Box
          sx={{
            display: "grid",
            gap: 3,
            gridTemplateColumns: {
              xs: "1fr",
              sm: "repeat(2, minmax(0, 1fr))",
              lg: "repeat(4, minmax(0, 1fr))",
            },
          }}
        >
          <Box>
            <Typography variant="caption" color="text.secondary">
              {translate("monitoringRun.started")}
            </Typography>
            <Box>
              <DateField source="dateCreated" showTime />
            </Box>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              {translate("monitoringRun.finished")}
            </Typography>
            <Box>
              {completed ? (
                <DateField source="dateDone" showTime />
              ) : (
                <Typography variant="body2">
                  {translate("monitoringRun.running")}
                </Typography>
              )}
            </Box>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              {translate("monitoringRun.duration")}
            </Typography>
            <Typography variant="body2">
              {duration !== undefined && Number.isFinite(duration)
                ? `${duration.toFixed(2)} s`
                : "—"}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              {translate("monitoringRun.setting")}
            </Typography>
            <Box>
              {record.setting ? (
                <JsonApiReferenceField
                  source="setting"
                  reference="WebMapServiceMonitoringSetting"
                />
              ) : (
                <Typography variant="body2">
                  {translate("monitoringRun.settingUnavailable")}
                </Typography>
              )}
            </Box>
          </Box>
        </Box>
      </Paper>
      <MonitoringProbeResults
        key={record.id}
        capabilitiesIds={(record.getCapabilititesProbeResults ?? []).map(
          (result: { id: string | number }) => result.id,
        )}
        mapIds={(record.getMapProbeResults ?? []).map(
          (result: { id: string | number }) => result.id,
        )}
      />
    </Stack>
  );
};

const ShowWebMapServiceMonitoringRun = (props: ShowProps) => (
  <Show {...props} actions={false}>
    <MonitoringRunDetails />
  </Show>
);

export default ShowWebMapServiceMonitoringRun;
