import { useCallback, useEffect, useId, useMemo, useState } from "react";
import {
  type RaRecord,
  useGetList,
  useRecordContext,
  useTranslate,
} from "react-admin";
import { useNavigate } from "react-router-dom";

import ExpandMore from "@mui/icons-material/ExpandMore";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Checkbox,
  FormControlLabel,
  LinearProgress,
  Link,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { v4 as uuidv4 } from "uuid";

import { API_BASE_URL } from "../../../../../context/HttpClientContext";
import { getAuthToken } from "../../../../../providers/authProvider";
import {
  OwsContextBase,
  useOwsContextBase,
} from "../../../../../react-ows-lib/ContextProvider/OwsContextBase";
import { validExtent } from "../../../../MapViewer/utils";
import PreviewMap, { type Viewport } from "./PreviewMap";
import {
  PreviewFailure,
  serviceResource,
  useIdentify,
  usePreview,
  type Protocol,
  type PreviewLink,
  type PreviewResult,
} from "./usePreview";

/** Loading and error state of a preview or identify request, whatever it answers with. */
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

const parseIdentify = (text: string): unknown => {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
};

const entries = (value: unknown) =>
  value && typeof value === "object" && !Array.isArray(value)
    ? Object.entries(value as Record<string, unknown>)
    : [];

const identifyFeatures = (value: unknown) => {
  const features = (value as { features?: unknown })?.features;
  return Array.isArray(features) ? features : undefined;
};

/** Extract only text and table structure; upstream nodes never enter the live DOM. */
const readIdentifyHtml = (text: string) => {
  const document = new DOMParser().parseFromString(text, "text/html");
  document
    .querySelectorAll(
      "script, style, template, noscript, iframe, object, embed, svg, math, form",
    )
    .forEach((node) => node.remove());
  const tables = Array.from(document.querySelectorAll("table"), (table) => ({
    caption: table.caption?.textContent?.trim(),
    rows: Array.from(table.rows, (row) =>
      Array.from(row.cells, (cell) => ({
        text: cell.textContent?.trim() ?? "",
        header: cell.tagName === "TH",
      })),
    ).filter((row) => row.some((cell) => cell.text)),
  })).filter((table) => table.rows.length > 0);
  document.querySelectorAll("table").forEach((node) => node.remove());
  document.body
    .querySelectorAll("br, p, div, li, h1, h2, h3, h4, h5, h6")
    .forEach((node) => node.append("\n"));
  return { tables, text: document.body.textContent?.trim() ?? "" };
};

