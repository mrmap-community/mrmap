import { type ListProps } from "react-admin";

import ListMetadataRecords, {
  MetadataExplorer,
} from "../Generic/Explorer/ListMetadataRecords";
import DatasetCoverageMap from "./DatasetCoverageMap";

export const DatasetExplorer = () => (
  <MetadataExplorer MapComponent={DatasetCoverageMap} />
);

const ListDatasetMetadataRecord = (props: Partial<ListProps>) => (
  <ListMetadataRecords
    {...props}
    resource="DatasetMetadataRecord"
    MapComponent={DatasetCoverageMap}
  />
);

export default ListDatasetMetadataRecord;
