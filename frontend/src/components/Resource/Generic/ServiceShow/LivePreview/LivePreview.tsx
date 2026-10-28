import type L from "leaflet";

import { useCallback, useEffect, useId, useState } from "react";
import {
  type RaRecord,
  useGetList,
  useRecordContext,
  useTranslate,
} from "react-admin";
import { MapContainer, Rectangle, useMap } from "react-leaflet";
import { useNavigate } from "react-router-dom";

import ExpandMore from "@mui/icons-material/ExpandMore";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  LinearProgress,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { CRS } from "leaflet";

import { useOwsContextBase } from "../../../../../react-ows-lib/ContextProvider/OwsContextBase";
import AutoResizeMapContainer from "../../../../MapContainer/ResizeAbleMapContainer";
import { extentBounds, validExtent } from "../../../../MapViewer/utils";
import { getCoverageBounds } from "../../Explorer/coverage";
import ElementViewer, {
  capabilitiesHeaders,
  renderSingleResource,
} from "../ElementViewer";
import {
  PreviewFailure,
  serviceResource,
  usePreview,
  type LiveRecord,
  type PreviewLink,
  type PreviewResult,
  type Protocol,
} from "./usePreview";

/** Loading and error state of a preview request, whatever it answers with. */
const PreviewStatus = ({
  query,
}: {
  query: {
    isFetching: boolean;
    error: PreviewFailure | null;
    refetch: () => void;
  };
}) => {
  const translate = useTranslate();
  return (
    <>
      {query.isFetching && (
        <LinearProgress aria-label={translate("livePreview.loading")} />
      )}
      {query.error && (
        <Alert
          severity="error"
          action={
            <Button onClick={() => query.refetch()}>
              {translate("ra.action.retry")}
            </Button>
          }
        >
          {translate(`livePreview.errors.${query.error.code}`, {
            _: translate("livePreview.errors.unavailable"),
          })}
        </Alert>
      )}
    </>
  );
};

/** States which service answered the preview and when it did. */
const PreviewSource = ({ result }: { result?: PreviewResult }) => {
  const translate = useTranslate();
  if (!result?.fetchedAt) return null;
  return (
    <Typography variant="caption" role="status">
      {translate("livePreview.source", {
        source: result.source,
        time: new Date(result.fetchedAt).toLocaleString(),
      })}
    </Typography>
  );
};

/** Fitted when the map mounts and whenever the records it shows change. */
const FitRecords = ({ bounds }: { bounds: L.LatLngBounds }) => {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds);
  }, [map, bounds]);
  return null;
};

/**
 * The map of the catalogue records: one rectangle per record's coverage, the selected one
 * highlighted, click selects. Catalogue records describe services elsewhere, so nothing of
 * them is asked from a service - only the stored coverages are shown.
 */
const RecordsMap = ({
  records,
  selected,
  onSelect,
}: {
  records: LiveRecord[];
  selected: number;
  onSelect: (index: number) => void;
}) => {
  const placed = records.flatMap((record, index) =>
    validExtent(record.extent) ? [{ index, extent: record.extent }] : [],
  );
  const bounds = placed.reduce<L.LatLngBounds | undefined>(
    (union, { extent }) => {
      const bounds = extentBounds(extent);
      return union ? union.extend(bounds) : bounds;
    },
    undefined,
  );
  return (
    <Box sx={{ height: 380, position: "relative", width: "100%" }}>
      <MapContainer
        crs={CRS.EPSG4326}
        center={[30, 0]}
        zoom={2}
        scrollWheelZoom
        style={{ height: "100%", width: "100%" }}
      >
        <AutoResizeMapContainer />
        {bounds && <FitRecords bounds={bounds} />}
        {placed.map(({ extent, index }) => (
          <Rectangle
            key={`${records[index].identifier}-${index}`}
            bounds={extentBounds(extent)}
            pathOptions={{
              color: index === selected ? "#c14400" : "#1976d2",
              weight: index === selected ? 4 : 1,
            }}
            eventHandlers={{ click: () => onSelect(index) }}
          />
        ))}
      </MapContainer>
    </Box>
  );
};

/**
 * The live preview of one element of a service: the element is chosen from the registry and
 * rendered by the viewer of the single resource - the same component the inspection of the
 * element works with, so what one shows the other shows. The map asks the service itself,
 * per viewport, over the proxy or at the remote origin the way the document of the element
 * names it.
 */
