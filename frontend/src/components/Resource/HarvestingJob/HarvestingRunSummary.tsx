import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Card,
  CardActionArea,
  Chip,
  Grid,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import {
  DateField,
  Link,
  useCreatePath,
  useRecordContext,
  useTranslate,
} from "react-admin";
import JsonApiReferenceField from "../../../jsonapi/components/ReferenceField";
import { Count } from "../../../jsonapi/components/Count";
import HarvestingPhaseStepper from "./HarvestingPhaseStepper";
import HarvestingJobActions from "./HarvestingJobActions";

const HarvestingRunSummary = () => {
  const run = useRecordContext();
  const translate = useTranslate();
  const createPath = useCreatePath();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (run?.doneAt) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [run?.doneAt]);
  if (!run) return null;
  const path = createPath({
    resource: "HarvestingJob",
    id: run.id,
    type: "show",
  });
  const progress = Math.min(100, Math.max(0, Number(run.progress) || 0));
  const started = run.dateCreated ? new Date(run.dateCreated).getTime() : NaN;
  const end = run.doneAt ? new Date(run.doneAt).getTime() : now;
  const seconds = Math.max(0, Math.floor((end - started) / 1000));
  const elapsed = Number.isFinite(seconds)
    ? `${Math.floor(seconds / 3600)}h ${Math.floor(seconds / 60) % 60}m ${seconds % 60}s`
    : translate("harvestRun.notRecorded");
  const counters = [
    { resource: "DatasetMetadataRecord", label: "datasets" },
    { resource: "ServiceMetadataRecord", label: "services" },
    { resource: "TemporaryMdMetadataFile", label: "unhandled" },
  ];
  return (
    <Stack spacing={2}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        sx={{ justifyContent: "space-between", gap: 1 }}
      >
        <Box>
          <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
            <Typography variant="h4">
              {translate("harvestRun.title", { id: run.id })}
            </Typography>
            <Chip
              color={run.doneAt ? "default" : "info"}
              label={run.phaseLabel}
            />
          </Stack>
          <JsonApiReferenceField
            source="service"
            reference="CatalogueService"
          />
        </Box>
        <HarvestingJobActions />
      </Stack>
      <Card variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
        <HarvestingPhaseStepper phase={run.phase} />
        <Box sx={{ bgcolor: "action.hover", p: 2, borderRadius: 1 }}>
          <Stack
            direction="row"
            sx={{ justifyContent: "space-between", gap: 1 }}
          >
            <Typography variant="subtitle1">{run.phaseLabel}</Typography>
            {run.totalRecords != null && (
              <Typography variant="subtitle1">
                {progress.toFixed(1)}%
              </Typography>
            )}
          </Stack>
          <LinearProgress
            sx={{ my: 1 }}
            value={progress}
            variant={
              !run.doneAt && run.totalRecords == null
                ? "indeterminate"
                : "determinate"
            }
            aria-label={translate("harvestingActivity.progress")}
          />
          <Typography variant="body2" color="text.secondary">
            {run.totalRecords != null
              ? translate("harvestingActivity.totalRecords", {
                  count: run.totalRecords,
                })
              : translate("harvestingActivity.discovering")}
          </Typography>
          {run.unhandledRecordsCount != null && (
            <Typography variant="body2" color="text.secondary">
              {translate("harvestingActivity.awaitingImport", {
                count: run.unhandledRecordsCount,
              })}
            </Typography>
          )}
          <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={3}
            sx={{ mt: 2 }}
          >
            <Box>
              <Typography variant="caption" color="text.secondary">
                {translate("harvestingActivity.started")}
              </Typography>
              <Typography>
                <DateField
                  source="dateCreated"
                  showTime
                  emptyText={translate("harvestRun.notRecorded")}
                />
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {translate("harvestRun.elapsed")}
              </Typography>
              <Typography>{elapsed}</Typography>
            </Box>
            {run.doneAt && (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  {translate("harvestRun.finished")}
                </Typography>
                <Typography>
                  <DateField source="doneAt" showTime />
                </Typography>
              </Box>
            )}
          </Stack>
        </Box>
      </Card>
      <Grid container spacing={2}>
        {counters.map((counter) => (
          <Grid key={counter.resource} size={{ xs: 6, md: 3 }}>
            <Card variant="outlined">
              <CardActionArea
                component={Link}
                to={`${path}/${counter.resource}`}
                sx={{ p: 2 }}
              >
                <Typography variant="body2" color="text.secondary">
                  {translate(`harvestRun.${counter.label}`)}
                </Typography>
                <Typography variant="h5">
                  <Count
                    relatedResource="HarvestingJob"
                    relatedResourceId={run.id}
                    resource={counter.resource}
                    refetchInterval={run.doneAt ? false : 5000}
                  />
                </Typography>
              </CardActionArea>
            </Card>
          </Grid>
        ))}
        <Grid size={{ xs: 6, md: 3 }}>
          <Card variant="outlined">
            <CardActionArea
              component={Link}
              to={`${path}/TemporaryMdMetadataFile?filter=${encodeURIComponent(JSON.stringify({ hasImportError: true }))}`}
              sx={{ p: 2 }}
            >
              <Typography variant="body2" color="text.secondary">
                {translate("harvestRun.errors")}
              </Typography>
              <Typography
                variant="h5"
                color={run.importErrorCount ? "warning.main" : "text.primary"}
              >
                {run.importErrorCount ?? "—"}
              </Typography>
            </CardActionArea>
          </Card>
        </Grid>
      </Grid>
      {run.importErrorCount > 0 && (
        <Alert
          severity="warning"
          action={
            <Link to={`${path}/HarvestingLog`}>
              {translate("harvestRun.viewLogs")}
            </Link>
          }
        >
          {translate("harvestingActivity.importErrors", {
            count: run.importErrorCount,
          })}
        </Alert>
      )}
    </Stack>
  );
};

export default HarvestingRunSummary;
