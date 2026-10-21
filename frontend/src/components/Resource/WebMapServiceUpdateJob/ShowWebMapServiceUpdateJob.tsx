import { useCallback, useMemo, useState } from "react";
import {
  type RaRecord,
  type ShowProps,
  Show,
  useCreatePath,
  useGetOne,
  useRecordContext,
  useNotify,
  useShowContext,
  useTranslate,
  Link,
  Loading,
} from "react-admin";

import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import {
  Alert,
  Box,
  Breadcrumbs,
  Chip,
  Divider,
  LinearProgress,
  List,
  ListItemButton,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

import { useQueryParam } from "../../utils";
import {
  type ServiceUpdateConfig,
  wmsUpdateConfig,
} from "../Generic/Update/serviceUpdateConfig";
import WmsTreeView from "../WebMapService/TreeView/WmsTreeView";
import CompletedUpdateJob from "./CompletedUpdateJob";
import { EditLayerMapping } from "./EditLayerMapping";

const label = (record?: RaRecord) =>
  record?.title ??
  record?.identifier ??
  record?.stringRepresentation ??
  record?.id ??
  "—";
const changeType = (mapping: RaRecord, config: ServiceUpdateConfig) =>
  !mapping[config.oldElement]
    ? "added"
    : !mapping[config.newElement]
      ? "removed"
      : mapping.delta?.length
        ? "modified"
        : config.hasTree
          ? "unchanged"
          : "mapped";
const panelSx = {
  p: 2.5,
  border: 1,
  borderColor: "divider",
  borderRadius: 2,
  minWidth: 0,
};

const LayerComparison = ({
  layer,
  mapping,
  side,
  config,
}: {
  config: ServiceUpdateConfig;
  layer?: RaRecord;
  mapping: RaRecord;
  side: "old" | "new";
}) => {
  const translate = useTranslate();
  const fields = [
    { field: "title", value: layer?.title },
    { field: "identifier", value: layer?.identifier },
    ...(!config.hasTree ? [{ field: "abstract", value: layer?.abstract }] : []),
    ...(mapping.delta ?? [])
      .filter((delta: { field: string }) => delta.field !== "title")
      .map((delta: { field: string; old: unknown; new: unknown }) => ({
        field: delta.field,
        value: delta[side],
      })),
  ];
  return (
    <Box sx={{ ...panelSx, bgcolor: "action.hover", flex: 1 }}>
      <Typography variant="subtitle2" sx={{ mb: 2 }}>
        {translate(`updateReview.${side === "old" ? "current" : "incoming"}`)}
      </Typography>
      {layer ? (
        <Stack spacing={1.5}>
          {fields.map(({ field, value }) => (
            <Box key={field}>
              <Typography variant="caption" color="text.secondary">
                {translate(
                  `resources.${config.elementResource}.fields.${field}`,
                  { _: field },
                )}
              </Typography>
              <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                {value == null ? "—" : String(value)}
              </Typography>
            </Box>
          ))}
        </Stack>
      ) : (
        <Stack
          spacing={1}
          sx={{ py: 3, alignItems: "center", color: "text.secondary" }}
        >
          <DescriptionOutlinedIcon fontSize="large" />
          <Typography variant="body2">
            {translate(
              config.hasTree
                ? "updateReview.noMatch"
                : "wfsUpdateReview.noMatch",
            )}
          </Typography>
        </Stack>
      )}
    </Box>
  );
};

const ServiceUpdateJobCard = ({ config }: { config: ServiceUpdateConfig }) => {
  const job = useRecordContext();
  const { refetch } = useShowContext();
  const translate = useTranslate();
  const notify = useNotify();
  const createPath = useCreatePath();
  const [selectedLayer, setSelectedLayer] = useQueryParam(config.selectedParam);
  const [search, setSearch] = useState("");
  const [treeSearch, setTreeSearch] = useState("");
  const [filter, setFilter] = useState("pending");
  const [expandedItems, setExpandedItems] = useState<string[]>([]);
  const message = (key: string) =>
    translate(`${config.hasTree ? "updateReview" : "wfsUpdateReview"}.${key}`);
  const meta = useMemo(
    () => ({
      jsonApiParams: config.hasTree
        ? {
            include: "layers",
            "fields[Layer]":
              "mptt_lft,mptt_rgt,mptt_depth,title,identifier,string_representation",
            "fields[WebMapService]": "title,layers",
          }
        : { include: "featuretypes" },
    }),
    [config],
  );
  const finished = Boolean(job?.doneAt) && [0, 3, 5].includes(job?.statusCode);
  const candidateId = finished ? undefined : job?.updateCandidate?.id;
  const serviceId = job?.service?.id;
  const candidateQuery = useGetOne(
    config.serviceResource,
    { id: candidateId, meta },
    { enabled: candidateId != null },
  );
  const currentQuery = useGetOne(
    config.serviceResource,
    { id: serviceId, meta },
    { enabled: serviceId != null && !finished },
  );
  const newLayers: RaRecord[] = candidateQuery.data?.[config.elements] ?? [];
  const oldLayers: RaRecord[] = currentQuery.data?.[config.elements] ?? [];
  const mappings: RaRecord[] = job?.mappings ?? [];
  const pending = mappings.filter((mapping) => !mapping.isConfirmed);
  const resolved = mappings.length - pending.length;
  const progress = mappings.length ? (resolved / mappings.length) * 100 : 0;
  const newById = useMemo(
    () => new Map(newLayers.map((layer) => [String(layer.id), layer])),
    [newLayers],
  );
  const oldById = useMemo(
    () => new Map(oldLayers.map((layer) => [String(layer.id), layer])),
    [oldLayers],
  );
  const getLayer = (mapping: RaRecord, side: "old" | "new") => {
    const reference =
      side === "old" ? mapping[config.oldElement] : mapping[config.newElement];
    return (
      (side === "old" ? oldById : newById).get(String(reference?.id)) ??
      reference
    );
  };
  const visibleMappings = mappings.filter(
    (mapping) =>
      (filter === "all" ||
        (filter === "pending"
          ? !mapping.isConfirmed
          : changeType(mapping, config) === filter)) &&
      String(label(getLayer(mapping, "new") ?? getLayer(mapping, "old")))
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const selectedMapping = selectedLayer
    ? mappings.find(
        (mapping) =>
          String(
            mapping[config.newElement]?.id ?? mapping[config.oldElement]?.id,
          ) === selectedLayer,
      )
    : visibleMappings[0];
  const selectedNode = selectedLayer
    ? newById.get(selectedLayer)
    : selectedMapping && getLayer(selectedMapping, "new");
  const matchingLayers = newLayers.filter(
    (layer) =>
      String(layer.id) === String(selectedNode?.id) ||
      String(label(layer)).toLowerCase().includes(treeSearch.toLowerCase()),
  );
  const expandedAncestors = newLayers
    .filter(
      (layer) =>
        layer.mpttLft === 1 ||
        (selectedNode &&
          layer.mpttLft < selectedNode.mpttLft &&
          layer.mpttRgt > selectedNode.mpttRgt) ||
        (treeSearch &&
          matchingLayers.some(
            (match) =>
              layer.mpttLft < match.mpttLft && layer.mpttRgt > match.mpttRgt,
          )),
    )
    .map((layer) => String(layer.id));
  const getLayerProps = useCallback(
    (layer: RaRecord) => {
      const mapping = mappings.find(
        (item) => String(item[config.newElement]?.id) === String(layer.id),
      );
      const visible =
        !treeSearch ||
        matchingLayers.some(
          (match) =>
            match.id === layer.id ||
            (layer.mpttLft < match.mpttLft && layer.mpttRgt > match.mpttRgt),
        );
      return {
        itemId: String(layer.id),
        label: (
          <Typography
            variant="body2"
            sx={{ py: 0.5, overflowWrap: "anywhere" }}
            color={
              mapping && !mapping[config.oldElement]
                ? "success.main"
                : "text.primary"
            }
          >
            {label(layer)}
          </Typography>
        ),
        sx: { display: visible ? undefined : "none" },
      };
    },
    [mappings, treeSearch, matchingLayers, config],
  );
  if (!job) return null;
  if (finished) return <CompletedUpdateJob job={job} config={config} />;
  const loading =
    (candidateId != null && candidateQuery.isPending) ||
    (serviceId != null && currentQuery.isPending);
  const error = candidateQuery.error || currentQuery.error;
  return (
    <Stack
      spacing={3}
      sx={{ p: { xs: 1, md: 3 }, bgcolor: "background.default" }}
    >
      <Breadcrumbs>
        <Link
          to={createPath({
            resource: config.serviceResource,
            id: serviceId,
            type: "show",
          })}
        >
          {label(currentQuery.data ?? job.service)}
        </Link>
        <Typography variant="body2">
          {translate("updateReview.job", { id: job.id })}
        </Typography>
      </Breadcrumbs>
      <Box>
        <Stack
          direction="row"
          spacing={2}
          sx={{ flexWrap: "wrap", alignItems: "center" }}
        >
          <Typography variant="h4" sx={{ fontWeight: 600 }}>
            {translate("updateReview.title")}
          </Typography>
          <Chip
            size="small"
            color={pending.length ? "warning" : "success"}
            label={translate(
              pending.length
                ? "updateReview.needsReview"
                : "updateReview.resolved",
            )}
          />
        </Stack>
        <Typography variant="h6" sx={{ mt: 1 }}>
          {label(currentQuery.data ?? job.service)}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {translate("updateReview.subtitle")}
        </Typography>
      </Box>
      <Paper variant="outlined" sx={panelSx}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={3}

          sx={{ alignItems: { sm: "center" } }}
        >
          <Box sx={{ minWidth: 200 }}>
            <Typography sx={{ fontWeight: 600 }}>
              {translate("updateReview.remaining", { count: pending.length })}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {translate("updateReview.progress", {
                resolved,
                total: mappings.length,
              })}
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={progress}
            sx={{ flex: 1, minWidth: 100, height: 8, borderRadius: 4 }}
          />
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {Math.round(progress)}%
          </Typography>
        </Stack>
      </Paper>
      {error && <Alert severity="error">{message("loadError")}</Alert>}
      {loading && !error ? (
        <Loading />
      ) : !error ? (
        <Box
          sx={{
            display: "grid",
            gap: 2,
            alignItems: "start",
            gridTemplateColumns: {
              xs: "minmax(0, 1fr)",
              md: "260px minmax(0, 1fr)",
              lg: "260px 340px minmax(0, 1fr)",
            },
          }}
        >
          <Paper variant="outlined" sx={panelSx}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
              {message("tree")}
            </Typography>
            <TextField
              size="small"
              fullWidth
              label={message("findLayer")}
              value={treeSearch}
              onChange={(event) => setTreeSearch(event.target.value)}
              sx={{ mb: 2 }}
            />
            {config.hasTree && candidateQuery.data && (
              <WmsTreeView
                sx={{
                  maxHeight: "min(60vh, 640px)",
                  overflowY: "auto",
                  overscrollBehavior: "contain",
                }}
                record={candidateQuery.data}
                getLayerProps={getLayerProps}
                focusSelectedLayer
                selectedItems={
                  selectedMapping?.[config.newElement]
                    ? String(selectedMapping[config.newElement].id)
                    : (selectedLayer ?? null)
                }
                expandedItems={[
                  ...new Set([...expandedItems, ...expandedAncestors]),
                ]}
                onExpandedItemsChange={(_event: unknown, items: string[]) =>
                  setExpandedItems(items)
                }
              />
            )}
            {!config.hasTree && (
              <List aria-label={message("tree")} disablePadding>
                {matchingLayers.map((element) => (
                  <ListItemButton
                    key={element.id}
                    selected={String(element.id) === selectedLayer}
                    onClick={() => setSelectedLayer(String(element.id))}
                  >
                    <Typography variant="body2">{label(element)}</Typography>
                  </ListItemButton>
                ))}
              </List>
            )}
          </Paper>
          <Paper variant="outlined" sx={panelSx}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
              {translate("updateReview.changes")}
            </Typography>
            <Stack direction="row" sx={{ mb: 2, flexWrap: "wrap", gap: 1 }}>
              {(config.hasTree
                ? ["pending", "all", "added", "modified"]
                : ["pending", "all", "added"]
              ).map((value) => (
                <Chip
                  key={value}
                  size="small"
                  label={message(value)}
                  color={filter === value ? "primary" : "default"}
                  variant={filter === value ? "filled" : "outlined"}
                  onClick={() => setFilter(value)}
                />
              ))}
            </Stack>
            <TextField
              size="small"
              fullWidth
              label={translate("updateReview.searchChanges")}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <List
              aria-label={translate("updateReview.changes")}
              disablePadding
              sx={{ mt: 2 }}
            >
              {visibleMappings.map((mapping) => (
                <ListItemButton
                  key={mapping.id}
                  selected={selectedMapping?.id === mapping.id}
                  onClick={() =>
                    setSelectedLayer(
                      String(
                        mapping[config.newElement]?.id ??
                          mapping[config.oldElement]?.id,
                      ),
                    )
                  }
                  sx={{
                    border: 1,
                    borderColor:
                      selectedMapping?.id === mapping.id
                        ? "primary.main"
                        : "divider",
                    borderRadius: 1,
                    mb: 1.5,
                    p: 2,
                  }}
                >
                  <Stack spacing={1} sx={{ minWidth: 0 }}>
                    <Typography
                      variant="body2"

                      sx={{ fontWeight: 600, overflowWrap: "anywhere" }}
                    >
                      {label(
                        getLayer(mapping, "new") ?? getLayer(mapping, "old"),
                      )}
                    </Typography>
                    <Stack direction="row" spacing={1}>
                      <Chip
                        size="small"
                        variant="outlined"
                        color={
                          changeType(mapping, config) === "added"
                            ? "success"
                            : "info"
                        }
                        label={message(changeType(mapping, config))}
                      />
                      <Chip
                        size="small"
                        color={mapping.isConfirmed ? "success" : "warning"}
                        label={translate(
                          mapping.isConfirmed
                            ? "updateReview.confirmed"
                            : "updateReview.pending",
                        )}
                      />
                    </Stack>
                  </Stack>
                </ListItemButton>
              ))}
            </List>
            {!visibleMappings.length && (
              <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                {translate("updateReview.noChanges")}
              </Typography>
            )}
          </Paper>
          <Paper
            variant="outlined"
            sx={{ ...panelSx, gridColumn: { md: "1 / -1", lg: "auto" } }}
          >
            {selectedMapping ? (
              <Stack spacing={3}>
                <Box>
                  <Typography variant="h6" sx={{ overflowWrap: "anywhere" }}>
                    {label(
                      getLayer(selectedMapping, "new") ??
                        getLayer(selectedMapping, "old"),
                    )}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {translate(
                      `${config.hasTree ? "updateReview" : "wfsUpdateReview"}.mapping`,
                      {
                        id: selectedMapping.id,
                      },
                    )}
                  </Typography>
                </Box>
                <Divider />
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                  <LayerComparison
                    config={config}
                    layer={getLayer(selectedMapping, "old")}
                    mapping={selectedMapping}
                    side="old"
                  />
                  <LayerComparison
                    config={config}
                    layer={getLayer(selectedMapping, "new")}
                    mapping={selectedMapping}
                    side="new"
                  />
                </Stack>
                <Divider />
                <EditLayerMapping
                  config={config}
                  mapping={selectedMapping}
                  mutationOptions={{
                    onSuccess: () => {
                      notify("ra.notification.updated", { type: "info" });
                      void refetch();
                    },
                  }}
                />
              </Stack>
            ) : (
              <Typography color="text.secondary">
                {translate("updateReview.selectChange")}
              </Typography>
            )}
          </Paper>
        </Box>
      ) : null}
    </Stack>
  );
};

export const ShowServiceUpdateJob = ({
  config = wmsUpdateConfig,
  ...props
}: ShowProps & { config?: ServiceUpdateConfig }) => (
  <Show
    {...props}
    queryOptions={{
      meta: { jsonApiParams: { include: "service,updateCandidate,mappings" } },
    }}
    actions={false}
  >
    <ServiceUpdateJobCard config={config} />
  </Show>
);

export const ShowWebMapServiceUpdate = (props: ShowProps) => (
  <ShowServiceUpdateJob {...props} />
);