const DataPreview = ({
  protocol,
  serviceId,
  initialSelection,
  onViewer,
}: {
  protocol: "WMS" | "WFS";
  serviceId: string;
  initialSelection?: string;
  onViewer?: (element: RaRecord) => void;
}) => {
  const translate = useTranslate();
  const [selection, setSelection] = useState(initialSelection ?? "");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const choices = useGetList<RaRecord>(
    protocol === "WMS" ? "Layer" : "FeatureType",
    {
      pagination: { page, perPage: 25 },
      sort: { field: "title", order: "ASC" },
      filter: search ? { search } : {},
      meta: {
        relatedResource: { resource: serviceResource[protocol], id: serviceId },
      },
    },
  );
  const namedChoices =
    choices.data?.filter((record) => record.identifier) ?? [];
  useEffect(() => {
    if (!selection && namedChoices[0])
      setSelection(String(namedChoices[0].identifier));
  }, [choices.data]);
  const chosen = namedChoices.find(
    (record) => String(record.identifier) === selection,
  );
  return (
    <Stack spacing={2}>
      {choices.error && (
        <Alert
          severity="error"
          action={
            <Button onClick={() => choices.refetch()}>
              {translate("ra.action.retry")}
            </Button>
          }
        >
          {translate("livePreview.errors.discovery")}
        </Alert>
      )}
      {choices.isFetching && (
        <LinearProgress aria-label={translate("livePreview.loading")} />
      )}
      {!choices.isPending && !choices.error && choices.total === 0 && (
        <Alert severity="info">
          {translate("livePreview.emptySelections")}
        </Alert>
      )}
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField
          size="small"
          label={translate("livePreview.search")}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
        />
        <TextField
          select
          fullWidth
          size="small"
          label={translate(
            protocol === "WMS"
              ? "livePreview.layer"
              : "livePreview.featureType",
          )}
          value={selection}
          onChange={(event) => setSelection(event.target.value)}
        >
          <MenuItem value="">{translate("livePreview.select")}</MenuItem>
          {selection &&
            !namedChoices.some((record) => record.identifier === selection) && (
              <MenuItem value={selection}>{selection}</MenuItem>
            )}
          {namedChoices.map((record) => (
            <MenuItem key={record.id} value={String(record.identifier)}>
              {String(record.title || record.identifier)}
            </MenuItem>
          ))}
        </TextField>
        <Button
          disabled={page <= 1}
          onClick={() => setPage((value) => value - 1)}
        >
          {translate("ra.navigation.previous")}
        </Button>
        <Button
          disabled={page * 25 >= (choices.total ?? 0)}
          onClick={() => setPage((value) => value + 1)}
        >
          {translate("ra.navigation.next")}
        </Button>
      </Stack>
      {onViewer && (
        <Stack direction="row" spacing={1} sx={{ alignSelf: "flex-start" }}>
          <Button disabled={!chosen} onClick={() => chosen && onViewer(chosen)}>
            {translate("ra.action.mapviewer")}
          </Button>
        </Stack>
      )}
      {selection && !chosen && (
        <Typography variant="body2">
          {translate("livePreview.selectOutsidePage", { selection })}
        </Typography>
      )}
      {chosen && (
        <ElementViewer
          key={String(chosen.id)}
          capabilitiesUrl={chosen.capabilitiesUrl}
          extent={chosen.bboxLatLon}
        />
      )}
    </Stack>
  );
};

