import {
  DateField,
  Show,
  type ShowProps,
  useRecordContext,
  useTranslate,
} from "react-admin";

import { Alert, Box, Chip, Paper, Stack, Typography } from "@mui/material";

import JsonApiReferenceField from "../../../jsonapi/components/ReferenceField";
import { getDuration } from "../WebMapService/Show/Overview/MonitoringRuns/formatMonitoringRun";
import MonitoringProbeResults, {
  type ProbeResultsGroup,
} from "./MonitoringProbeResults";

export interface RunProbeResultsConfig {
  /** resource which stores the results of the probe */
  resource: string;
  /** kind of the probe which created the results */
  type: ProbeResultsGroup["type"];
  /** field of the run which refers to the results of the probe */
  source: string;
}

export interface MonitoringRunDetailsProps {
  /** resource of the setting which scheduled the run */
  settingResource: string;
  /** configuration of the probe results which belong to a run */
  probeResults: RunProbeResultsConfig[];
}

export interface ShowMonitoringRunProps
  extends ShowProps,
    MonitoringRunDetailsProps {}

const MonitoringRunDetails = ({
  settingResource,
  probeResults,
}: MonitoringRunDetailsProps) => {
  const record = useRecordContext();
  const translate = useTranslate();
  if (!record) return null;

  const completed = Boolean(record.dateDone);
  const status = !completed ? "running" : record.success ? "passed" : "failed";
  const severity = !completed ? "info" : record.success ? "success" : "error";
  const duration = getDuration(record.dateCreated, record.dateDone);
  const groups: ProbeResultsGroup[] = probeResults.map(
    ({ resource, type, source }) => ({
      resource,
      type,
      ids: ((record[source] as { id: string | number }[] | undefined) ?? []).map(
        (result) => result.id,
      ),
    }),
  );

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
                  reference={settingResource}
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
      <MonitoringProbeResults key={record.id} groups={groups} />
    </Stack>
  );
};

const ShowMonitoringRun = ({
  settingResource,
  probeResults,
  ...props
}: ShowMonitoringRunProps) => (
  <Show {...props} actions={false}>
    <MonitoringRunDetails
      settingResource={settingResource}
      probeResults={probeResults}
    />
  </Show>
);

export default ShowMonitoringRun;