/** Presents service data as React text and tables, with the original available on demand. */
export const FeatureInfoResult = ({
  text,
  contentType,
  paginate = false,
}: {
  text: string;
  contentType: string;
  paginate?: boolean;
}) => {
  const translate = useTranslate();
  const [featureIndex, setFeatureIndex] = useState(0);
  useEffect(() => setFeatureIndex(0), [text]);
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    const next = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [text]);
  const mediaType = contentType.split(";")[0].trim().toLowerCase();
  const html = useMemo(
    () =>
      mediaType === "text/html" || mediaType === "application/xhtml+xml"
        ? readIdentifyHtml(text)
        : undefined,
    [mediaType, text],
  );
  const parsed =
    mediaType === "application/json" || mediaType === "application/geo+json"
      ? parseIdentify(text)
      : undefined;
  const features = parsed === undefined ? undefined : identifyFeatures(parsed);
  return (
    <Stack spacing={1} sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
      {html ? (
        <>
          {!html.tables.length && !html.text && (
            <Typography variant="body2" color="text.secondary">
              {translate("livePreview.noFeatures")}
            </Typography>
          )}
          {html.text && (
            <Typography
              variant="body2"
              sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
            >
              {html.text}
            </Typography>
          )}
          {html.tables.map((table, index) => (
            <TableContainer key={index} sx={{ maxHeight: 300 }}>
              <Table
                size="small"
                sx={{
                  "& td, & th": {
                    verticalAlign: "top",
                    minWidth: 100,
                    maxWidth: 280,
                    overflowWrap: "anywhere",
                  },
                }}
              >
                {table.caption && (
                  <caption style={{ captionSide: "top" }}>
                    {table.caption}
                  </caption>
                )}
                <TableBody>
                  {table.rows.map((row, rowIndex) => (
                    <TableRow key={rowIndex}>
                      {row.map((cell, cellIndex) => (
                        <TableCell
                          key={cellIndex}
                          component={cell.header ? "th" : "td"}
                          sx={
                            cell.header
                              ? { fontWeight: "bold", bgcolor: "action.hover" }
                              : undefined
                          }
                        >
                          {cell.text}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ))}
        </>
      ) : features ? (
        features.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {translate("livePreview.noFeatures")}
          </Typography>
        ) : (
          <Stack spacing={1}>
            {paginate && (
              <Stack direction="row" sx={{ alignItems: "center" }} spacing={1}>
                <Typography variant="caption" sx={{ flex: 1 }}>
                  {translate("viewerFeatureInfo.featurePage", {
                    current: Math.min(featureIndex + 1, features.length),
                    total: features.length,
                  })}
                </Typography>
                <Button
                  size="small"
                  disabled={featureIndex === 0}
                  onClick={() => setFeatureIndex((index) => index - 1)}
                  aria-label={translate("ra.navigation.previous")}
                >
                  ‹
                </Button>
                <Button
                  size="small"
                  disabled={featureIndex >= features.length - 1}
                  onClick={() => setFeatureIndex((index) => index + 1)}
                  aria-label={translate("ra.navigation.next")}
                >
                  ›
                </Button>
              </Stack>
            )}
            {(paginate
              ? features.slice(featureIndex, featureIndex + 1)
              : features
            ).map((feature, index) => (
              <Stack
                key={index}
                sx={{
                  border: paginate ? 0 : 1,
                  borderColor: "divider",
                  p: paginate ? 0 : 1,
                }}
              >
                {(entries((feature as { properties?: unknown })?.properties)
                  .length
                  ? entries((feature as { properties?: unknown }).properties)
                  : entries(feature)
                ).map(([key, value]) => (
                  <Typography
                    key={key}
                    component="div"
                    variant="body2"
                    sx={
                      paginate
                        ? {
                            display: "grid",
                            gridTemplateColumns:
                              "minmax(90px, .8fr) minmax(0, 1.2fr)",
                            gap: 1,
                            py: 1,
                            borderTop: 1,
                            borderColor: "divider",
                            overflowWrap: "anywhere",
                          }
                        : undefined
                    }
                  >
                    {paginate ? (
                      <>
                        <span>{key}</span>
                        <span>
                          {typeof value === "object"
                            ? JSON.stringify(value)
                            : String(value ?? "")}
                        </span>
                      </>
                    ) : (
                      <>
                        {key}:{" "}
                        {typeof value === "object"
                          ? JSON.stringify(value)
                          : String(value ?? "")}
                      </>
                    )}
                  </Typography>
                ))}
              </Stack>
            ))}
          </Stack>
        )
      ) : (
        <Typography
          component="pre"
          sx={{ whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}
        >
          {parsed === undefined ? text : JSON.stringify(parsed, null, 2)}
        </Typography>
      )}
      <Accordion
        slotProps={{ transition: { unmountOnExit: true } }}
        disableGutters
        elevation={0}
        sx={{
          "&:before": { display: "none" },
          borderTop: 1,
          borderColor: "divider",
        }}
      >
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="body2">
            {translate("livePreview.rawResponse")}
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          {url && (
            <Link href={url} download="getfeatureinfo.txt">
              {translate("livePreview.featureInfo")}
            </Link>
          )}
          <Typography
            component="pre"
            sx={{
              fontFamily: "monospace",
              fontSize: "0.75rem",
              whiteSpace: "pre",
              maxHeight: 200,
              overflow: "auto",
            }}
          >
            {text}
          </Typography>
        </AccordionDetails>
      </Accordion>
    </Stack>
  );
};

const DataPreview = ({
  protocol,
  serviceId,
  initialSelection,
  onViewer,
}: {
  protocol: "WMS" | "WFS";
  serviceId: string;
  initialSelection?: string;
  onViewer?: (selection: string, viewport: Viewport) => void;
}) => {
  const translate = useTranslate();
  const [selection, setSelection] = useState(initialSelection ?? "");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [visible, setVisible] = useState(true);
  const [viewport, setViewport] = useState<Viewport>();
  const [identify, setIdentify] = useState<{ x: number; y: number }>();
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
  const discovery = usePreview(
    protocol,
    serviceId,
    { selection },
    Boolean(selection),
  );
  const query = usePreview(
    protocol,
    serviceId,
    { selection, ...viewport },
    Boolean(
      selection && visible && viewport && discovery.data && !discovery.error,
    ),
  );
  const info = useIdentify(
    discovery.data?.identify,
    viewport,
    visible ? identify : undefined,
  );
  const updateViewport = useCallback((next: Viewport) => {
    setViewport((previous) =>
      previous?.bbox === next.bbox &&
      previous?.width === next.width &&
      previous?.height === next.height
        ? previous
        : next,
    );
    setIdentify(undefined);
  }, []);
  const namedChoices =
    choices.data?.filter((record) => record.identifier) ?? [];
  useEffect(() => {
    if (!selection && namedChoices[0])
      setSelection(String(namedChoices[0].identifier));
  }, [choices.data]);
  return (
    <Stack spacing={2}>
      {!discovery.supported && (
        <Alert severity="warning">
          {translate("livePreview.errors.operation")}
        </Alert>
      )}
      <Typography variant="body2">
        {translate("livePreview.storedDiscovery")}
      </Typography>
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
          onChange={(event) => {
            setSelection(event.target.value);
            setIdentify(undefined);
          }}
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
      <Stack direction="row" spacing={1}>
        <FormControlLabel
          control={
            <Checkbox
              checked={visible}
              onChange={(event) => {
                setVisible(event.target.checked);
                setIdentify(undefined);
              }}
            />
          }
          label={translate("livePreview.visible")}
        />
        <Button
          disabled={!selection || query.isFetching}
          onClick={() => {
            discovery.refetch();
            if (visible && viewport) query.refetch();
          }}
        >
          {translate("ra.action.refresh")}
        </Button>
        {onViewer && (
          <Button
            disabled={!selection || !viewport || Boolean(discovery.error)}
            onClick={() => viewport && onViewer(selection, viewport)}
          >
            {translate("ra.action.mapviewer")}
          </Button>
        )}
      </Stack>
      <PreviewStatus query={discovery} />
      <PreviewStatus query={query} />
      <PreviewSource result={query.data} />
      {query.data?.limited && (
        <Alert severity="info">
          {translate("livePreview.limited", { count: query.data.limit })}
        </Alert>
      )}
      {query.data?.features?.features.length === 0 && (
        <Alert severity="info">{translate("livePreview.emptyFeatures")}</Alert>
      )}
      {protocol === "WMS" &&
        discovery.data &&
        !discovery.data.configuration?.queryable && (
          <Typography variant="body2">
            {translate("livePreview.noIdentify")}
          </Typography>
        )}
      <PreviewMap
        viewport={viewport}
        onViewport={updateViewport}
        extent={discovery.data?.configuration?.extent}
        image={visible ? query.data?.image : undefined}
        features={visible ? query.data?.features : undefined}
        identifyAvailable={Boolean(
          visible && discovery.data?.configuration?.queryable,
        )}
        onIdentify={
          visible && discovery.data?.configuration?.queryable
            ? (x, y) => setIdentify({ x, y })
            : undefined
        }
      />
      <PreviewStatus query={info} />
      {visible && info.data?.info !== undefined && (
        <FeatureInfoResult
          text={info.data.info}
          contentType={
            info.data.contentType ?? discovery.data?.identify?.infoFormat ?? ""
          }
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
      <PreviewMap
        onViewport={() => {}}
        records={records}
        selectedRecord={selected}
        onSelectRecord={(index) => {
          setSelected(index);
          setLinked(undefined);
        }}
        extent={record?.extent}
      />
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
  // the viewer is handed the service through the security proxy: a registered service keeps its
  // stored credentials and its spatial security on the server side, because the camouflaged
  // operations of the delivered capabilities point back to this origin and the viewer will ask
  // the proxy, which bounds the requests, instead of the upstream service
  const transfer = useCallback(
    async (selection: string, viewport: Viewport) => {
      const wms = protocol === "WMS";
      const url = new URL(
        `/mrmap-proxy/${wms ? "wms" : "wfs"}/${record?.id}`,
        API_BASE_URL,
      );
      url.search = wms
        ? "SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0"
        : "SERVICE=WFS&REQUEST=GetCapabilities&VERSION=2.0.0";
      const token = getAuthToken()?.token;
      const authenticationId = uuidv4();
      const appendService = wms
        ? globalContext.addWMSByUrl
        : globalContext.addWFSByUrl;
      await appendService(
        url.href,
        token ? new Headers({ Authorization: `Token ${token}` }) : undefined,
        (context, treeId) => {
          const authenticationHeaders = Array.isArray(
            context.authenticationHeaders,
          )
            ? context.authenticationHeaders
            : [];
          if (token)
            context.authenticationHeaders = [
              ...authenticationHeaders,
              {
                id: authenticationId,
                type: "header",
                name: "Authorization",
                value: `Token ${token}`,
                origin: url.origin,
              },
            ];
          context.features
            .filter((feature) =>
              feature.properties.folder?.startsWith(`/${treeId}`),
            )
            .forEach((feature) => {
              const operation = wms
                ? feature.getWmsOperationByCode("GetMap")
                : feature.getWfsOperationByCode("GetFeature");
              if (operation) {
                const request = new URL(operation.href);
                const requested = [...request.searchParams.entries()].find(
                  ([key]) =>
                    key.toLowerCase() === (wms ? "layers" : "typename"),
                )?.[1];
                const active = requested === selection;
                operation.active = active;
                feature.properties.active = active;
                feature.properties.offerings?.forEach((offering) =>
                  offering.operations?.forEach((item) => {
                    item.active = active;
                    if (token && new URL(item.href).origin === url.origin)
                      item["x-authentication-id"] = authenticationId;
                  }),
                );
              }
            });
          context.bbox = viewport.bbox.split(",").map(Number) as [
            number,
            number,
            number,
            number,
          ];
          return context;
        },
      );
      navigate("/viewer", {
        state: { previewExtent: viewport.bbox.split(",").map(Number) },
      });
    },
    [
      protocol,
      record?.id,
      globalContext.addWMSByUrl,
      globalContext.addWFSByUrl,
      navigate,
    ],
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
        {expanded && (
          <OwsContextBase key={`${protocol}:${record.id}`}>
            {protocol === "CSW" ? (
              <CataloguePreview serviceId={String(record.id)} />
            ) : (
              <DataPreview
                protocol={protocol}
                serviceId={String(record.id)}
                onViewer={transfer}
              />
            )}
          </OwsContextBase>
        )}
      </AccordionDetails>
    </Accordion>
  );
};

export default LivePreview;
