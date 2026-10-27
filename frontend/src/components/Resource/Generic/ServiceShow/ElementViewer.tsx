import type { OWSContext } from "../../../../ows-lib/OwsContext/core";

import { useCallback, useEffect, useMemo } from "react";
import { useTranslate } from "react-admin";
import { MapContainer } from "react-leaflet";

import { Alert, Box, Button, LinearProgress, Stack, Typography } from "@mui/material";
import { CRS } from "leaflet";

import { API_BASE_URL } from "../../../../context/HttpClientContext";
import { getAuthToken } from "../../../../providers/authProvider";
import { OwsContextBase, useOwsContextBase } from "../../../../react-ows-lib/ContextProvider/OwsContextBase";
import WebFeatureServiceControl from "../../../MapContainer/GetFeatureControl";
import WebMapServiceControl from "../../../MapContainer/GetMapControl";
import AutoResizeMapContainer from "../../../MapContainer/ResizeAbleMapContainer";
import { MapViewerBase, useMapViewerBase } from "../../../MapViewer/MapViewerBase";
import { getCoverageBounds } from "../Explorer/coverage";

/**
 * The MrMap token is handed to the request that reads the capabilities document only while that
 * document is read from the MrMap origin: the per element document of the registry is always
 * answered by this origin (registry/proxy/resource_capabilities.py), a document from anywhere
 * else is asked without credentials.
 */
export const capabilitiesHeaders = (url: URL): Headers | undefined => {
  const token = getAuthToken()?.token;
  if (!token || url.origin !== new URL(API_BASE_URL, window.location.href).origin) {
    return undefined;
  }
  return new Headers({ Authorization: `Token ${String(token)}` });
};

/** The operations which make a resource show up on the map, one per protocol. */
const RENDER_CODES = new Set(["GetMap", "GetFeature"]);

/**
 * The single resource which the per element document advertises is rendered right away: its
 * rendering operation becomes active, everything else of the document stays as it is. The
 * credentials with which the document was read keep bound to the origin they were given for,
 * what the document advertises beyond that origin is asked bare - the MrMap token is never
 * sent to a remote service, so an endpoint of another origin either answers the browser
 * directly or it visibly fails.
 */
export const renderSingleResource = (
  context: OWSContext,
  documentUrl: string,
): OWSContext => {
  const documentOrigin = new URL(documentUrl).origin;
  context.features.forEach((feature) => {
    let renderable = false;
    for (const offering of feature.properties.offerings ?? []) {
      for (const operation of offering.operations ?? []) {
        const render = RENDER_CODES.has(operation.code);
        operation.active = render;
        if (render) {
          renderable = true;
          if (new URL(operation.href).origin !== documentOrigin) {
            delete operation["x-authentication-id"];
          }
        }
      }
    }
    feature.properties.active = renderable;
  });
  return context;
};

/** Names the resources which the viewer cannot render, so a silent map is not mistaken for an empty layer. */
const UnsupportedNotice = () => {
  const translate = useTranslate();
  const { unsupportedFeatures } = useMapViewerBase();
  if (unsupportedFeatures.length === 0) {
    return null;
  }
  return (
    <Alert severity="warning">
      {translate("viewerUnsupported.summary", {
        count: unsupportedFeatures.length,
      })}
    </Alert>
  );
};

/** The viewer of one element, once its document is read: the map asks the service per viewport on its own. */
const ElementMap = ({
  capabilitiesUrl,
  previewExtent,
}: {
  capabilitiesUrl: string;
  previewExtent?: number[];
}) => {
  const translate = useTranslate();
  const {
    addServiceByUrl,
    resetContext,
    loadingStatus,
    loadingMessage,
    errorMessage,
  } = useOwsContextBase();

  const load = useCallback(() => {
    resetContext();
    void addServiceByUrl(
      capabilitiesUrl,
      capabilitiesHeaders(new URL(capabilitiesUrl)),
      (context) => renderSingleResource(context, capabilitiesUrl),
    );
  }, [addServiceByUrl, resetContext, capabilitiesUrl]);
  useEffect(() => {
    load();
  }, [load]);

  if (loadingStatus === "error") {
    return (
      <Alert
        severity="error"
        action={
          <Button onClick={load}>{translate("ra.action.retry")}</Button>
        }
      >
        {errorMessage ?? translate("elementViewer.error")}
      </Alert>
    );
  }
  if (loadingStatus !== "ready") {
    return (
      <Stack spacing={0.5}>
        <LinearProgress aria-label={translate("elementViewer.loading")} />
        {loadingMessage && (
          <Typography variant="caption" color="text.secondary">
            {loadingMessage}
          </Typography>
        )}
      </Stack>
    );
  }
  return (
    <Stack spacing={0.5}>
      <UnsupportedNotice />
      <MapViewerBase previewExtent={previewExtent}>
        <Box sx={{ height: 380, position: "relative", width: "100%" }}>
          <MapContainer
            crs={CRS.EPSG4326}
            center={[51.505, -0.09]}
            zoom={2}
            maxZoom={20}
            minZoom={0}
            maxBoundsViscosity={0.8}
            scrollWheelZoom
            style={{ height: "100%", width: "100%" }}
          >
            <AutoResizeMapContainer />
            <WebMapServiceControl />
            <WebFeatureServiceControl />
          </MapContainer>
        </Box>
      </MapViewerBase>
    </Stack>
  );
};

/**
 * Renders exactly one layer or feature type with the machinery of the map viewer.
 *
 * The document of a single resource (registry/proxy/resource_capabilities.py, serialized as
 * `capabilitiesUrl`) is the only input: it names the resource and the urls its operations are
 * answered at - the security proxy for a service which is secured or camouflaged, the remote
 * service for a service which is neither - so the viewer asks over the proxy or straight at the
 * remote origin the way the registry decided it per service. The panel hands the document to a
 * viewer context, lets the resource show itself and zooms the map to the extent the element
 * advertises; from there every pan and zoom of the map refreshes the answer, exactly like in the
 * full map viewer.
 */
export const ElementViewer = ({
  capabilitiesUrl,
  extent,
}: {
  capabilitiesUrl?: unknown;
  extent?: unknown;
}) => {
  const translate = useTranslate();
  const url =
    typeof capabilitiesUrl === "string" && capabilitiesUrl
      ? capabilitiesUrl
      : undefined;
  const previewExtent = useMemo(() => {
    const bounds = getCoverageBounds(extent);
    return bounds
      ? [
          bounds.getWest(),
          bounds.getSouth(),
          bounds.getEast(),
          bounds.getNorth(),
        ]
      : undefined;
  }, [extent]);
  if (!url) {
    return <Alert severity="warning">{translate("elementViewer.noDocument")}</Alert>;
  }
  return (
    <OwsContextBase key={url}>
      <ElementMap capabilitiesUrl={url} previewExtent={previewExtent} />
    </OwsContextBase>
  );
};

export default ElementViewer;
