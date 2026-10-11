import { useRecordContext, useResourceContext } from "react-admin";
import ListGuesser from "../../../../../../jsonapi/components/ListGuesser";
import MonitoringRunsCardBase from "./MonitoringRunsCardBase";
import MonitoringRunsList from "./MonitoringRunsList";

const MonitoringRunsCard = ({
  resource
}: { resource: string }) => {
  const parentResource = useResourceContext();
  const record = useRecordContext();
  const relatedResource = {
    resource: parentResource,
    id: record?.id,
  };
  return (
    <ListGuesser
      resource={resource}
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
      storeKey={`_${resource}_overview_monitoring_runs`}

      defaultSelectedColumns={["id", "dateCreated", "dateDone", "status"]}
      dataGridProps={{
        component: MonitoringRunsList,
      }}
    />
  );
};

export default MonitoringRunsCard;
