import { type ListProps, useResourceDefinition } from "react-admin";
import ListMetadataRecords from "../Generic/Explorer/ListMetadataRecords";

const ListServiceMetadataRecord = (props: Partial<ListProps>) => {
  const { hasShow } = useResourceDefinition({
    resource: "ServiceMetadataRecord",
  });
  return (
    <ListMetadataRecords
      {...props}
      resource="ServiceMetadataRecord"
      namespace="serviceMetadataExplorer"
      showDetails={!!hasShow}
    />
  );
};

export default ListServiceMetadataRecord;
