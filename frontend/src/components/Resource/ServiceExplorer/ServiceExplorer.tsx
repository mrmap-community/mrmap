import { useState } from "react";
import {
  EditButton,
  ResourceContextProvider,
  SearchInput,
  ShowButton,
  useListContext,
  useTranslate,
} from "react-admin";

import { Button, Chip, Stack, Tab, Tabs } from "@mui/material";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import { useFieldsForOperation } from "../../../jsonapi/hooks/useFieldsForOperation";
import CustomListActions, {
  type CustomListActionsProps,
} from "../../Lists/CustomListActions";
import { HarvestButton } from "../CatalogueService/CatalogueServiceList";
import { ExplorerView } from "../Generic/Explorer/ExplorerView";
import WmsViewerButtons from "../WebMapService/Button/ListActions";

const protocols = ["WebMapService", "WebFeatureService", "CatalogueService"];
const ExplorerActions = (props: CustomListActionsProps) => (
  <CustomListActions {...props} isConfigureable={false} />
);

export const ServiceResults = ({ resource }: { resource: string }) => {
  const { filterValues, setFilters, displayedFilters } = useListContext();
  const translate = useTranslate();
  const fields = useFieldsForOperation({
    operationId: `list_${resource}`,
    forInput: false,
    ignoreId: false,
  });
  const choices = fields.find((field) => field.props.source === "version")
    ?.props.choices as { id: unknown; name: string }[] | undefined;
  return (
    <>
      {filterValues.bbox_lat_lon__intersects && (
        <Button
          onClick={() => {
            const { bbox_lat_lon__intersects: _, ...rest } = filterValues;
            setFilters(rest, displayedFilters);
          }}
        >
          {translate("serviceExplorer.clearArea")}
        </Button>
      )}
      {resource === "CatalogueService" && (
        <Chip label={translate("serviceExplorer.catalogueScope")} />
      )}
      <ExplorerView
        geometrySource="extent"
        namespace="serviceExplorer"
        sortFields={["title", "hits", "dateStamp"]}
        onSearchArea={(geometry) =>
          setFilters(
            { ...filterValues, bbox_lat_lon__intersects: geometry },
            displayedFilters,
          )
        }
        rowDetails={(record) => (
          <>
            <Chip
              size="small"
              label={translate(
                `serviceExplorer.${record.isActive ? "active" : "inactive"}`,
              )}
            />
            <Chip
              size="small"
              label={translate("serviceExplorer.hits", {
                count: record.hits ?? 0,
              })}
            />
            <Chip
              size="small"
              label={
                choices?.find((choice) => choice.id === record.version)?.name ??
                record.version
              }
            />
            {record.serviceContact?.name && (
              <Chip size="small" label={record.serviceContact.name} />
            )}
            <Chip
              size="small"
              label={translate(
                resource === "CatalogueService"
                  ? "serviceExplorer.records"
                  : "serviceExplorer.elements",
                { count: record.elementCount ?? 0 },
              )}
            />
            {resource !== "CatalogueService" && (
              <Chip
                size="small"
                label={translate(
                  `serviceExplorer.${record.isSpatialSecured ? "spatialSecured" : record.isSecured ? "secured" : "public"}`,
                )}
              />
            )}
          </>
        )}
        rowActions={(record) => (
          <>
            <ShowButton />
            {record.canEdit && <EditButton />}
            {resource === "WebMapService" && <WmsViewerButtons />}
            {resource === "CatalogueService" && <HarvestButton />}
          </>
        )}
      />
    </>
  );
};

const ServiceExplorer = () => {
  const translate = useTranslate();
  const [resource, setResource] = useState(protocols[0]);
  const fields =
    "id,title,abstract,extent,element_count,can_edit,is_active,hits,version,date_stamp,service_contact" +
    (resource === "CatalogueService"
      ? ",running_harvesting_job"
      : ",is_secured,is_spatial_secured,xml_backup_file,xml_backup_file_secured");
  return (
    <Stack spacing={2}>
      <Tabs
        value={resource}
        onChange={(_, value: string) => setResource(value)}
        aria-label={translate("serviceExplorer.protocol")}
      >
        {protocols.map((name, index) => (
          <Tab key={name} value={name} label={["WMS", "WFS", "CSW"][index]} />
        ))}
      </Tabs>
      <ResourceContextProvider value={resource}>
        <ListGuesser
          key={resource}
          resource={resource}
          disableSyncWithLocation
          filter={{ is_update_candidate: false }}
          perPage={10}
          sort={{ field: "title", order: "ASC" }}
          aside={false}
          additionalFilters={[
            {component: SearchInput, props:{source: "search", alwaysOn: true}}
          ]}
          ActionsComponent={ExplorerActions}
          queryOptions={{
            meta: {
              jsonApiParams: {
                [`fields[${resource}]`]: fields,
                include: "serviceContact",
                "fields[MetadataContact]": "id,name",
              },
            },
          }}
          empty={false}
          listContent={<ServiceResults resource={resource} />}
        />
      </ResourceContextProvider>
    </Stack>
  );
};

export default ServiceExplorer;
