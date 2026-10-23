import type { Feature } from "geojson";

import type { ReactNode } from "react";
import { Link, Loading, ResourceContextProvider, type RaRecord, useGetMany, useGetOne, useResourceDefinition, useTranslate } from "react-admin";

import { Alert, Button, Chip, Divider, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";

import FeatureGroupEditor from "../../../Input/FeatureGroupEditor";
import GeoJsonMap from "../../../MapContainer/GeoJsonMap";
import { getCoverageBounds } from "../../DatasetMetadataRecord/coverage";
import { IncludedRecordFields } from "../RecordShow/RecordFields";

// Expand the relationships needed to display the selected element's details.
const INCLUDE_OF_RESOURCE: Record<string, string> = {
  Layer: "styles,referenceSystems,timeExtents",
  FeatureType: "referenceSystems,defaultReferenceSystem,outputFormats",
};

const relatedRecords = (value: unknown): RaRecord[] =>
  Array.isArray(value) ? (value as RaRecord[]) : [];

const readableName = (item: RaRecord): string =>
  (item.stringRepresentation as string) ??
  (item.name as string) ??
  (item.title as string) ??
  `#${String(item.id)}`;

const Chips = ({ items }: { items: RaRecord[] }) => {
  const translate = useTranslate();
  if (items.length === 0)
    return <Typography component="span">{translate("layerInspection.none")}</Typography>;
  return (
    <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 0.5 }}>
      {items.map((item) => (
        <Chip key={String(item.id)} size="small" variant="outlined" label={readableName(item)} />
      ))}
    </Stack>
  );
};

/** A parsed boolean answers yes or no; an absent one stays unknown. */
const TriState = ({ value, label }: { value: unknown; label?: string }) => {
  const translate = useTranslate();
  const state = value === true ? "yes" : value === false ? "no" : "unknown";
  return (
    <Chip
      size="small"
      color={state === "yes" ? "success" : state === "no" ? "default" : "warning"}
      label={label ? `${label}: ${translate(`layerInspection.${state}`)}` : translate(`layerInspection.${state}`)}
    />
  );
};

const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <Stack spacing={0.5}>
    <Typography variant="overline" color="text.secondary">
      {title}
    </Typography>
    {children}
  </Stack>
);

export interface ElementInspectionProps {
  resource: "Layer" | "FeatureType";
  id?: RaRecord["id"];
  serviceResource: "WebMapService" | "WebFeatureService";
  serviceId?: RaRecord["id"];
  /** Preview destination of the owning service, e.g. the map viewer button. */
  previewAction?: ReactNode;
}

/**
 * Read-oriented inspection of one WMS layer or WFS feature type: coverage,
 * reference systems and time extents, the capabilities constraints exposed
 * for the element type, and destinations to related metadata, access rules
 * and the authorized editor. It states what the api answers; an absent value
 * is presented as not exposed, never as a passed check.
 */
