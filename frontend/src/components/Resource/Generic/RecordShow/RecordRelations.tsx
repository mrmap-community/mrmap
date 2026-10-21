import { createElement, useMemo, useState } from "react";
import {
  BasenameContextProvider,
  BooleanField,
  Datagrid,
  FunctionField,
  ReferenceField,
  ResourceContextProvider,
  SearchInput,
  useGetList,
  useRecordContext,
  useResourceContext,
  useResourceDefinition,
  useTranslate,
  type RaRecord,
} from "react-admin";

import {
  Alert,
  Box,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";

import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import { choiceLabel } from "./RecordFields";

import "@xyflow/react/dist/style.css";

export const relationGroups = (resource: string) =>
  resource === "DatasetMetadataRecord"
    ? [
        { source: "layer", resource: "Layer" },
        { source: "featureType", resource: "FeatureType" },
        { source: "csw", resource: "CatalogueService" },
      ]
    : [
        { source: "wms", resource: "WebMapService" },
        { source: "wfs", resource: "WebFeatureService" },
        { source: "csw", resource: "CatalogueService" },
      ];

const TargetLink = ({
  source,
  reference,
}: {
  source: string;
  reference: string;
  label?: string;
}) => {
  const { hasShow } = useResourceDefinition({ resource: reference });
  return (
    <BasenameContextProvider basename="">
      <ReferenceField
        source={`${source}.id`}
        reference={reference}
        link={
          hasShow
            ? "show"
            : (record) =>
                `/${reference}?filter=${encodeURIComponent(JSON.stringify({ id: record.id }))}`
        }
      >
        <FunctionField
          render={(record) =>
            record.title || record.stringRepresentation || record.id
          }
        />
      </ReferenceField>
    </BasenameContextProvider>
  );
};

const RelationOrigin = ({ source }: { source: string; label?: string }) => {
  const fields = useFieldsForOperation({
    operationId: "retrieve_MetadataRelation",
    forInput: false,
  });
  const field = fields.find((candidate) => candidate.props.source === source);
  return field ? createElement(field.component, field.props) : null;
};

export const relationGraph = (
  record: RaRecord,
  relations: RaRecord[],
  groups: ReturnType<typeof relationGroups>,
  originChoices?: { id: unknown; name: string }[],
  harvestedLabel = "Harvested through",
) => {
  const nodes: Node[] = [
    {
      id: "record",
      position: { x: 360, y: 0 },
      data: { label: record.title || record.id },
    },
  ];
  const edges: Edge[] = [];
  groups.forEach((group, groupIndex) => {
    relations
      .filter((relation) => relation[group.source])
      .forEach((relation, index) => {
        const target = relation[group.source];
        const id = `${group.source}:${relation.id}`;
        nodes.push({
          id,
          position: { x: groupIndex * 360, y: 160 + index * 100 },
          data: {
            label:
              target.title ||
              target.stringRepresentation ||
              `${group.resource}: ${target.id}`,
          },
        });
        edges.push({
          id: `edge:${relation.id}`,
          source: id,
          target: "record",
          label: `${group.resource} · ${choiceLabel(relation.origin, originChoices) ?? "—"}`,
          data: { isInternal: relation.isInternal },
        });
      });
  });
  (record.harvestedThrough ?? [])
    .slice(0, Math.max(0, 100 - relations.length))
    .forEach((catalogue: RaRecord, index: number) => {
      const id = `harvested:${catalogue.id}`;
      nodes.push({
        id,
        position: { x: 1080, y: 160 + index * 100 },
        data: {
          label:
            catalogue.title || catalogue.stringRepresentation || catalogue.id,
        },
      });
      edges.push({
        id: `edge:${id}`,
        source: id,
        target: "record",
        label: harvestedLabel,
      });
    });
  return { nodes, edges };
};

const RelationGraph = ({
  filter,
}: {
  filter: Record<string, string | number>;
}) => {
  const record = useRecordContext();
  const resource = useResourceContext();
  const translate = useTranslate();
  const groups = useMemo(() => relationGroups(resource ?? ""), [resource]);
  const fields = useFieldsForOperation({
    operationId: "retrieve_MetadataRelation",
    forInput: false,
  });
  const { data, total, isPending, error } = useGetList("MetadataRelation", {
    filter,
    pagination: { page: 1, perPage: 100 },
    sort: { field: "id", order: "ASC" },
    meta: {
      jsonApiParams: {
        include: groups.map((group) => group.source).join(","),
        ...Object.fromEntries(
          groups.map((group) => [
            `fields[${group.resource}]`,
            "title,string_representation",
          ]),
        ),
      },
    },
  });
  const graph = useMemo(
    () =>
      record
        ? relationGraph(
            record,
            data ?? [],
            groups,
            fields.find((field) => field.props.source === "origin")?.props
              .choices,
            translate("recordShow.harvestedThrough"),
          )
        : { nodes: [], edges: [] },
    [record, data, groups, fields, translate],
  );
  if (error)
    return <Alert severity="error">{translate("recordShow.loadFailed")}</Alert>;
  if (isPending)
    return <Typography>{translate("ra.message.loading")}</Typography>;
  return (
    <Stack spacing={1}>
      {total != null &&
        total + (record?.harvestedThrough?.length ?? 0) > 100 && (
          <Alert severity="info">{translate("recordShow.graphLimit")}</Alert>
        )}
      <Box sx={{ width: "100%", height: 480, minWidth: 0 }}>
        <ReactFlow {...graph} fitView nodesDraggable={false}>
          <Controls />
          <Background />
        </ReactFlow>
      </Box>
    </Stack>
  );
};

const RecordRelations = () => {
  const resource = useResourceContext();
  const record = useRecordContext();
  const translate = useTranslate();
  const [view, setView] = useState("tables");
  if (!record) return null;
  const parentFilter = {
    [resource === "DatasetMetadataRecord"
      ? "dataset_metadata"
      : "service_metadata"]: record.id,
  };
  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      <ToggleButtonGroup
        exclusive
        value={view}
        onChange={(_, value) => {
          if (value) setView(value);
        }}
        aria-label={translate("recordShow.relationView")}
      >
        <ToggleButton value="tables">
          {translate("recordShow.tables")}
        </ToggleButton>
        <ToggleButton value="graph">
          {translate("recordShow.graph")}
        </ToggleButton>
      </ToggleButtonGroup>
      {view === "graph" ? (
        <RelationGraph filter={parentFilter} />
      ) : (
        relationGroups(resource ?? "").map((group) => (
          <Box key={group.source}>
            <Typography variant="h6">
              {translate(`resources.${group.resource}.name`, {
                smart_count: 2,
                _: group.resource,
              })}
            </Typography>
            <ResourceContextProvider value="MetadataRelation">
              <ListGuesser
                resource="MetadataRelation"
                filter={{
                  ...parentFilter,
                  [`${group.source === "featureType" ? "feature_type" : group.source}__isnull`]: false,
                }}
                listContent={
                  <Datagrid bulkActionButtons={false} rowClick={false}>
                    <TargetLink
                      source={group.source}
                      reference={group.resource}
                      label={translate(`resources.${group.resource}.name`, {
                        smart_count: 1,
                        _: group.resource,
                      })}
                    />
                    <RelationOrigin
                      source="origin"
                      label={translate("recordShow.linkOrigin")}
                    />
                    <BooleanField
                      source="isInternal"
                      label="recordShow.internal"
                    />
                  </Datagrid>
                }
                disableSyncWithLocation
                storeKey={`${resource}.${record.id}.${group.source}`}
                additionalFilters={[
                  {component: SearchInput, props:{source: "search", alwaysOn: true}}
                ]}
                rowActions={<span />}
                aside={undefined}
                dataGridProps={{ bulkActionButtons: false, rowClick: false }}
              />
            </ResourceContextProvider>
          </Box>
        ))
      )}
      <Typography variant="h6">
        {translate("recordShow.harvestedThrough")}
      </Typography>
      <ResourceContextProvider value="CatalogueService">
        <ListGuesser
          resource="CatalogueService"
          relatedResource={{ resource, id: record.id }}
          defaultSelectedColumns={["title"]}
          disableSyncWithLocation
          storeKey={`${resource}.${record.id}.catalogues`}
          rowActions={<span />}
          aside={undefined}
          dataGridProps={{ bulkActionButtons: false, rowClick: "show" }}
        />
      </ResourceContextProvider>
    </Stack>
  );
};

export default RecordRelations;
