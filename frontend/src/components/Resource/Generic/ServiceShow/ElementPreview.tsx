import type { FeatureCollection } from "geojson";
import type L from "leaflet";

import { useEffect, useMemo } from "react";
import { useGetOne, useTranslate, type RaRecord } from "react-admin";
import { ImageOverlay, useMap } from "react-leaflet";

import { Alert, Button, LinearProgress, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import FeatureGroupEditor from "../../../Input/FeatureGroupEditor";
import GeoJsonMap from "../../../MapContainer/GeoJsonMap";
import { getCoverageBounds } from "../Explorer/coverage";
import {
  buildWfsGetFeatureUrl,
  buildWmsGetMapUrl,
  FEATURE_LIMIT,
  geoJsonOutputFormat,
  proxyUrl,
  remoteOperationUrl,
  requestHeaders,
  type PreviewProtocol,
} from "./previewRequests";

/**
 * The preview always shows the element's advertised extent. The leaflet bounds
 * object must be fitted when the map mounts and whenever the inspected element
 * changes, so it lives in a small map child instead of an imperative lookup.
 */
const FitExtent = ({ bounds }: { bounds: L.LatLngBounds }) => {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds);
  }, [map, bounds]);
  return null;
};

/**
 * Rendered preview of the selected layer or feature type, as asked for in issue #676.
 *
 * The panel builds the OGC request for the element itself - a GetMap of the layer or a
 * GetFeature of the feature type within the advertised extent - and asks the service
 * directly. A service which is secured by rules is asked through the mrmap security
 * proxy, which authenticates upstream with the stored credentials and applies the
 * spatial rules; a service without rules is asked straight at its stored operation
 * url. Nothing is rendered before a request can succeed, and an unmounted panel
 * aborts the in-flight request.
 */
