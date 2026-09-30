import { useRecordContext, useResourceContext } from "react-admin";
import ListGuesser from "../../../../../../jsonapi/components/ListGuesser";
import MonitoringRunsCardBase from "./MonitoringRunsCardBase";
import MonitoringRunsList from "./MonitoringRunsList";

const MonitoringRunsCard = () => {
  const resource = useResourceContext();
  const nestedResource = "WebMapServiceMonitoringRun";
  const record = useRecordContext();
  const relatedResource = {
    resource: resource,
    id: record?.id,
  };
  return (
    <ListGuesser
      resource={nestedResource}
      relatedResource={relatedResource}
      disableSyncWithLocation
      sort={{ field: "dateDone", order: "DESC" }}
      perPage={5}
      actions={false}
      filters={undefined}
      aside={undefined}
      pagination={false}
      empty={false}
      component={MonitoringRunsCardBase}
      storeKey="wms_overview_monitoring_runs"
      defaultSelectedColumns={["id", "dateCreated", "dateDone", "status"]}
      dataGridProps={{
        component: MonitoringRunsList,
      }}
    />
  );
};

export default MonitoringRunsCard;
