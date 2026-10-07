import { useRecordContext, useResourceContext } from "react-admin";
import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import UpdateJobsCardBase from "../../WebMapService/Show/Overview/UpdateJobs/UpdateJobsCardBase";
import UpdateJobsList from "../../WebMapService/Show/Overview/UpdateJobs/UpdateJobsList";

const ServiceUpdateJobsCard = ({ resource }: { resource: string }) => {
  const parentResource = useResourceContext();
  const record = useRecordContext();
  const queryOptions = {
    meta: {
      jsonApiParams: {
        include: "mappings",
      },
    },
  };
  const relatedResource = {
    resource: parentResource,
    id: record?.id,
  };
  return (
    <ListGuesser
      resource={resource}
      relatedResource={relatedResource}
      disableSyncWithLocation
      sort={{ field: "doneAt", order: "DESC" }}
      filter={{
        service: record?.id,
        status_code__ne: 4,
      }}
      queryOptions={
        parentResource !== "CatalogueService" ? queryOptions : undefined
      }
      perPage={5}
      refetchInterval={5_000}
      actions={false}
      filters={undefined}
      aside={undefined}
      pagination={false}
      component={UpdateJobsCardBase}
      storeKey={`_${resource}_overview_update_jobs`}
      dataGridProps={{
        component: UpdateJobsList,
      }}
      empty={false}
    />
  );
};

export default ServiceUpdateJobsCard;