const ElementInspection = ({
  resource,
  id,
  serviceResource,
  serviceId,
  previewAction,
}: ElementInspectionProps) => {
  const translate = useTranslate();
  const message = (key: string) => translate(`layerInspection.${key}`);
  const { hasEdit } = useResourceDefinition({ resource });

  const { data: record, isPending, error, refetch } = useGetOne(
    resource,
    {
      id: id as string,
      meta: { jsonApiParams: { include: INCLUDE_OF_RESOURCE[resource] } },
    },
    {
      enabled: id !== undefined && id !== null,
    },
  );

  const metadataIds =
    resource === "Layer"
      ? relatedRecords(record?.datasetMetadata).map((item) => item.id)
      : [];
  const { data: metadataRecords } = useGetMany("DatasetMetadataRecord", {
    ids: metadataIds,
    meta: { jsonApiParams: { "fields[DatasetMetadataRecord]": "id,string_representation" } },
  });

  if (id === undefined || id === null)
    return <Typography color="text.secondary">{message("select")}</Typography>;
  if (error)
    return (
      <Alert
        severity="error"
        action={
          <Button onClick={() => void refetch()}>{translate("ra.action.retry")}</Button>
        }
      >
        {message("loadError")}
      </Alert>
    );
  if (isPending || record === undefined) return <Loading />;

  const geometry = (record.bboxLatLon ?? record.bbox) as Feature["geometry"] | string | undefined;
  const coverage =
    typeof geometry === "object" && getCoverageBounds(geometry) ? geometry : undefined;
  const isLayer = resource === "Layer";
  const referenceSystems = relatedRecords(record.referenceSystems);
  const defaultReferenceSystem = record.defaultReferenceSystem as RaRecord | null | undefined;
  const availableReferenceSystems = !isLayer && defaultReferenceSystem
    ? [defaultReferenceSystem, ...referenceSystems.filter((item) => String(item.id) !== String(defaultReferenceSystem.id))]
    : referenceSystems;
  const ruleResource = isLayer
    ? "AllowedWebMapServiceOperation"
    : "AllowedWebFeatureServiceOperation";
  const describe = record.describeFeatureTypeDocument as string | undefined;

  return (
    <ResourceContextProvider value={resource}>
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
          <Typography variant="h6" component="h3">
            {readableName(record)}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ ml: "auto" }}>
            {previewAction}
            {hasEdit && (
              // react-admin gates the editor itself; it is offered when permitted
              <Button size="small" component={Link} to={`/${resource}/${String(id)}/edit`}>
                {message("edit")}
              </Button>
            )}
          </Stack>
        </Stack>
        {record.abstract ? (
          <Typography variant="body2">{record.abstract as string}</Typography>
        ) : (
          <Typography variant="body2" color="text.secondary">
            {message("noAbstract")}
          </Typography>
        )}
        <Divider />
        <Section title={message("coverage")}>
          {coverage ? (
            <GeoJsonMap id={`${resource}-${String(id)}-coverage`}>
              <FeatureGroupEditor
                geoJson={{ type: "Feature", properties: {}, geometry: coverage } as never}
                editable={false}
              />
            </GeoJsonMap>
          ) : (
            <Alert severity="info">
              {isLayer ? message("noCoverage") : message("noFeatureTypeCoverage")}
            </Alert>
          )}
        </Section>
        <Section title={message("referenceSystems")}>
          <Chips items={availableReferenceSystems} />
        </Section>
        {isLayer && (
          <Section title={message("time")}>
            {relatedRecords(record.timeExtents).length ? (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {["begin", "end", "resolution"].map((source) => (
                        <TableCell key={source}>{message(source)}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {relatedRecords(record.timeExtents).map((extent) => (
                      <TableRow key={String(extent.id)}>
                        {["begin", "end", "resolution"].map((source) => (
                          <TableCell key={source}>
                            <IncludedRecordFields
                              resource="TimeExtent"
                              record={extent}
                              sources={[source]}
                            />
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Typography color="text.secondary">{message("noTime")}</Typography>
            )}
          </Section>
        )}
        {isLayer ? (
          <Section title={message("rendering")}>
            <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1 }}>
              <Chip size="small" label={`${message("queryable")}:`} variant="outlined" />
              <TriState value={record.isQueryable} />
              <Chip size="small" label={`${message("opaque")}:`} variant="outlined" />
              <TriState value={record.isOpaque} />
              <Chip size="small" label={`${message("cascaded")}:`} variant="outlined" />
              <TriState value={record.isCascaded} />
              <Chip
                size="small"
                variant="outlined"
                label={`${message("scaleLimits")}: ${
                  record.scaleMin != null || record.scaleMax != null
                    ? `${String(record.scaleMin ?? "-")} : ${String(record.scaleMax ?? "-")}`
                    : message("unknown")
                }`}
              />
            </Stack>
            <Chips items={relatedRecords(record.styles)} />
          </Section>
        ) : (
          <Section title={message("formats")}>
            <Chips items={relatedRecords(record.outputFormats)} />
            {describe ? (
              <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                {describe.slice(0, 500)}
                {describe.length > 500 ? " …" : ""}
              </Typography>
            ) : (
              <Alert severity="info">{message("noDescription")}</Alert>
            )}
          </Section>
        )}
        {isLayer && relatedRecords(metadataRecords ?? []).length > 0 && (
          <Section title={message("metadata")}>
            <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 0.5 }}>
              {relatedRecords(metadataRecords).map((item) => (
                <Button
                  key={String(item.id)}
                  size="small"
                  component={Link}
                  to={`/DatasetMetadataRecord/${String(item.id)}/show`}
                >
                  {readableName(item)}
                </Button>
              ))}
            </Stack>
          </Section>
        )}
        <Section title={message("access")}>
          <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", alignItems: "center", gap: 1 }}>
            <TriState value={record.isSecured} label={message("secured")} />
            <TriState value={record.isSpatialSecured} label={message("spatialSecured")} />
            {serviceId !== undefined && serviceId !== null && (
              <Button
                size="small"
                component={Link}
                to={`/${serviceResource}/${String(serviceId)}/show/${ruleResource}`}
              >
                {message("rules")}
              </Button>
            )}
          </Stack>
        </Section>
      </Stack>
    </ResourceContextProvider>
  );
};

export default ElementInspection;