const CataloguePreview = ({ serviceId }: { serviceId: string }) => {
  const translate = useTranslate();
  const [positions, setPositions] = useState([1]);
  const [selected, setSelected] = useState(0);
  const [linked, setLinked] = useState<PreviewLink>();
  const start = positions[positions.length - 1];
  const query = usePreview("CSW", serviceId, { start });
  const records = query.data?.records ?? [];
  const record = records[selected];
  const changePage = (next: number[]) => {
    setPositions(next);
    setSelected(0);
    setLinked(undefined);
  };
  return (
    <Stack spacing={2}>
      {!query.supported && (
        <Alert severity="warning">
          {translate("livePreview.errors.operation")}
        </Alert>
      )}
      <Stack direction="row" spacing={1}>
        <Button disabled={query.isFetching} onClick={() => query.refetch()}>
          {translate("ra.action.refresh")}
        </Button>
        <Button
          disabled={positions.length <= 1 || query.isFetching}
          onClick={() => changePage(positions.slice(0, -1))}
        >
          {translate("ra.navigation.previous")}
        </Button>
        <Button
          disabled={!query.data?.next || query.isFetching}
          onClick={() => changePage([...positions, query.data!.next!])}
        >
          {translate("ra.navigation.next")}
        </Button>
      </Stack>
      <PreviewStatus query={query} />
      <PreviewSource result={query.data} />
      {query.data && (
        <Typography variant="body2">
          {translate("livePreview.pageScope", {
            start,
            count: records.length,
            total: query.data.matched,
          })}
        </Typography>
      )}
      {query.data && records.length === 0 && (
        <Alert severity="info">{translate("livePreview.emptyRecords")}</Alert>
      )}
      {records.length > 0 && (
        <TextField
          select
          size="small"
          label={translate("livePreview.record")}
          value={selected}
          onChange={(event) => {
            setSelected(Number(event.target.value));
            setLinked(undefined);
          }}
        >
          {records.map((item, index) => (
            <MenuItem key={`${item.identifier}-${index}`} value={index}>
              {item.title ||
                item.identifier ||
                translate("livePreview.untitled")}
            </MenuItem>
          ))}
        </TextField>
      )}
      {record && (
        <Stack spacing={1}>
          <Typography variant="subtitle2">{record.identifier}</Typography>
          <Typography>{record.abstract}</Typography>
          {!validExtent(record.extent) && (
            <Typography>{translate("livePreview.noCoverage")}</Typography>
          )}
          {record.previews.length === 0 && (
            <Typography>{translate("livePreview.noRegistered")}</Typography>
          )}
          {record.previews.map((link, index) => (
            <Button key={index} onClick={() => setLinked(link)}>
              {translate("livePreview.previewLinked", { title: link.title })}
            </Button>
          ))}
        </Stack>
      )}
      {records.length > 0 && (
        <Stack spacing={0.5}>
          <RecordsMap
            records={records}
            selected={selected}
            onSelect={(index) => {
              setSelected(index);
              setLinked(undefined);
            }}
          />
          <Typography variant="caption" color="text.secondary">
            {translate("livePreview.coverage")}
          </Typography>
        </Stack>
      )}
      {linked && (
        <DataPreview
          key={`${linked.serviceId}-${linked.selection}`}
          protocol={linked.protocol}
          serviceId={linked.serviceId}
          initialSelection={linked.selection}
        />
      )}
    </Stack>
  );
};

const LivePreview = ({ protocol }: { protocol: Protocol }) => {
  const record = useRecordContext();
  const translate = useTranslate();
  const id = useId();
  const [expanded, setExpanded] = useState(false);
  const globalContext = useOwsContextBase();
  const navigate = useNavigate();
  // the element is handed to the full viewer through its own capabilities document: the
  // document already names the urls its operations are answered at - the proxy for a
  // secured service, which keeps the stored credentials and the spatial security on the
  // server side, the remote service for a service without rules - so the viewer keeps on
  // asking exactly where the live preview asked
  const transfer = useCallback(
    async (element: RaRecord) => {
      const documentUrl = String(element.capabilitiesUrl ?? "");
      if (!documentUrl) {
        return;
      }
      await globalContext.addServiceByUrl(
        documentUrl,
        capabilitiesHeaders(new URL(documentUrl)),
        (context) => renderSingleResource(context, documentUrl),
      );
      const bounds = getCoverageBounds(element.bboxLatLon);
      navigate("/viewer", {
        state: {
          previewExtent: bounds
            ? [
                bounds.getWest(),
                bounds.getSouth(),
                bounds.getEast(),
                bounds.getNorth(),
              ]
            : undefined,
        },
      });
    },
    [globalContext.addServiceByUrl, navigate],
  );
  if (!record) return null;
  return (
    <Accordion
      expanded={expanded}
      onChange={(_, value) => setExpanded(value)}
      sx={{ width: "100%" }}
    >
      <AccordionSummary
        expandIcon={<ExpandMore />}
        id={`${id}-summary`}
        aria-controls={`${id}-content`}
      >
        <Typography variant="h6">{translate("livePreview.title")}</Typography>
      </AccordionSummary>
      <AccordionDetails id={`${id}-content`}>
        {expanded &&
          (protocol === "CSW" ? (
            <CataloguePreview serviceId={String(record.id)} />
          ) : (
            <DataPreview
              protocol={protocol}
              serviceId={String(record.id)}
              onViewer={(element) => void transfer(element)}
            />
          ))}
      </AccordionDetails>
    </Accordion>
  );
};

export default LivePreview;
