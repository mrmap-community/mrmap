import { useRecordContext } from "react-admin";
import ListGuesser from "../../../../../../jsonapi/components/ListGuesser";
import UpdateJobsCardBase from "./UpdateJobsCardBase";
import UpdateJobsList from "./UpdateJobsList";

const UpdateJobsCard = () => {
  const nestedResource = "WebMapServiceUpdateJob";
  const record = useRecordContext();
  const queryOptions = {
    meta: {
      jsonApiParams: {
        include: "mappings",
      },
    },
  };
  return (
    <ListGuesser
      resource={nestedResource}
      disableSyncWithLocation
      sort={{ field: "doneAt", order: "DESC" }}
      filter={{
        service: record?.id,
        status_code__ne: 4,
      }}
      queryOptions={queryOptions}
      actions={false}
      filters={undefined}
      aside={undefined}
      pagination={false}
      component={UpdateJobsCardBase}
      storeKey="wms_overview_update_jobs"
      defaultSelectedColumns={["id", "dateCreated", "doneAt", "status"]}
      dataGridProps={{
        component: UpdateJobsList,
      }}
      empty={false}
    />
  );
};

export default UpdateJobsCard;
