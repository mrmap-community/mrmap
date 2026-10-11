import {
  Alert,
  Box,
  Chip,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import {
  Button,
  DateField,
  Loading,
  NumberField,
  RecordContextProvider,
  useListContext,
  useRecordContext,
  useTranslate,
} from "react-admin";
import { Link } from "react-router-dom";
import type { PropsWithChildren } from "react";
import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import useOperation from "../../../../jsonapi/hooks/useOperation";
import SimpleCard from "../../../MUI/SimpleCard";
import HarvestingPhaseStepper from "../../HarvestingJob/HarvestingPhaseStepper";
import HarvestingDailyStatsChart from "../HarvestingDailyStatsChart";

const HarvestingActivityCardBase = ({ children }: PropsWithChildren) => {
  const service = useRecordContext();
  const translate = useTranslate();
  return (
    <SimpleCard
      title={translate("serviceShow.harvesting")}
      cardProps={{ variant: "outlined", sx: { width: "100%", minWidth: 0 } }}
      footer={
        <Button
          component={Link}
          to={`/CatalogueService/${service?.id}/show/HarvestingJob`}
          label="harvestingActivity.viewAll"
        />
      }
    >
      <Stack spacing={2}>
        {children}
        <Stack direction="row" spacing={3} sx={{ flexWrap: "wrap", gap: 1 }}>
          {[
            "harvestedDatasetCount",
            "harvestedServiceCount",
            "harvestedTotalCount",
          ].map((source) => (
            <Box key={source}>
              <Typography variant="caption" color="text.secondary">
                {translate(`harvestingActivity.${source}`)}
              </Typography>
              <Typography>
                <NumberField source={source} />
              </Typography>
            </Box>
          ))}
        </Stack>
        <HarvestingDailyStatsChart
          resource="HarvestedMetadataRelation"
          filter={{ service: service?.id }}
        />
      </Stack>
    </SimpleCard>
  );
};

const HarvestingActivityList = () => {
  const { data, isPending, error } = useListContext();
  const translate = useTranslate();
  if (isPending) return <Loading />;
  if (error)
    return (
      <Alert severity="error">
        {translate("harvestingActivity.loadError")}
      </Alert>
    );
  if (!data?.length)
    return (
      <Typography color="text.secondary">
        {translate("harvestingActivity.empty")}
      </Typography>
    );
  return (
    <Stack spacing={2}>
      {data.map((run) => {
        const active = !run.doneAt;
        const progress = Math.min(100, Math.max(0, Number(run.progress) || 0));
        const knownTotal = typeof run.totalRecords === "number";
        return (
          <RecordContextProvider key={run.id} value={run}>
            <Box
              sx={{
                p: 2,
                border: 1,
                borderColor: active ? "info.main" : "divider",
                borderRadius: 1,
              }}
            >
              <Stack
                direction="row"
                sx={{
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 1,
                }}
              >
                <Typography variant="subtitle2">
                  {translate(
                    active
                      ? "harvestingActivity.processing"
                      : "harvestingActivity.finished",
                  )}
                </Typography>
                <Chip
                  size="small"
                  color={active ? "info" : "default"}
                  label={run.phaseLabel}
                />
              </Stack>
              <HarvestingPhaseStepper phase={run.phase} />
              <LinearProgress
                sx={{ my: 1.5 }}
                aria-label={translate("harvestingActivity.progress")}
                variant={
                  active && !knownTotal ? "indeterminate" : "determinate"
                }
                value={progress}
              />
              <Stack
                direction="row"
                sx={{
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: 1,
                }}
              >
                <Typography variant="body2" color="text.secondary">
                  {knownTotal
                    ? translate("harvestingActivity.totalRecords", {
                        count: run.totalRecords,
                      })
                    : translate("harvestingActivity.discovering")}
                </Typography>
                {knownTotal && (
                  <Typography variant="body2">
                    {progress.toFixed(1)}%
                  </Typography>
                )}
              </Stack>
              {typeof run.unhandledRecordsCount === "number" && (
                <Typography variant="body2" color="text.secondary">
                  {translate("harvestingActivity.awaitingImport", {
                    count: run.unhandledRecordsCount,
                  })}
                </Typography>
              )}
              {run.importErrorCount > 0 && (
                <Alert severity="warning" sx={{ mt: 1 }}>
                  {translate("harvestingActivity.importErrors", {
                    count: run.importErrorCount,
                  })}
                </Alert>
              )}
              <Stack
                direction="row"
                sx={{
                  mt: 1,
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <Typography variant="caption" color="text.secondary">
                  {translate("harvestingActivity.started")}:{" "}
                  <DateField source="dateCreated" showTime emptyText="—" />
                </Typography>
                <Button
                  component={Link}
                  to={`/HarvestingJob/${run.id}/show`}
                  label="harvestingActivity.viewRun"
                />
              </Stack>
            </Box>
          </RecordContextProvider>
        );
      })}
    </Stack>
  );
};

const HarvestingActivityCard = () => {
  const service = useRecordContext();
  const operation = useOperation(
    "list_related_HarvestingJob_of_CatalogueService",
  );
  if (!service || !operation) return null;
  return (
    <ListGuesser
      resource="HarvestingJob"
      relatedResource={{ resource: "CatalogueService", id: service.id }}
      disableSyncWithLocation
      sort={{ field: "dateCreated", order: "DESC" }}
      perPage={3}
      actions={false}
      filters={undefined}
      aside={undefined}
      pagination={false}
      empty={false}
      component={HarvestingActivityCardBase}
      dataGridProps={{ component: HarvestingActivityList }}
      storeKey={`CatalogueService.${service.id}.HarvestingJob.activity`}
      refetchInterval={5000}
      queryOptions={{
        meta: {
          jsonApiParams: {
            "fields[HarvestingJob]":
              "id,phase,phase_label,progress,date_created,done_at,total_records,unhandled_records_count,import_error_count",
          },
        },
      }}
      defaultSelectedColumns={[
        "phase",
        "phaseLabel",
        "progress",
        "dateCreated",
        "doneAt",
        "totalRecords",
        "unhandledRecordsCount",
        "importErrorCount",
      ]}
    />
  );
};

export { HarvestingActivityList, HarvestingPhaseStepper };
export default HarvestingActivityCard;
