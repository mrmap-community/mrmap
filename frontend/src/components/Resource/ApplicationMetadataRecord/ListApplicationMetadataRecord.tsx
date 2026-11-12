import { type ListProps, useResourceDefinition } from "react-admin";

import ListMetadataRecords from "../Generic/Explorer/ListMetadataRecords";

const ListApplicationMetadataRecord = (props: Partial<ListProps>) => {
  const { hasShow } = useResourceDefinition({
    resource: "ApplicationMetadataRecord",
  });
  return (
    <ListMetadataRecords
      {...props}
      resource="ApplicationMetadataRecord"
      namespace="applicationMetadataExplorer"
      showDetails={!!hasShow}
    />
  );
};

export default ListApplicationMetadataRecord;
