import type { CoverageMapProps } from "./CoverageMap";

import type { ComponentType, ReactNode } from "react";
import {
  type ListProps,
  type RaRecord,
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
import { MetadataFacets, MetadataIndicators } from "./MetadataIndicators";

const ExplorerActions = (props: CustomListActionsProps) => (
  <CustomListActions {...props} isConfigureable={false} />
);
interface MetadataExplorerProps {
  namespace?: string;
  MapComponent?: ComponentType<CoverageMapProps>;
  showDetails?: boolean;
  rowDetails?: (record: RaRecord) => ReactNode;
}

export const MetadataExplorer = ({
  namespace = "datasetExplorer",
  MapComponent,
  showDetails = true,
  rowDetails,
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
        rowDetails={rowDetails}
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
            "id,title,abstract,bounding_geometry,date_stamp,is_broken,insufficient_quality,licence",
        },
      },
    }}
    listContent={
      <>
        <MetadataFacets />
        <MetadataExplorer
          namespace={namespace}
          MapComponent={MapComponent}
          showDetails={showDetails}
          rowDetails={(record) => <MetadataIndicators record={record} />}
        />
      </>
    }
  />
);

export default ListMetadataRecords;
