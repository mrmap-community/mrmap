import { Stack } from "@mui/material";
import {
  Button,
  NumberField,
  SimpleShowLayout,
  useRecordContext,
  useTranslate,
} from "react-admin";
import { Link } from "react-router-dom";
import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import useOperation from "../../../../jsonapi/hooks/useOperation";
import SimpleCard from "../../../MUI/SimpleCard";
import ServiceOverview from "../../Generic/ServiceShow/ServiceOverview";
import ServiceUpdateJobsCard from "../../Generic/ServiceShow/ServiceUpdateJobsCard";
import MonitoringRunsCard from "../../WebMapService/Show/Overview/MonitoringRuns/MonitoringRunsCard";
import HarvestingDailyStatsChart from "../HarvestingDailyStatsChart";

function ActivityCard({
  resource,
  title,
  columns,
}: {
  resource: string;
  title: string;
  columns: string[];
}) {
  const record = useRecordContext();
  const translate = useTranslate();
  const operation = useOperation(
    `list_related_${resource}_of_CatalogueService`,
  );
  if (!record || !operation) return null;
  const path = `/CatalogueService/${record.id}/show/${resource}`;
  return (
    <SimpleCard
      title={translate(title)}
      cardProps={{ variant: "outlined", sx: { width: "100%", minWidth: 0 } }}
      footer={
        <Button component={Link} to={path} label="serviceShow.configure" />
      }
    >
      <Stack spacing={2}>
        {resource === "HarvestingJob" && (
          <>
            <SimpleShowLayout>
              <NumberField source="harvestedDatasetCount" />
              <NumberField source="harvestedServiceCount" />
              <NumberField source="harvestedTotalCount" />
            </SimpleShowLayout>
            <HarvestingDailyStatsChart
              resource="HarvestedMetadataRelation"
              filter={{ service: record.id }}
            />
          </>
        )}
        <ListGuesser
          resource={resource}
          relatedResource={{ resource: "CatalogueService", id: record.id }}
          defaultSelectedColumns={columns}
          perPage={5}
          sort={{ field: "id", order: "DESC" }}
          disableSyncWithLocation
          storeKey={`CatalogueService.${record.id}.${resource}.overview`}
          actions={false}
          filters={undefined}
          aside={undefined}
          exporter={false}
          refetchInterval={resource === "HarvestingJob" ? 20000 : false}
          rowActions={<></>}
          dataGridProps={{ rowClick: false, bulkActionButtons: false }}
          empty={<span>{translate("serviceShow.empty")}</span>}
        />
      </Stack>
    </SimpleCard>
  );
}

export default function Overview() {
  return (
    <ServiceOverview protocol="CSW">
   
      <ServiceUpdateJobsCard resource="CatalogueServiceUpdateJob" />
      <MonitoringRunsCard resource="CatalogueServiceMonitoringRun" />
    
      <ActivityCard
        resource="HarvestingJob"
        title="serviceShow.harvesting"
        columns={["phase", "progress", "createdAt", "doneAt"]}
      />
      <ActivityCard
        resource="PeriodicHarvestingJob"
        title="serviceShow.schedules"
        columns={["enabled", "scheduling", "timeUntilNextRun"]}
      />
    </ServiceOverview>
  );
}
