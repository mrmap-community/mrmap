import { createElement, useMemo, useState, type ReactNode } from "react";
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
  Button,
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

// the number of relations the graph draws: a display budget for the nodes, while
// the table of every group continues the same query server-side, so the end of a
// long group stays reachable instead of being lost behind the budget (#1268)
const GRAPH_LIMIT = 100;

// the column of MetadataRelation which holds the record itself, keyed by the kind
// of the record; the mirror of registry.models.metadata.MetadataRelation.RECORD_FIELDS.
// A record kind without a column of its own has no place in that table, so its screen
// asks no relation query at all (the application record names no element and no service)
const RECORD_COLUMNS: Record<string, string> = {
  DatasetMetadataRecord: "dataset_metadata",
  ServiceMetadataRecord: "service_metadata",
};

// the columns which hold a described element; the mirror of
// registry.models.metadata.MetadataRelation.DESCRIBED_OBJECT_FIELDS. The type of a
// relation IS which of these is filled - the model has no relation kind - so the
// groups of a record are read from the filled column of its own rows instead of
// being chosen by the kind of the record: what the two-way branch this replaced hid
// is a service record which describes a layer or a feature type (#1268).
// `source` names the relation in a response, `filter` the term the api declares.
const DESCRIBED_COLUMNS = [
  { source: "layer", filter: "layer", resource: "Layer" },
  { source: "featureType", filter: "feature_type", resource: "FeatureType" },
  { source: "wms", filter: "wms", resource: "WebMapService" },
  { source: "wfs", filter: "wfs", resource: "WebFeatureService" },
  { source: "csw", filter: "csw", resource: "CatalogueService" },
];

export type RelationGroup = (typeof DESCRIBED_COLUMNS)[number];

export const recordColumn = (resource: string) => RECORD_COLUMNS[resource];

// the query of one group: the relations of the record, narrowed to the column which
// is filled. The count of the group and its table answer the very same query, so
// what a facet counts is what its rows are (#1268)
export const groupFilter = (
  column: string,
  id: RaRecord["id"],
  group: RelationGroup,
) => ({ [column]: id, [`${group.filter}__isnull`]: false });

// the groups which are actually stored for a page of relations, in the order of the
// columns of the table; a column no row fills is no group of this record
export const filledGroups = (relations: RaRecord[]) =>
  DESCRIBED_COLUMNS.filter((group) =>
    relations.some((relation) => relation[group.source]),
  );

const TargetLink = ({
  source,
  reference,
  label,
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
        label={label}
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

const RelationOrigin = ({
  source,
  label,
}: {
  source: string;
  label?: string;
}) => {
  const fields = useFieldsForOperation({
    operationId: "retrieve_MetadataRelation",
    forInput: false,
  });
  const field = fields.find((candidate) => candidate.props.source === source);
  return field
    ? createElement(field.component, { ...field.props, label })
    : null;
};

export const relationGraph = (
  record: RaRecord,
  relations: RaRecord[],
  describe: (resource: string) => string = (resource) => resource,
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
  filledGroups(relations).forEach((group, groupIndex) => {
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
        // the edge names what the filled column asserts - that this record
        // describes that element - and where the coupling came from, instead of
        // an undirected "related" (#1268)
        edges.push({
          id: `edge:${relation.id}`,
          source: id,
          target: "record",
          label: `${describe(group.resource)} · ${choiceLabel(relation.origin, originChoices) ?? "—"}`,
          data: { isInternal: relation.isInternal },
        });
      });
  });
  (record.harvestedThrough ?? [])
    .slice(0, Math.max(0, GRAPH_LIMIT - relations.length))
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
      // a harvested catalogue is the provenance of the record, another fact than
      // the coupling above, and it is drawn as its own edge for exactly that reason
      edges.push({
        id: `edge:${id}`,
        source: id,
        target: "record",
        label: harvestedLabel,
      });
    });
  return { nodes, edges };
};

