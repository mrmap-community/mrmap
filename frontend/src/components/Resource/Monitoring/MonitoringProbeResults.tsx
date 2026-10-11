import { useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Chip,
  Divider,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlined";
import HelpOutlineIcon from "@mui/icons-material/HelpOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  type Identifier,
  type RaRecord,
  Loading,
  useGetMany,
  useTranslate,
} from "react-admin";

const definitions = {
  GetCapabilities: [
    { label: "validXml", field: "checkResponseIsValidXml" },
    { label: "requiredContent", field: "checkResponseDoesContain" },
    { label: "noExceptions", field: "checkResponseDoesNotContain" },
  ],
  GetMap: [
    { label: "imageResponse", field: "checkResponseImage" },
    { label: "noExceptions", field: "checkResponseDoesNotContain" },
  ],
} as const;
type ProbeType = keyof typeof definitions;
type Status = "failed" | "passed" | "notRecorded";
interface Check {
  label: string;
  success: boolean | null;
  message?: string | null;
}
interface Probe {
  id: Identifier;
  type: ProbeType;
  checks: Check[];
  status: Status;
}
const styles = {
  failed: { color: "error", Icon: ErrorOutlineIcon },
  passed: { color: "success", Icon: CheckCircleOutlineIcon },
  notRecorded: { color: "default", Icon: HelpOutlineIcon },
} as const;

function toProbe(record: RaRecord, type: ProbeType): Probe {
  const checks = definitions[type].map(({ label, field }) => ({
    label,
    success: record[`${field}Success`] ?? null,
    message: record[`${field}Message`],
  }));
  const status = checks.some((check) => check.success === false)
    ? "failed"
    : checks.some((check) => check.success === true)
      ? "passed"
      : "notRecorded";
  return { id: record.id, type, checks, status };
}

function ProbeCard({ probe }: { probe: Probe }) {
  const translate = useTranslate();
  const { color, Icon } = styles[probe.status];
  const failedChecks = probe.checks.filter((check) => check.success === false);
  const passedChecks = probe.checks.filter((check) => check.success === true);
  return (
    <Accordion
      defaultExpanded={probe.status === "failed"}
      disableGutters
      variant="outlined"
      sx={{ "&:before": { display: "none" } }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Stack spacing={1} sx={{ width: "100%", minWidth: 0 }}>
          <Stack
            direction="row"
            spacing={1}
            sx={{ alignItems: "center", flexWrap: "wrap" }}
          >
            <Icon color={color === "default" ? "disabled" : color} />
            <Typography sx={{ fontWeight: 600 }}>{probe.type}</Typography>
            <Chip
              size="small"
              color={color}
              label={translate(`monitoringRun.${probe.status}`)}
            />
            <Typography variant="caption" color="text.secondary">
              {String(probe.id)}
            </Typography>
          </Stack>
          <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
            {probe.status === "failed"
              ? failedChecks
                  .map(
                    (check) =>
                      `${translate(`monitoringRun.${check.label}`)}: ${check.message || translate("monitoringRun.noMessage")}`,
                  )
                  .join(" · ")
              : translate(
                  probe.status === "passed"
                    ? "monitoringRun.checksPassed"
                    : "monitoringRun.notRecordedMessage",
                  { count: passedChecks.length },
                )}
          </Typography>
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <Stack divider={<Divider />} spacing={1.5}>
          {[...probe.checks]
            .sort(
              (a, b) =>
                Number(b.success === false) - Number(a.success === false),
            )
            .map((check) => {
              const checkStatus =
                check.success === false
                  ? "failed"
                  : check.success === true
                    ? "passed"
                    : "notRecorded";
              const { Icon: CheckIcon, color: checkColor } =
                styles[checkStatus];
              return (
                <Stack key={check.label} direction="row" spacing={1.5}>
                  <CheckIcon
                    color={checkColor === "default" ? "disabled" : checkColor}
                  />
                  <Box sx={{ minWidth: 0 }}>
                    <Typography sx={{ fontWeight: 600 }}>
                      {translate(`monitoringRun.${check.label}`)} ·{" "}
                      {translate(`monitoringRun.${checkStatus}`)}
                    </Typography>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                    >
                      {check.message ||
                        translate(
                          check.success == null
                            ? "monitoringRun.notRecordedMessage"
                            : "monitoringRun.noMessage",
                        )}
                    </Typography>
                  </Box>
                </Stack>
              );
            })}
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}

export default function MonitoringProbeResults({
  capabilitiesIds,
  mapIds,
}: {
  capabilitiesIds: Identifier[];
  mapIds: Identifier[];
}) {
  const translate = useTranslate();
  const [filter, setFilter] = useState<Status | "all">("all");
  const capabilities = useGetMany(
    "GetCapabilitiesProbeResult",
    { ids: capabilitiesIds },
    { enabled: capabilitiesIds.length > 0 },
  );
  const maps = useGetMany(
    "GetMapProbeResult",
    { ids: mapIds },
    { enabled: mapIds.length > 0 },
  );
  if (capabilities.error || maps.error)
    return (
      <Alert severity="error">
        {translate("monitoringRun.resultsLoadError")}
      </Alert>
    );
  if (
    (capabilitiesIds.length > 0 && capabilities.isPending) ||
    (mapIds.length > 0 && maps.isPending)
  )
    return <Loading />;
  const probes = [
    ...(capabilities.data ?? []).map((record) =>
      toProbe(record, "GetCapabilities"),
    ),
    ...(maps.data ?? []).map((record) => toProbe(record, "GetMap")),
  ].sort(
    (a, b) => Number(b.status === "failed") - Number(a.status === "failed"),
  );
  const visible = probes.filter(
    (probe) => filter === "all" || probe.status === filter,
  );
  return (
    <Stack spacing={2}>
      <Box
        sx={{
          display: "grid",
          gap: 2,
          gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
        }}
      >
        {(["passed", "failed"] as const).map((status) => (
          <Paper
            variant="outlined"
            key={status}
            sx={{
              p: 2,
              borderTop: 4,
              borderTopColor: `${styles[status].color}.main`,
            }}
          >
            <Typography variant="h4" sx={{ fontWeight: 600 }}>
              {probes.filter((probe) => probe.status === status).length}
            </Typography>
            <Typography>{translate(`monitoringRun.${status}`)}</Typography>
          </Paper>
        ))}
      </Box>
      <Typography variant="h6">
        {translate("monitoringRun.probeResults")}
      </Typography>
      <Stack direction="row" sx={{ gap: 1, flexWrap: "wrap" }}>
        {(["all", "failed", "passed", "notRecorded"] as const).map((status) => (
          <Chip
            key={status}
            label={translate(
              status === "all" ? "updateReview.all" : `monitoringRun.${status}`,
            )}
            color={filter === status ? "primary" : "default"}
            variant={filter === status ? "filled" : "outlined"}
            onClick={() => setFilter(status)}
          />
        ))}
      </Stack>
      {visible.map((probe) => (
        <ProbeCard key={`${probe.type}:${probe.id}`} probe={probe} />
      ))}
      {!visible.length && (
        <Typography color="text.secondary">
          {translate(
            probes.length
              ? "monitoringRun.noMatchingResults"
              : "monitoringRun.noResults",
          )}
        </Typography>
      )}
    </Stack>
  );
}
