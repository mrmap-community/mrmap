import { useFormContext, useWatch } from "react-hook-form";
import type { FieldDefinition } from "../../../../../../jsonapi/utils";
import { Alert, Button, Stack, Typography } from "@mui/material";
import { createElement, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  FilterForm,
  ListBase,
  Loading,
  type Identifier,
  useBasename,
  useGetList,
  useListContext,
  useRecordContext,
  useTranslate,
} from "react-admin";
import { useFilterInputForOperation } from "../../../../../../jsonapi/hooks/useFilterInputForOperation";
import FeatureGroupEditor from "../../../../../Input/FeatureGroupEditor";
import GeoJsonMap from "../../../../../MapContainer/GeoJsonMap";
import SimpleCard from "../../../../../MUI/SimpleCard";
import { getSpatialAccess } from "./spatialAccess";
import useCompleteList from "./useCompleteList";

const resource = "AllowedWebMapServiceOperation";
const operationId = `list_related_${resource}_of_WebMapService`;
const policyFilters = [
  { source: "access_group", label: "group" },
  { source: "access_user", label: "user" },
  { source: "operations__value", label: "operation" },
  { source: "secured_layers__id", label: "layer" },
];

const IdentityFilter = ({
  definition,
  alternativeSource,
  ...props
}: {
  definition: FieldDefinition;
  alternativeSource: string;
  source: string;
  label: string;
  alwaysOn: boolean;
}) => {
  const value = useWatch({ name: props.source });
  const { setValue } = useFormContext();
  useEffect(() => {
    if (value != null && value !== "")
      setValue(alternativeSource, null, { shouldDirty: true });
  }, [value, alternativeSource, setValue]);
  return createElement(definition.component, { ...definition.props, ...props });
};

const SpatialPolicyResult = ({ serviceId }: { serviceId: Identifier }) => {
  const translate = useTranslate();
  const {
    data = [],
    total,
    filterValues,
    isPending,
    isFetching,
    error,
    refetch,
  } = useListContext();
  // An empty filtered list means denied access only if the service has rules.
  const serviceRules = useGetList(resource, {
    pagination: { page: 1, perPage: 1 },
    meta: { relatedResource: { resource: "WebMapService", id: serviceId } },
  });
  const group = filterValues.access_group;
  const user = filterValues.access_user;
  const selected = [
    filterValues.operations__value,
    filterValues.secured_layers__id,
  ];
  const hasGroup = group != null && group !== "";
  const hasUser = user != null && user !== "";
  const ready =
    hasGroup !== hasUser &&
    selected.every((value) => value != null && value !== "");
  const overflow = total != null && total > data.length;
  // The map must include every matching rule, beyond the current list page.
  const complete = useCompleteList(resource, serviceId, {
    filter: filterValues,
    enabled: ready && overflow && !isFetching && !error,
  });
  const failed = error || serviceRules.error || (overflow && complete.error);
  const pending =
    isPending ||
    isFetching ||
    serviceRules.isPending ||
    (overflow &&
      (complete.isPending || complete.hasNextPage || complete.isFetching));
  if (failed)
    return (
      <Alert
        severity="error"
        action={
          <Button
            onClick={() => {
              void refetch();
              void serviceRules.refetch();
              if (overflow) void complete.refetch();
            }}
          >
            {translate("ra.action.retry")}
          </Button>
        }
      >
        {translate("spatialSecurity.loadError")}
      </Alert>
    );
  if (!ready)
    return <Alert severity="info">{translate("spatialSecurity.select")}</Alert>;
  if (pending) return <Loading />;
  const access = getSpatialAccess(
    overflow ? complete.records : data,
    hasUser ? undefined : String(group),
    String(selected[0]),
    String(selected[1]),
    serviceRules.total !== 0,
  );
  return (
    <Stack spacing={2}>
      <Alert severity={access.status === "denied" ? "warning" : "info"}>
        {translate(`spatialSecurity.${access.status}`)}
      </Alert>
      {access.status === "restricted" && (
        <>
          <GeoJsonMap id={`spatial-security-${serviceId}`}>
            <FeatureGroupEditor geoJson={access.areas} editable={false} />
          </GeoJsonMap>
          <Typography variant="caption">
            {translate("spatialSecurity.legend")}
          </Typography>
        </>
      )}
    </Stack>
  );
};

const SpatialPolicyTesterContent = ({
  serviceId,
}: {
  serviceId: Identifier;
}) => {
  const definitions = useFilterInputForOperation(operationId);
  const translate = useTranslate();
  const basename = useBasename();
  const filters = policyFilters.flatMap(({ source, label }) => {
    const definition = definitions.find(
      (field) => field.props.source === source,
    );
    return definition
      ? [
          createElement(
            label === "group" || label === "user"
              ? IdentityFilter
              : definition.component,
            {
              ...definition.props,
              ...((label === "group" || label === "user") && {
                definition,
                alternativeSource:
                  label === "group" ? "access_user" : "access_group",
              }),
              key: source,
              alwaysOn: true,
              label: `spatialSecurity.${label}`,
              ...(label === "layer" && {
                getListParams: {
                  meta: {
                    relatedResource: {
                      resource: "WebMapService",
                      id: serviceId,
                    },
                  },
                },
              }),
            },
          ),
        ]
      : [];
  });
  return (
    <SimpleCard
      title={translate("spatialSecurity.testerTitle")}
      subheader={translate("spatialSecurity.subtitle")}
      cardProps={{ sx: { width: "100%", border: 1, borderColor: "info.main" } }}
      footer={
        <Button component={Link} to={`${basename}/ProxySetting`}>
          {translate("serviceShow.proxy")}
        </Button>
      }
    >
      {filters.length !== policyFilters.length ? (
        <Alert severity="info">
          {translate("spatialSecurity.schemaUnavailable")}
        </Alert>
      ) : (
        <Stack spacing={2}>
          <FilterForm filters={filters} />
          <SpatialPolicyResult serviceId={serviceId} />
          <Typography variant="body2" color="text.secondary">
            {translate("spatialSecurity.note")}
          </Typography>
        </Stack>
      )}
    </SimpleCard>
  );
};

const SpatialPolicyTester = () => {
  const service = useRecordContext();
  return service ? (
    <ListBase
      key={service.id}
      resource={resource}
      perPage={100}
      sort={{ field: "id", order: "ASC" }}
      disableSyncWithLocation
      storeKey={false}
      queryOptions={{
        meta: {
          relatedResource: { resource: "WebMapService", id: service.id },
        },
      }}
    >
      <SpatialPolicyTesterContent serviceId={service.id} />
    </ListBase>
  ) : null;
};

export default SpatialPolicyTester;