// One group of the relations of a record: the sentence the filled column tells,
// how many rows it has, and the way to all of them. The number comes from the
// server with the group's own filter, so it is the real total and not the length of
// the page the graph drew. A column no row fills renders nothing: nothing stored is
// never shown, and nothing absent is ever inferred (#1268).
const RelationGroupFacet = ({
  group,
  filter,
  describe,
  onShowAll,
  children,
}: {
  group: RelationGroup;
  filter: Record<string, unknown>;
  describe: (resource: string) => string;
  onShowAll?: () => void;
  children?: ReactNode;
}) => {
  const translate = useTranslate();
  const { total, isPending } = useGetList("MetadataRelation", {
    filter,
    pagination: { page: 1, perPage: 1 },
    sort: { field: "id", order: "ASC" },
    meta: { jsonApiParams: { "fields[MetadataRelation]": "id" } },
  });
  // a group appears once its column answered that a row fills it; a group which is
  // still being asked, and one counted empty, render nothing, so the screen never
  // shows a heading it has to take back and states no coupling which is not stored.
  // An answer without a count is not a zero: the group stays, only without a number.
  if (isPending || total === 0) return null;
  return (
    <Box>
      <Stack
        direction="row"
        useFlexGap
        spacing={1}
        sx={{ alignItems: "center", flexWrap: "wrap" }}
      >
        <Typography variant="h6" component={onShowAll ? "span" : "h3"}>
          {describe(group.resource)}
        </Typography>
        {total != null && (
          <Typography variant="body2" color="text.secondary">
            {translate("recordShow.groupCount", { smart_count: total })}
          </Typography>
        )}
        {onShowAll && (
          <Button size="small" onClick={onShowAll}>
            {translate("recordShow.showAllGroup")}
          </Button>
        )}
      </Stack>
      {children}
    </Box>
  );
};

