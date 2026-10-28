import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import type { RaRecord } from "react-admin";
import { useRecordContext, useResourceContext, useTranslate } from "react-admin";

import { Alert, Box, Button, LinearProgress, Stack, Typography } from "@mui/material";

import { unsupportedReasonLabel } from "../../../../ows-lib/OwsContext/capabilities";
import { OwsContextBase, useOwsContextBase } from "../../../../react-ows-lib/ContextProvider/OwsContextBase";
import MapPreview from "../../../MapViewer/MapPreview";
import { MapViewerBase } from "../../../MapViewer/MapViewerBase";
import { getCoverageBounds } from "../Explorer/coverage";
import { activateElement, advertisedExtent, elementCapabilitiesUrl, sessionHeader, unsupportedOf } from "./singleLayerContext";

/** The extent stored for an element, as the [west, south, east, north] the viewer navigates with. */
const coverageExtent = (element?: RaRecord): number[] | undefined => {
  const bounds = getCoverageBounds(element?.bboxLatLon ?? element?.bbox);
  if (bounds === undefined) return undefined;
  return [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()];
};

/**
 * The preview of one element, rendered the way the map viewer renders it.
 *
 * The element answers the url of the capabilities document which advertises it alone, so the preview
 * is seeded with that document and asks exactly one resource; the protocol is read of the document
 * instead of being assumed from the resource. Everything the viewer does with a document it does
 * here too: the operations of the activated element are asked for the viewport the map shows, so
 * panning and zooming re-asks the service the way the viewer does, the stored credentials of a
 * secured service stay on the server side of the proxy which answers the document, and the spatial
 * rules of the requesting user are applied to every answer. A layer is drawn as the image of its
 * GetMap, a feature type as the vector features its GetFeature answers in GeoJSON.
 */
const SingleElementPreview = ({ height }: { height: number | string }): ReactNode => {
  const element = useRecordContext();
  const translate = useTranslate();
  const { addServiceByUrl, isLoading, errorMessage, owsContext } = useOwsContextBase();
  const [attempt, setAttempt] = useState(0);

  const url = useMemo(() => elementCapabilitiesUrl(element), [element]);
  const stored = useMemo(() => coverageExtent(element), [element]);
  const href = url?.href;

  useEffect(() => {
    if (href === undefined) return;
    // the provider keeps the header for the origin of this document alone and gives it to the
    // operations of the document itself; the hook below only decides which of them are asked
    addServiceByUrl(href, sessionHeader(), activateElement(stored, href));
  }, [href, stored, addServiceByUrl, attempt]);

  if (url === undefined) {
    return <Alert severity="info">{translate("layerInspection.previewNoCapabilities")}</Alert>;
  }

  // the area the map is navigated to: what the element advertises in the document it arrived with,
  // and what the registry stores for it as long as that document is not there
  const area = advertisedExtent(owsContext) ?? stored;
  const reasons = unsupportedOf(owsContext);

  return (
    <Stack spacing={1}>
      {isLoading && (
        <Box role="status">
          <Typography variant="body2">{translate("layerInspection.previewLoading")}</Typography>
          <LinearProgress />
        </Box>
      )}
      {errorMessage !== undefined && (
        <Alert
          severity="error"
          action={
            <Button size="small" onClick={() => setAttempt((previous) => previous + 1)}>
              {translate("ra.action.retry")}
            </Button>
          }
        >
          {translate("layerInspection.previewError")} {errorMessage}
        </Alert>
      )}
      {reasons.length > 0 && (
        <Alert severity="warning">
          {translate("viewerUnsupported.resource")}{" "}
          {reasons.map((reason) => unsupportedReasonLabel(reason, translate)).join("; ")}
        </Alert>
      )}
      <MapViewerBase previewExtent={area}>
        <MapPreview height={height} />
      </MapViewerBase>
    </Stack>
  );
};

/**
 * The live preview of the inspected layer or feature type, asked by the service which owns it.
 *
 * It reads the element from the record context, which is what lets the inspection of a service and
 * the aside of the layer list show the very same preview: both hand it the element as their record.
 * The document of one element is a state of its own, so the preview keeps a context provider of its
 * own around the map: the map the user has open next door is not touched by it and the preview of
 * another element starts from an empty document instead of keeping the layers of the one before.
 */
const ElementLivePreview = ({ height = 380 }: { height?: number | string }): ReactNode => {
  const element = useRecordContext();
  const resource = useResourceContext();
  if (element === undefined) return null;
  return (
    <OwsContextBase key={`${resource ?? "element"}:${String(element.id)}`}>
      <SingleElementPreview height={height} />
    </OwsContextBase>
  );
};

export default ElementLivePreview;