export const ElementPreview = ({
  protocol,
  element,
  service,
}: {
  protocol: PreviewProtocol;
  element?: RaRecord;
  service?: RaRecord;
}) => {
  const translate = useTranslate();

  // an element which is inspected away from the screen of its service does not
  // carry the service, so it is read from the relation of the element alone then
  const elementServiceId = element?.service?.id
    ? String((element.service as RaRecord).id)
    : undefined;
  const serviceId = service?.id ? String(service.id) : elementServiceId;
  const serviceRelation = useGetOne(
    protocol === "WMS" ? "WebMapService" : "WebFeatureService",
    {
      id: elementServiceId,
      meta: { jsonApiParams: { include: "operationUrls" } },
    },
    { enabled: service === undefined && elementServiceId !== undefined },
  );
  const resolvedService = service ?? serviceRelation.data;

  const selection = element?.identifier ? String(element.identifier) : undefined;
  const secured = Boolean(
    resolvedService?.isSecured || resolvedService?.isSpatialSecured,
  );
  const version = resolvedService?.version ? String(resolvedService.version) : undefined;

  const bounds = useMemo(
    () => getCoverageBounds(element?.bboxLatLon ?? element?.bbox),
    [element],
  );
  const extent = useMemo(
    () =>
      bounds
        ? [
            bounds.getWest(),
            bounds.getSouth(),
            bounds.getEast(),
            bounds.getNorth(),
          ]
        : undefined,
    [bounds],
  );
  const outputFormat = protocol === "WMS" ? "image/png" : geoJsonOutputFormat(element);

  const base = useMemo(
    () =>
      serviceId === undefined
        ? undefined
        : secured
          ? proxyUrl(protocol, serviceId)
          : remoteOperationUrl(resolvedService, protocol),
    [protocol, secured, serviceId, resolvedService],
  );
  const url = useMemo(() => {
    if (!base || !selection || !version || !extent || !outputFormat) {
      return undefined;
    }
    return protocol === "WMS"
      ? buildWmsGetMapUrl(base, { identifier: selection, version, extent })
      : buildWfsGetFeatureUrl(base, {
          identifier: selection,
          version,
          extent,
          outputFormat,
        });
  }, [base, protocol, selection, version, extent, outputFormat]);

  const headers = useMemo(
    () => (url && secured ? requestHeaders(url) : undefined),
    [url, secured],
  );
  // an unsecured service is asked by the browser straight from its origin; the
  // picture of a remote origin needs no token and a plain image request asks no
  // cross-origin permission, so it is used as it is
  const remoteImage = protocol === "WMS" && !secured;

  const picture = useQuery<Blob, Error>({
    queryKey: ["elementPreview", url?.href],
    enabled: protocol === "WMS" && url !== undefined && !remoteImage,
    retry: false,
    gcTime: 0,
    staleTime: 0,
    queryFn: async ({ signal }) => {
      const response = await fetch(String(url), { signal, headers });
      if (!response.ok) throw new Error("unavailable");
      const blob = await response.blob();
      if (!blob.type.startsWith("image/")) throw new Error("format");
      return blob;
    },
  });
  const blobUrl = useMemo(
    () => (picture.data ? URL.createObjectURL(picture.data) : undefined),
    [picture.data],
  );
  useEffect(() => {
    if (!blobUrl) {
      return;
    }
    return () => {
      URL.revokeObjectURL(blobUrl);
    };
  }, [blobUrl]);

  const features = useQuery<FeatureCollection, Error>({
    queryKey: ["elementPreview", url?.href],
    enabled: protocol === "WFS" && url !== undefined,
    retry: false,
    gcTime: 0,
    staleTime: 0,
    queryFn: async ({ signal }) => {
      const response = await fetch(String(url), { signal, headers });
      if (!response.ok) throw new Error("unavailable");
      const body = await response.text();
      // an OGC exception report or a GML answer is not readable in the browser
      if (body.trimStart().startsWith("<")) throw new Error("format");
      try {
        return JSON.parse(body) as FeatureCollection;
      } catch {
        throw new Error("malformed");
      }
    },
  });

  if (!element || !selection || serviceId === undefined) {
    return null;
  }

  const failed =
    (protocol === "WMS" && !remoteImage && picture.error) ||
    (protocol === "WFS" && features.error);
  // a disabled useGetOne stays pending, so only a service which is really asked for waits
  const awaitingService =
    service === undefined && elementServiceId !== undefined && serviceRelation.isPending;
  const isFetching =
    serviceRelation.isFetching ||
    (protocol === "WMS" && !remoteImage && picture.isFetching) ||
    (protocol === "WFS" && features.isFetching);
  const image = remoteImage && url ? url.href : blobUrl;
  const collection = protocol === "WFS" ? features.data : undefined;
  const showsFeatures = Boolean(
    collection && collection.features.length > 0,
  );
  const retry = protocol === "WMS" ? picture.refetch : features.refetch;

  return (
    <>
      {serviceRelation.error ? (
        <Alert
          severity="error"
          action={
            <Button onClick={() => void serviceRelation.refetch()}>
              {translate("ra.action.retry")}
            </Button>
          }
        >
          {translate("layerInspection.loadError")}
        </Alert>
      ) : awaitingService ? (
        <LinearProgress aria-label={translate("livePreview.loading")} />
      ) : !base ? (
        <Alert severity="warning">
          {translate("livePreview.errors.operation")}
        </Alert>
      ) : protocol === "WFS" && !outputFormat ? (
        <Alert severity="warning">
          {translate("livePreview.errors.format")}
        </Alert>
      ) : !extent || !bounds ? (
        <Alert severity="info">{translate("layerInspection.noPreviewExtent")}</Alert>
      ) : !version ? (
        <Alert severity="warning">
          {translate("livePreview.errors.operation")}
        </Alert>
      ) : isFetching ? (
        <LinearProgress aria-label={translate("livePreview.loading")} />
      ) : failed ? (
        <Alert
          severity="error"
          action={
            <Button onClick={() => void retry()}>{translate("ra.action.retry")}</Button>
          }
        >
          {translate("layerInspection.previewError")}
        </Alert>
      ) : protocol === "WMS" ? (
        image ? (
          <GeoJsonMap id={`element-preview-${String(element.id)}`}>
            <FitExtent bounds={bounds} />
            <ImageOverlay url={image} bounds={bounds} />
          </GeoJsonMap>
        ) : (
          <LinearProgress aria-label={translate("livePreview.loading")} />
        )
      ) : showsFeatures && collection ? (
        <Stack spacing={0.5}>
          <GeoJsonMap id={`element-preview-${String(element.id)}`}>
            <FeatureGroupEditor geoJson={collection} editable={false} />
          </GeoJsonMap>
          <Typography variant="caption" color="text.secondary">
            {translate("livePreview.limited", { count: FEATURE_LIMIT })}
          </Typography>
        </Stack>
      ) : (
        <Alert severity="info">{translate("livePreview.emptyFeatures")}</Alert>
      )}
    </>
  );
};

export default ElementPreview;
