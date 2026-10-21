import { useCallback, useEffect, useId, useState } from "react";
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
import PreviewMap, { type Viewport, validExtent } from "./PreviewMap";
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

/**
 * Renders an identify result by its media type.
 *
 * Nothing of the upstream response becomes markup of this page: JSON is read into
 * attributes, everything else is shown as text, and the download link is always typed
 * `text/plain`. `text/html` is refused, because the security proxy answers it from the
 * MrMap origin and it could read the credentials stored there.
 */
export const FeatureInfoResult = ({
  text,
  contentType,
}: {
  text: string;
  contentType: string;
}) => {
  const translate = useTranslate();
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    const next = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [text]);
  const mediaType = contentType.split(";")[0].trim().toLowerCase();
  const parsed =
    mediaType === "application/json" || mediaType === "application/geo+json"
      ? parseIdentify(text)
      : undefined;
  const features = parsed === undefined ? undefined : identifyFeatures(parsed);
  return (
    <Stack spacing={1}>
      {url && (
        <Link href={url} target="_blank" rel="noopener noreferrer">
          {translate("livePreview.featureInfo")}
        </Link>
      )}
      {(mediaType === "text/html" ||
        mediaType === "application/xhtml+xml") && (
        <Alert severity="warning">
          {translate("livePreview.htmlNotRendered")}
        </Alert>
      )}
      {features ? (
        <Stack spacing={1}>
          {features.map((feature, index) => (
            <Stack
              key={index}
              sx={{ border: 1, borderColor: "divider", p: 1 }}
            >
              {(entries(
                (feature as { properties?: unknown })?.properties,
              ).length
                ? entries((feature as { properties?: unknown }).properties)
                : entries(feature)
              ).map(([key, value]) => (
                <Typography key={key} component="div" variant="body2">
                  {key}:{" "}
                  {typeof value === "object"
                    ? JSON.stringify(value)
                    : String(value ?? "")}
                </Typography>
              ))}
            </Stack>
          ))}
        </Stack>
      ) : (
        <Typography
          component="pre"
          sx={{ whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}
        >
          {parsed === undefined ? text : JSON.stringify(parsed, null, 2)}
        </Typography>
      )}
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
            info.data.contentType ??
            discovery.data?.identify?.infoFormat ??
            ""
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
  const transfer = useCallback(
    async (selection: string, viewport: Viewport) => {
      const url = new URL(`/mrmap-proxy/wms/${record?.id}`, API_BASE_URL);
      url.search = "SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0";
      const token = getAuthToken()?.token;
      const authenticationId = uuidv4();
      await globalContext.addWMSByUrl(
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
              },
            ];
          context.features
            .filter((feature) =>
              feature.properties.folder?.startsWith(`/${treeId}`),
            )
            .forEach((feature) => {
              const operation = feature.getWmsOperationByCode("GetMap");
              if (operation) {
                const request = new URL(operation.href);
                const layer = [...request.searchParams.entries()].find(
                  ([key]) => key.toLowerCase() === "layers",
                )?.[1];
                const active = layer === selection;
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
    [record?.id, globalContext.addWMSByUrl, navigate],
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
                onViewer={protocol === "WMS" ? transfer : undefined}
              />
            )}
          </OwsContextBase>
        )}
      </AccordionDetails>
    </Accordion>
  );
};

export default LivePreview;
