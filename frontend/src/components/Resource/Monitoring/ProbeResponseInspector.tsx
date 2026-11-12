import { useEffect, useState } from "react";
import { useTranslate } from "react-admin";

import CloudOffOutlineIcon from "@mui/icons-material/CloudOffOutlined";
import {
  Alert,
  Box,
  Button,
  Skeleton,
  Stack,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import {
  API_BASE_URL,
  useHttpClientContext,
} from "../../../context/HttpClientContext";
import { getAuthToken } from "../../../providers/authProvider";
import { PreviewImage } from "../Generic/ServiceShow/ServicePreviewImage";

/** The execution summary of one probe, as the result serializers answer it
 * (`PROBE_RESULT_EXECUTION_FIELDS` in registry/serializers/monitoring.py).
 * The body of the response is never part of this answer - the inspector
 * reads it from `responseArtifactUrl` alone (#682). */
export interface ProbeExecution {
  statusCode?: number | null;
  monitoredUri?: string | null;
  requestDuration?: string | null;
  dateCreated?: string | null;
  dateDone?: string | null;
  requestError?: string | null;
  errorDetail?: string | null;
  responseSize?: number | null;
  responseContentType?: string | null;
  hasResponseArtifact: boolean;
  responseArtifactUrl?: string | null;
}

const TEXT_TYPES = [
  "application/xml",
  "text/xml",
  "application/gml+xml",
  "application/json",
  "text/plain",
];

/** The characters of a stored document which are rendered: a body which a
 * probe was allowed to keep is at most the configured maximum size, but the
 * whole of it does not belong into the DOM of an expanded card. */
const SHOWN_TEXT_LENGTH = 60_000;

const isTextType = (contentType: string) =>
  TEXT_TYPES.some((type) => contentType.startsWith(type));

/** The size of the stored body in the short unit form an inspector reads;
 * the unit itself is not translated, as KB and MB are read everywhere. */
const formatBytes = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

/** The duration as the backend answers it - a DRF DurationField renders
 * "HH:MM:SS.ffffff" - in the short form an inspector reads. */
const readDuration = (value?: string | null) => {
  if (!value) return null;
  const [hours = "0", minutes = "0", rest = "0"] = value.split(":");
  const total = Number(hours) * 3600 + Number(minutes) * 60 + Number(rest);
  return Number.isFinite(total)
    ? total < 1
      ? `${Math.round(total * 1000)} ms`
      : `${total.toFixed(1)} s`
    : value;
};

const ArtifactAlert = ({ status }: { status?: number }) => {
  const translate = useTranslate();
  const key =
    status === 410
      ? "monitoringRun.response.expired"
      : status === 404
        ? "monitoringRun.response.missing"
        : "monitoringRun.response.unavailable";
  return (
    <Alert severity="warning" icon={<CloudOffOutlineIcon fontSize="inherit" />}>
      {translate(key)}
    </Alert>
  );
};

const ImageArtifact = ({ blob }: { blob: Blob }) => {
  const translate = useTranslate();
  const [imageUrl, setImageUrl] = useState<string>();
  useEffect(() => {
    const nextImageUrl = URL.createObjectURL(blob);
    setImageUrl(nextImageUrl);
    return () => {
      URL.revokeObjectURL(nextImageUrl);
      setImageUrl(undefined);
    };
  }, [blob]);
  return (
    <PreviewImage
      key={imageUrl}
      src={imageUrl}
      alt={translate("monitoringRun.response.image")}
      loadingLabel={translate("monitoringRun.response.loading")}
      unavailableLabel={translate("monitoringRun.response.unavailable")}
      containerSx={{ width: { xs: "100%", sm: 320 }, height: 260 }}
    />
  );
};

const TextArtifact = ({ blob }: { blob: Blob }) => {
  const translate = useTranslate();
  const [text, setText] = useState<string>();
  const [downloadUrl, setDownloadUrl] = useState<string>();
  useEffect(() => {
    let stale = false;
    void blob.text().then((body) => {
      if (!stale) setText(body);
    });
    const nextDownloadUrl = URL.createObjectURL(blob);
    setDownloadUrl(nextDownloadUrl);
    return () => {
      stale = true;
      URL.revokeObjectURL(nextDownloadUrl);
      setDownloadUrl(undefined);
    };
  }, [blob]);
  if (text === undefined)
    return (
      <Skeleton
        variant="rectangular"
        height={120}
        role="status"
        aria-label={translate("monitoringRun.response.loading")}
      />
    );
  const truncated = text.length > SHOWN_TEXT_LENGTH;
  return (
    <Stack spacing={1}>
      <Box
        component="pre"
        sx={{
          m: 0,
          p: 1.5,
          maxHeight: 320,
          overflow: "auto",
          borderRadius: 1,
          bgcolor: "action.hover",
          fontSize: "0.75rem",
          whiteSpace: "pre-wrap",
          overflowWrap: "anywhere",
        }}
      >
        {truncated ? text.slice(0, SHOWN_TEXT_LENGTH) : text}
      </Box>
      <Stack
        direction="row"
        spacing={1}
        sx={{ alignItems: "center", flexWrap: "wrap" }}
      >
        {truncated && (
          <Typography variant="caption" color="text.secondary">
            {translate("monitoringRun.response.truncated")}
          </Typography>
        )}
        {downloadUrl && (
          <Button
            size="small"
            variant="outlined"
            href={downloadUrl}
            download={`probe-response-${blob.type || "body"}`}
          >
            {translate("monitoringRun.response.download")}
          </Button>
        )}
      </Stack>
    </Stack>
  );
};

const ResponseArtifact = ({
  execution,
  active,
}: {
  execution: ProbeExecution;
  active: boolean;
}) => {
  const translate = useTranslate();
  const { api } = useHttpClientContext();
  const { responseArtifactUrl: url } = execution;
  const contentType = execution.responseContentType ?? "";
  const isImage = contentType.startsWith("image/");
  const renderable = isImage || isTextType(contentType);
  const { data, error } = useQuery({
    queryKey: ["probeResponseArtifact", url],
    enabled: Boolean(api && url && renderable && active),
    retry: false,
    gcTime: 0,
    staleTime: Infinity,
    queryFn: async ({ signal }) => {
      if (!api || !url) throw new Error("Artifact unavailable");
      const endpoint = new URL(url, API_BASE_URL);
      if (endpoint.origin !== new URL(API_BASE_URL).origin)
        throw new Error("Artifact must use the MrMap API");
      const token = getAuthToken()?.token;
      return (
        await api.client.request<Blob>({
          url: endpoint.href,
          responseType: "blob",
          signal,
          headers: {
            Accept: "*/*",
            ...(token ? { Authorization: `Token ${token}` } : {}),
          },
        })
      ).data;
    },
  });

  if (!renderable)
    return (
      <Typography variant="body2" color="text.secondary">
        {translate("monitoringRun.response.notRenderable", { type: contentType })}
      </Typography>
    );
  if (error)
    return (
      <ArtifactAlert
        status={(error as { response?: { status?: number } }).response?.status}
      />
    );
  if (!data)
    return (
      <Box sx={{ width: { xs: "100%", sm: 320 } }}>
        <Skeleton
          variant="rectangular"
          height={isImage ? 260 : 120}
          role="status"
          aria-label={translate("monitoringRun.response.loading")}
        />
      </Box>
    );
  return isImage ? <ImageArtifact blob={data} /> : <TextArtifact blob={data} />;
};

const ExecutionField = ({ label, value }: { label: string; value: string }) => (
  <Box sx={{ minWidth: 0 }}>
    <Typography variant="caption" color="text.secondary">
      {label}
    </Typography>
    <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
      {value}
    </Typography>
  </Box>
);

/** Renders what a probe actually answered at execution time (#682): the
 * summary of the request, which every result answers next to its checks, and
 * the stored body of the response, which the authenticated artifact endpoint
 * of the result answers alone. The body arrives as it was captured - an
 * image as an image, a document as readable text - and a body which is gone,
 * expired or never stored is said so instead of failing the card. An html or
 * svg body was never stored by the probe and is never rendered here. The
 * body is only fetched while `active` - the caller passes the open state of
 * its card, so a whole list never fetches every stored response at once. */
export const ProbeResponseInspector = ({
  execution,
  active = true,
}: {
  execution: ProbeExecution;
  active?: boolean;
}) => {
  const translateRoot = useTranslate();
  const translate = (key: string, options?: Record<string, unknown>) =>
    translateRoot(`monitoringRun.response.${key}`, options);
  const {
    statusCode,
    monitoredUri,
    requestDuration,
    requestError,
    errorDetail,
    responseSize,
    responseContentType,
    hasResponseArtifact,
  } = execution;
  const duration = readDuration(requestDuration);
  return (
    <Stack spacing={1.5}>
      <Typography variant="overline" color="text.secondary">
        {translate("title")}
      </Typography>
      {requestError && (
        <Alert severity="error">
          <Typography variant="body2">{requestError}</Typography>
          {errorDetail && (
            <Typography
              variant="caption"
              component="div"
              sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
            >
              {errorDetail}
            </Typography>
          )}
        </Alert>
      )}
      <Stack direction="row" spacing={3} sx={{ flexWrap: "wrap" }}>
        {statusCode !== null && statusCode !== undefined && (
          <ExecutionField
            label={translate("status")}
            value={String(statusCode)}
          />
        )}
        {duration && (
          <ExecutionField label={translate("duration")} value={duration} />
        )}
        {responseSize !== null && responseSize !== undefined && (
          <ExecutionField
            label={translate("size")}
            value={formatBytes(responseSize)}
          />
        )}
        {responseContentType && (
          <ExecutionField
            label={translate("contentType")}
            value={responseContentType}
          />
        )}
      </Stack>
      {monitoredUri && (
        <ExecutionField label={translate("uri")} value={monitoredUri} />
      )}
      {!hasResponseArtifact && (
        <Typography variant="body2" color="text.secondary">
          {translate("notStored")}
        </Typography>
      )}
      {hasResponseArtifact && (
        <ResponseArtifact execution={execution} active={active} />
      )}
    </Stack>
  );
};

export default ProbeResponseInspector;
