import { createElement, useCallback, useMemo, useState, type ReactNode } from "react";
import {
  BasenameContextProvider,
  BooleanField,
  Datagrid,
  DeleteButton,
  FunctionField,
  ReferenceField,
  ResourceContextProvider,
  SearchInput,
  WrapperField,
  useGetList,
  useNotify,
  useRecordContext,
  useRefresh,
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
import RecordRelationCreate from "./RecordRelationCreate";

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

// the same columns as the member of a response and of a write body, which
// json:api names in camelCase: `recordColumn` is what a filter asks with, this
// is what a declaration fills (#985)
const RECORD_SOURCES: Record<string, string> = {
  DatasetMetadataRecord: "datasetMetadata",
  ServiceMetadataRecord: "serviceMetadata",
};

// One group of the relations of a record: which column of the table its rows
// fill, how that column is asked for, and what the row asserts. `edge` and
// `column` are filled by the screen, which knows the language: the two column
// lists below are the mirror of the model and state no wording.
export interface RelationGroup {
  /** the member of a response which the rows of this group fill */
  source: string;
  /** the term the api declares to filter for that column */
  filter: string;
  /** the JSON:API type of the element or record the row names */
  resource: string;
  /** a row which couples two metadata records; absent means the element
   * coupling of `DESCRIBED_COLUMNS` (#985) */
  kind?: "element" | "record";
  /** for a pair row, which end of the coupling operates: the record the screen
   * shows (`own`) or the partner it names (`partner`). ISO serves the pair as
   * `srv:operatesOn` inside the operating record's document, so the sentence of
   * the group reads in that direction and differs between the two screens which
   * show the very same row (#985) */
  operator?: "own" | "partner";
  /** the sentence of the group, as an edge label and a heading */
  edge?: string;
  /** the same sentence as the heading of a table column */
  column?: string;
}

// the columns which hold a described element; the mirror of
// registry.models.metadata.MetadataRelation.DESCRIBED_OBJECT_FIELDS. The type of a
// relation IS which of these is filled - the model has no relation kind - so the
// groups of a record are read from the filled column of its own rows instead of
// being chosen by the kind of the record: what the two-way branch this replaced hid
// is a service record which describes a layer or a feature type (#1268).
// `source` names the relation in a response, `filter` the term the api declares.
const DESCRIBED_COLUMNS: RelationGroup[] = [
  { source: "layer", filter: "layer", resource: "Layer" },
  { source: "featureType", filter: "feature_type", resource: "FeatureType" },
  { source: "wms", filter: "wms", resource: "WebMapService" },
  { source: "wfs", filter: "wfs", resource: "WebFeatureService" },
  { source: "csw", filter: "csw", resource: "CatalogueService" },
];

// the OTHER kind of metadata record, which is the pair group of a record
// screen (#985). A pair row is the only row filling both record columns - no
// combination of VALID_RELATIONS fills an element beside both - so the
// screen's own column together with the partner column `__isnull: false`
// answers exactly its pair rows, from either side of the coupling.
const PARTNER_COLUMNS: Record<string, RelationGroup> = {
  DatasetMetadataRecord: {
    source: "serviceMetadata",
    filter: "service_metadata",
    resource: "ServiceMetadataRecord",
    kind: "record",
    operator: "partner",
  },
  ServiceMetadataRecord: {
    source: "datasetMetadata",
    filter: "dataset_metadata",
    resource: "DatasetMetadataRecord",
    kind: "record",
    operator: "own",
  },
};

// the four sentences of the pair row, keyed by the end of the coupling the
// screen is and by the shape of the assertion; a table instead of nested
// ternaries, because the four sentences differ ONLY in their key (#985)
const PAIR_SENTENCE_KEYS = {
  own: { edge: "operatesOnEdge", column: "operatesOnColumn" },
  partner: { edge: "operatedOnByEdge", column: "operatedOnByColumn" },
} as const;

export const recordColumn = (resource: string) => RECORD_COLUMNS[resource];

export const recordSource = (resource: string) => RECORD_SOURCES[resource];

export const partnerColumn = (resource: string) => PARTNER_COLUMNS[resource];

// every column a row of this screen can fill: the described elements and, for a
// kind with a column of its own, the other kind of record
export const relationGroups = (resource: string): RelationGroup[] => {
  const partner = PARTNER_COLUMNS[resource];
  return partner === undefined ? DESCRIBED_COLUMNS : [...DESCRIBED_COLUMNS, partner];
};

// the couplings a curator of this screen may declare, which is the matrix of D5
// of docs/metadata-identity.md: a dataset record is described by a layer or a
// feature type and coupled to one service record, a service record by any of the
// five elements and coupled to one dataset record. The api answers anything else
// with a 400; the screen offers only what the model can store (#985)
export const declarableGroups = (resource: string): RelationGroup[] => {
  const partner = PARTNER_COLUMNS[resource];
  if (partner === undefined) return [];
  if (resource === "DatasetMetadataRecord")
    return [
      ...DESCRIBED_COLUMNS.filter((group) =>
        ["layer", "featureType"].includes(group.source),
      ),
      partner,
    ];
  return [...DESCRIBED_COLUMNS, partner];
};

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
export const filledGroups = (
  relations: RaRecord[],
  groups: RelationGroup[] = DESCRIBED_COLUMNS,
) =>
  groups.filter((group) => relations.some((relation) => relation[group.source]));

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
  groups: RelationGroup[] = DESCRIBED_COLUMNS,
) => {
  const nodes: Node[] = [
    {
      id: "record",
      position: { x: 360, y: 0 },
      data: { label: record.title || record.id },
    },
  ];
  const edges: Edge[] = [];
  filledGroups(relations, groups).forEach((group, groupIndex) => {
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
        // describes that element, or that the service record operates on that
        // dataset - and where the coupling came from, instead of an
        // undirected "related" (#1268, #985)
        edges.push({
          id: `edge:${relation.id}`,
          source: id,
          target: "record",
          label: `${group.edge ?? describe(group.resource)} · ${choiceLabel(relation.origin, originChoices) ?? "—"}`,
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

// The row action of a relations table: only a row the curator declared is this
// endpoint's to take back — the api refuses a harvested coupling, because the
// document which declared it owns it (D7 of docs/metadata-identity.md) — so the
// screen offers nothing for those rows. Which row that is comes from the api as
// `isPublishable` instead of a copy of the backend's origin enum (#985).
// Exported for its spec: inside a table it reads the row's own context.
export const TakeBackButton = () => {
  const row = useRecordContext();
  const notify = useNotify();
  const refresh = useRefresh();
  if (!row?.isPublishable) return null;
  return (
    <DeleteButton
      // the take back rewrites the declaring record's document: an undoable
      // snackbar which promises to bring a deleted coupling back would promise
      // something the api never does
      mutationMode="pessimistic"
      label="recordShow.takeBack"
      confirmTitle="recordShow.takeBackConfirm"
      mutationOptions={{
        onSuccess: () => {
          notify("recordShow.takeBackDeleted", { type: "success" });
          // the row was published inside the declaring record's document, so
          // what changed is more than the list of rows: every query of the
          // screen goes with its own filter — the count of a facet, the rows of
          // a table, the page of the graph, the record itself — and all of them
          // are asked again (#985)
          refresh();
        },
        onError: () => notify("recordShow.takeBackFailed", { type: "error" }),
      }}
    />
  );
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
          {group.edge ?? describe(group.resource)}
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
  groups,
}: {
  filter: Record<string, unknown>;
  describe: (resource: string) => string;
  groups: RelationGroup[];
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
            describe,
            fields.find((field) => field.props.source === "origin")?.props
              .choices,
            translate("recordShow.harvestedThrough"),
            groups,
          )
        : { nodes: [], edges: [] },
    [record, data, describe, fields, translate, groups],
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

// The relations tab of a record. `readOnly` is what the record editor's pane
// states: relations are managed on the record's own page, and the editor shows
// them as the record answers them (#985).
const RecordRelations = ({ readOnly = false }: { readOnly?: boolean }) => {
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
  // what a relation of this screen asserts, in the words of the model: the
  // record describes the element whose column is filled, a pair of records
  // states that the service record operates on the dataset one, and the origin
  // says where the coupling came from. No relation kind is offered which the
  // model cannot store.
  const kindName = useCallback(
    (reference: string) =>
      translate(`resources.${reference}.name`, { smart_count: 1, _: reference }),
    [translate],
  );
  const describe = useCallback(
    (reference: string) =>
      translate("recordShow.describesEdge", { kind: kindName(reference) }),
    [translate, kindName],
  );
  // the sentence of a pair row: the row IS the same row on both screens, but the
  // document which publishes it is the operating record's, so the screen on the
  // operating end says "operates on" and the other end names its operator (#985)
  const pairSentence = useCallback(
    (group: RelationGroup, edge: boolean) => {
      const keys = PAIR_SENTENCE_KEYS[group.operator ?? "own"];
      return translate(`recordShow.${keys[edge ? "edge" : "column"]}`, {
        kind: kindName(group.resource),
      });
    },
    [translate, kindName],
  );
  // the groups of the screen with their sentences: the column lists mirror the
  // model and state no wording, so the labels are filled here (#985)
  const groups = useMemo<RelationGroup[]>(
    () =>
      relationGroups(resource ?? "").map((group) => ({
        ...group,
        edge:
          group.kind === "record"
            ? pairSentence(group, true)
            : describe(group.resource),
        column:
          group.kind === "record"
            ? pairSentence(group, false)
            : translate("recordShow.describesColumn", {
                kind: kindName(group.resource),
              }),
      })),
    [resource, translate, kindName, describe, pairSentence],
  );
  // the couplings this screen may declare, in the order the model can store
  // them and with the very same sentences the tables state — the dialog of the
  // declaration and the table of the row never say two different things (#985)
  const declarable = useMemo(() => {
    if (readOnly) return [];
    return declarableGroups(resource ?? "")
      .map((group) => groups.find((candidate) => candidate.source === group.source))
      .filter((group): group is RelationGroup => group !== undefined);
  }, [readOnly, resource, groups]);
  const catalogues = (
    <>
      <Typography variant="h6">
        {translate("recordShow.harvestedThrough")}
      </Typography>
      <ResourceContextProvider value="CatalogueService">
        <ListGuesser
          resource="CatalogueService"
          relatedResource={{ resource, id: record?.id }}
          defaultSelectedColumns={["title"]}
          disableSyncWithLocation
          storeKey={`${resource}.${record?.id}.catalogues`}
          rowActions={<span />}
          aside={undefined}
          dataGridProps={{ bulkActionButtons: false, rowClick: "show" }}
        />
      </ResourceContextProvider>
    </>
  );
  if (!record) return null;
  // a curator's screen states what it can declare, and does so before the
  // first row exists: the record which stores nothing yet is exactly the one
  // a coupling is worth declaring for (#985)
  const declare =
    declarable.length === 0 ? null : (
      <RecordRelationCreate
        ownColumn={recordSource(resource ?? "")}
        record={record}
        groups={declarable}
      />
    );
  // a kind without a column of its own has no MetadataRelation filter to ask: its
  // section is the catalogues it was harvested through and nothing else
  if (!column)
    return <Stack spacing={2} sx={{ minWidth: 0 }}>{catalogues}</Stack>;
  // a record which could have relations but stores none says so plainly, without
  // claiming that no relation could ever exist for it, and keeps showing the
  // catalogues it was harvested through: the origin of a record proves neither the
  // presence nor the absence of a coupling (#1268)
  if (isPending || total === 0)
    return (
      <Stack spacing={2} sx={{ minWidth: 0 }}>
        {total === 0 ? (
          <>
            <Alert severity="info">{translate("recordShow.noRelations")}</Alert>
            {declare}
          </>
        ) : (
          <Typography variant="body2" color="text.secondary">
            {translate("ra.message.loading")}
          </Typography>
        )}
        {catalogues}
      </Stack>
    );
  const shown = openedGroup
    ? groups.filter((group) => group.source === openedGroup)
    : groups;
  const facets = (onShowAll?: (group: RelationGroup) => void) => (
    <Stack direction="row" useFlexGap spacing={3} sx={{ flexWrap: "wrap" }}>
      {groups.map((group) => (
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
      <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: "wrap" }}>
        <ToggleButtonGroup
          exclusive
          value={view}
          onChange={(_, value) => {
            if (!value) return;
            // the switch by hand is the reader asking for every group again; only
            // the facet of the graph opens a single one
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
        {declare}
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {translate("recordShow.relationMeaning")}
      </Typography>
      {view === "graph" ? (
        <>
          {facets((group) => {
            setOpenedGroup(group.source);
            setView("tables");
          })}
          <RelationGraph
            filter={filter ?? {}}
            describe={describe}
            groups={groups}
          />
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
          {shown.map((group) => (
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
                        label={group.column}
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
                  // the search term of this endpoint searches the titles of the
                  // described elements; a pair row has no element and the model
                  // stores at most one pair of a kind per record, so the group
                  // of the pair asks nothing (#985)
                  additionalFilters={
                    group.kind === "record"
                      ? undefined
                      : [
                          {
                            component: SearchInput,
                            props: { source: "search", alwaysOn: true },
                          },
                        ]
                  }
                  rowActions={
                    readOnly ? (
                      <span />
                    ) : (
                      <WrapperField label={translate("ra.list.actions")}>
                        <TakeBackButton />
                      </WrapperField>
                    )
                  }
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