const RelationGraph = ({
  filter,
  describe,
}: {
  filter: Record<string, unknown>;
  describe: (resource: string) => string;
}) => {
  const record = useRecordContext();
  const translate = useTranslate();
  const fields = useFieldsForOperation({
    operationId: "retrieve_MetadataRelation",
    forInput: false,
  });
  // the graph asks every column of the table at once: which of them a row fills is
  // what decides its groups, so the answer cannot be limited to the columns one
  // kind of record was assumed to use
  const { data, total, isPending, error } = useGetList("MetadataRelation", {
    filter,
    pagination: { page: 1, perPage: GRAPH_LIMIT },
    sort: { field: "id", order: "ASC" },
    meta: {
      jsonApiParams: {
        include: DESCRIBED_COLUMNS.map((group) => group.source).join(","),
        ...Object.fromEntries(
          DESCRIBED_COLUMNS.map((group) => [
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
            describe,
            fields.find((field) => field.props.source === "origin")?.props
              .choices,
            translate("recordShow.harvestedThrough"),
          )
        : { nodes: [], edges: [] },
    [record, data, describe, fields, translate],
  );
  if (error)
    return <Alert severity="error">{translate("recordShow.loadFailed")}</Alert>;
  if (isPending)
    return <Typography>{translate("ra.message.loading")}</Typography>;
  const drawn = graph.nodes.length - 1; // without the node of the record itself
  const stored =
    (total ?? 0) + (record?.harvestedThrough?.length ?? 0);
  return (
    <Stack spacing={1}>
      {stored > drawn && (
        <Alert severity="info">
          {translate("recordShow.graphLimit", {
            shown: drawn,
            total: stored,
          })}
        </Alert>
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
  // the group which was opened from the graph; the tables show it alone, because
  // its own server side query is what continues where the graph stopped
  const [openedGroup, setOpenedGroup] = useState<string | undefined>(undefined);
  const column = recordColumn(resource ?? "");
  const filter = column && record ? { [column]: record.id } : undefined;
  // how many relations are stored for this record at all, asked without includes
  // and without rows: it decides whether there is anything to group (#1268)
  const { total, isPending } = useGetList(
    "MetadataRelation",
    {
      filter: filter ?? {},
      pagination: { page: 1, perPage: 1 },
      sort: { field: "id", order: "ASC" },
      meta: { jsonApiParams: { "fields[MetadataRelation]": "id" } },
    },
    { enabled: filter !== undefined },
  );
  if (!record) return null;
  // what a relation of this screen asserts, in the words of the model: the record
  // describes the element whose column is filled, and the origin says where the
  // coupling came from. No relation kind is offered which the model cannot store.
  const kindName = (reference: string) =>
    translate(`resources.${reference}.name`, { smart_count: 1, _: reference });
  const describe = (reference: string) =>
    translate("recordShow.describesEdge", { kind: kindName(reference) });
  const catalogues = (
    <>
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
    </>
  );
  // a kind without a column of its own has no MetadataRelation filter to ask: its
  // section is the catalogues it was harvested through and nothing else
  if (!column) return <Stack spacing={2} sx={{ minWidth: 0 }}>{catalogues}</Stack>;
  // a record which could have relations but stores none says so plainly, without
  // claiming that no relation could ever exist for it, and keeps showing the
  // catalogues it was harvested through: the origin of a record proves neither the
  // presence nor the absence of a coupling (#1268)
  if (isPending || total === 0)
    return (
      <Stack spacing={2} sx={{ minWidth: 0 }}>
        {total === 0 ? (
          <Alert severity="info">{translate("recordShow.noRelations")}</Alert>
        ) : (
          <Typography variant="body2" color="text.secondary">
            {translate("ra.message.loading")}
          </Typography>
        )}
        {catalogues}
      </Stack>
    );
  const groups = openedGroup
    ? DESCRIBED_COLUMNS.filter((group) => group.source === openedGroup)
    : DESCRIBED_COLUMNS;
  const facets = (onShowAll?: (group: RelationGroup) => void) => (
    <Stack direction="row" useFlexGap spacing={3} sx={{ flexWrap: "wrap" }}>
      {DESCRIBED_COLUMNS.map((group) => (
        <Box key={group.source}>
          <RelationGroupFacet
            group={group}
            filter={groupFilter(column, record.id, group)}
            describe={describe}
            onShowAll={onShowAll ? () => onShowAll(group) : undefined}
          />
        </Box>
      ))}
    </Stack>
  );
  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      <ToggleButtonGroup
        exclusive
        value={view}
        onChange={(_, value) => {
          if (!value) return;
          // the switch by hand is the reader asking for every group again; only the
          // facet of the graph opens a single one
          setOpenedGroup(undefined);
          setView(value);
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
      <Typography variant="body2" color="text.secondary">
        {translate("recordShow.relationMeaning")}
      </Typography>
      {view === "graph" ? (
        <>
          {facets((group) => {
            setOpenedGroup(group.source);
            setView("tables");
          })}
          <RelationGraph filter={filter ?? {}} describe={describe} />
        </>
      ) : (
        <>
          {openedGroup && (
            <Box>
              <Button size="small" onClick={() => setOpenedGroup(undefined)}>
                {translate("recordShow.allGroups")}
              </Button>
            </Box>
          )}
          {groups.map((group) => (
            <RelationGroupFacet
              key={group.source}
              group={group}
              filter={groupFilter(column, record.id, group)}
              describe={describe}
            >
              <ResourceContextProvider value="MetadataRelation">
                <ListGuesser
                  resource="MetadataRelation"
                  filter={groupFilter(column, record.id, group)}
                  listContent={
                    <Datagrid bulkActionButtons={false} rowClick={false}>
                      <TargetLink
                        source={group.source}
                        reference={group.resource}
                        label={translate("recordShow.describesColumn", {
                          kind: kindName(group.resource),
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
            </RelationGroupFacet>
          ))}
        </>
      )}
      {catalogues}
    </Stack>
  );
};

export default RecordRelations;
