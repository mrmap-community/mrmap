import { useEffect, useMemo } from "react";
import { useTranslate, type RaRecord } from "react-admin";
import { ImageOverlay, useMap } from "react-leaflet";

import { Alert, Button, LinearProgress, Stack, Typography } from "@mui/material";

import FeatureGroupEditor from "../../../Input/FeatureGroupEditor";
import GeoJsonMap from "../../../MapContainer/GeoJsonMap";
import { extentBounds, validExtent } from "../../../MapViewer/utils";
import { usePreview } from "./LivePreview/usePreview";

/**
 * The preview always shows the element's advertised extent. The leaflet bounds object must be
 * fitted when the map mounts and whenever the inspected element changes, so it lives in a small
 * map child instead of an imperative map lookup in the panel body.
 */
const FitExtent = ({ bounds }: { bounds: ReturnType<typeof extentBounds> }) => {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds);
  }, [map, bounds]);
  return null;
};

/**
 * Rendered preview of the selected layer or feature type, as asked for in issue #676.
 *
 * The extent drives the view and is read from the stored element definition through the
 * discovery call. The rendered content comes from the same permission-gated `preview`
 * operation the live preview uses, so the panel never speaks to a service origin directly:
 * a WMS layer is rendered as its advertised transparent image, a WFS feature type as the
 * features inside the extent. Nothing is requested until both calls can succeed, and an
 * unmounted panel aborts the in-flight requests.
 */
export const ElementPreview = ({
  protocol,
  record,
}: {
  protocol: "WMS" | "WFS";
  record?: RaRecord;
}) => {
  const translate = useTranslate();
  const serviceId = record?.service?.id ? String(record.service.id) : undefined;
  const selection = record?.identifier ? String(record.identifier) : undefined;
  const enabled = Boolean(serviceId && selection);

  const discovery = usePreview(
    protocol,
    serviceId ?? "",
    { selection: selection ?? "" },
    enabled,
  );
  const extent = discovery.data?.configuration?.extent;
  const hasExtent = Boolean(extent && validExtent(extent));
  const rendering = usePreview(
    protocol,
    serviceId ?? "",
    { selection: selection ?? "", bbox: extent ? extent.join(",") : "" },
    enabled && hasExtent,
  );
  const bounds = useMemo(
    () => (extent && validExtent(extent) ? extentBounds(extent) : undefined),
    [extent],
  );

  if (!enabled || !record) {
    return null;
  }

  const image = protocol === "WMS" ? rendering.data?.image : undefined;
  const features = protocol === "WFS" ? rendering.data?.features : undefined;
  const showsFeatures = Boolean(features && features.features.length > 0);
  const isRendering = Boolean(hasExtent) && (rendering.isPending || rendering.isFetching);

  return (
    <>
      {!discovery.supported ? (
        <Alert severity="warning">{translate("livePreview.errors.operation")}</Alert>
      ) : discovery.error ? (
        <Alert
          severity="error"
          action={
            <Button onClick={() => discovery.refetch()}>
              {translate("ra.action.retry")}
            </Button>
          }
        >
          {translate("livePreview.errors.discovery")}
        </Alert>
      ) : discovery.isFetching ? (
        <LinearProgress aria-label={translate("livePreview.loading")} />
      ) : !hasExtent || !bounds ? (
        <Alert severity="info">{translate("layerInspection.noPreviewExtent")}</Alert>
      ) : rendering.error ? (
        <Alert
          severity="error"
          action={
            <Button onClick={() => rendering.refetch()}>
              {translate("ra.action.retry")}
            </Button>
          }
        >
          {translate("layerInspection.previewError")}
        </Alert>
      ) : isRendering ? (
        <LinearProgress aria-label={translate("livePreview.loading")} />
      ) : image ? (
        <GeoJsonMap id={`element-preview-${String(record.id)}`}>
          <FitExtent bounds={bounds} />
          <ImageOverlay url={image} bounds={bounds} />
        </GeoJsonMap>
      ) : showsFeatures && features ? (
        <Stack spacing={0.5}>
          <GeoJsonMap id={`element-preview-${String(record.id)}`}>
            <FeatureGroupEditor geoJson={features} editable={false} />
          </GeoJsonMap>
          <Typography variant="caption" color="text.secondary">
            {translate("livePreview.limited", { count: rendering.data?.limit ?? 0 })}
          </Typography>
        </Stack>
      ) : (
        <Alert severity="info">{translate("livePreview.emptyFeatures")}</Alert>
      )}
    </>
  );
};

export default ElementPreview;
