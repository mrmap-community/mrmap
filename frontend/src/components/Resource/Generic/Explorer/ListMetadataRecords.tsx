import type { CoverageMapProps } from "./CoverageMap";

import type { ComponentType } from "react";
import {
  type ListProps,
  SearchInput,
  useListContext,
  useTranslate,
} from "react-admin";

import { Button } from "@mui/material";

import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import CustomListActions, {
  type CustomListActionsProps,
} from "../../../Lists/CustomListActions";
import { ExplorerView } from "./ExplorerView";

const ExplorerActions = (props: CustomListActionsProps) => (
  <CustomListActions {...props} isConfigureable={false} />
);
interface MetadataExplorerProps {
  namespace?: string;
  MapComponent?: ComponentType<CoverageMapProps>;
  showDetails?: boolean;
}

export const MetadataExplorer = ({
  namespace = "datasetExplorer",
  MapComponent,
  showDetails = true,
}: MetadataExplorerProps) => {
  const { filterValues, setFilters, displayedFilters } = useListContext();
  const translate = useTranslate();
  return (
    <>
      {filterValues?.bounding_geometry__intersects && (
        <Button
          onClick={() => {
            const { bounding_geometry__intersects: _, ...rest } = filterValues;
            setFilters(rest, displayedFilters);
          }}
        >
          {translate(`${namespace}.clearArea`)}
        </Button>
      )}
      <ExplorerView
        MapComponent={MapComponent}
        namespace={namespace}
        showDetails={showDetails}
        onSearchArea={(geometry) =>
          setFilters(
            { ...filterValues, bounding_geometry__intersects: geometry },
            displayedFilters,
          )
        }
      />
    </>
  );
};

const ListMetadataRecords = ({
  namespace,
  MapComponent,
  showDetails,
  ...props
}: Partial<ListProps> & MetadataExplorerProps & { resource: string }) => (
  <ListGuesser
    {...props}
    additionalFilters={[{component: SearchInput, props:{source: "search", alwaysOn: true}}]}
    perPage={10}
    sort={{ field: "title", order: "ASC" }}
    aside={false}
    ActionsComponent={ExplorerActions}
    queryOptions={{
      meta: {
        jsonApiParams: {
          [`fields[${props.resource}]`]:
            "id,title,abstract,bounding_geometry,date_stamp",
        },
      },
    }}
    listContent={
      <MetadataExplorer
        namespace={namespace}
        MapComponent={MapComponent}
        showDetails={showDetails}
      />
    }
  />
);

export default ListMetadataRecords;
