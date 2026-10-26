import type { Feature, FeatureCollection, GeoJsonProperties } from "geojson";
import type L from "leaflet";

import { Fragment, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslate } from "react-admin";
import { createPortal } from "react-dom";
import { GeoJSON, useMap } from "react-leaflet";

import {
  Box,
  Divider,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { resolveOperationAuthentication } from "../../ows-lib/OwsContext/authentication";
import { getRenderableGetFeatureOperation } from "../../ows-lib/OwsContext/capabilities";
import { OWSResource } from "../../ows-lib/OwsContext/core";
import {
  prepareViewportGetFeatureUrl,
  WFS_VIEWER_FEATURE_LIMIT,
} from "../../ows-lib/OwsContext/utils";
import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase";
import { useMapViewerBase } from "../MapViewer/MapViewerBase";

const VIEWPORT_DEBOUNCE_MS = 300;

// vectors are drawn in a pane of their own, above the raster overlays of the WMS layers
// (overlayPane sits at 400) so that the drawn feature order is the panes, not the mount order
const FEATURE_PANE = "wfsFeaturePane";

// the drawn vectors keep the ratio of their style: a layer blended down dims its stroke, its fill
// and its point symbols together, while a layer at full opacity draws exactly as it did before
const VECTOR_STYLE = {
  color: "#1976d2",
  weight: 2,
  fillColor: "#1976d2",
  fillOpacity: 0.15,
};

const vectorStyle = (opacity: number) => ({
  ...VECTOR_STYLE,
  opacity,
  fillOpacity: VECTOR_STYLE.fillOpacity * opacity,
});

interface FeatureRequest {
  feature: OWSResource;
  url: URL;
  headers?: Headers;
  authenticationError?: string;
}

interface FeatureStatus {
  title: string;
  limited: boolean;
  empty: boolean;
}

interface Selection {
  title: string;
  properties: GeoJsonProperties;
}

/** Recognize a WFS exception report, which some servers also answer with on a 200. */
const getServiceExceptionMessage = (body: string): string | undefined => {
  if (!body.trimStart().startsWith("<")) return undefined;

  try {
    const document = new DOMParser().parseFromString(body, "application/xml");
    const nodes = Array.from(document.getElementsByTagName("*"));
    const exception = nodes.find(
      (element) =>
        element.localName === "Exception" ||
        element.localName === "ServiceException",
    );
    const report = nodes.find((element) => element.localName === "ExceptionReport");
    if (exception === undefined && report === undefined) return undefined;
    const code =
      exception?.getAttribute("code") ?? report?.getAttribute("code") ?? "";
    const text =
      nodes.find((element) => element.localName === "ExceptionText")?.textContent?.trim() ||
      exception?.textContent?.trim() ||
      exception?.getAttribute("locator") ||
      report?.getAttribute("locator") ||
      "";
    if (code && text) return `${code}: ${text}`;
    return text || code || "OGC service exception";
  } catch {
    return undefined;
  }
};

/** A selected feature's properties; values are only ever shown as text, never as markup. */
const propertyValue = (value: unknown): ReactNode => {
  if (value === null) return "null";
  if (value === undefined) return "—";
  if (typeof value === "object")
    return (
      <Box
        component="pre"
        sx={{ m: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: "0.75rem" }}
      >
        {JSON.stringify(value, null, 2)}
      </Box>
    );
  return String(value);
};

const FeatureOverlay = ({
  request,
  onSelect,
  onStatus,
}: {
  request: FeatureRequest;
  onSelect: (selection: Selection | null) => void;
  onStatus: (id: string, status: FeatureStatus | undefined) => void;
}) => {
  const translate = useTranslate();
  const { reportMapLoading, removeMapLoading, opacityOf } = useMapViewerBase();
  const startedAt = useRef(performance.now());
  const { feature, url, headers, authenticationError } = request;
  const loadingId = `feature:${url.href}`;
  const title = feature.properties.title ?? url.searchParams.get("TYPENAME") ?? url.href;
  const opacity = opacityOf([feature]);
  const drawn = useRef<L.GeoJSON>(null);

  const query = useQuery<FeatureCollection>({
    queryKey: [
      "viewerFeatures",
      url.href,
      headers ? Array.from(headers) : undefined,
      authenticationError,
    ],
    enabled: !authenticationError,
    retry: false,
    gcTime: 0,
    queryFn: async ({ signal }) => {
      const response = await fetch(url.href, {
        signal,
        ...(headers && { headers, credentials: "omit" as RequestCredentials }),
        redirect: headers ? ("error" as RequestRedirect) : "follow",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const body = await response.text();
      const exception = getServiceExceptionMessage(body);
      if (exception !== undefined) throw new Error(exception);
      let collection: unknown;
      try {
        collection = JSON.parse(body);
      } catch {
        throw new Error("no GeoJSON response");
      }
      if (
        typeof collection !== "object" ||
        collection === null ||
        (collection as FeatureCollection).type !== "FeatureCollection" ||
        !Array.isArray((collection as FeatureCollection).features)
      )
        throw new Error("no GeoJSON feature collection");
      return collection as FeatureCollection;
    },
  });

  useEffect(() => {
    const timing = performance.now() - startedAt.current;
    if (authenticationError) {
      reportMapLoading(
        loadingId,
        "error",
        {
          message: translate(`viewerAuth.${authenticationError}`),
          features: [feature],
        },
        timing,
      );
    } else if (query.isFetching) {
      reportMapLoading(loadingId, "loading");
    } else if (query.error) {
      reportMapLoading(
        loadingId,
        "error",
        {
          message:
            query.error instanceof Error ? query.error.message : String(query.error),
          features: [feature],
        },
        timing,
      );
    } else if (query.data) {
      reportMapLoading(loadingId, "ready", undefined, timing);
    }
  }, [
    authenticationError,
    query.isFetching,
    query.error,
    query.data,
    loadingId,
    feature,
    reportMapLoading,
    translate,
  ]);

  useEffect(() => {
    return () => removeMapLoading(loadingId);
  }, [loadingId, removeMapLoading]);

  // the status belongs to the request that answered it: an obsolete viewport request unmounts
  // before it could report, so replaced results never accumulate on the map
  useEffect(() => {
    if (query.data === undefined) {
      onStatus(loadingId, undefined);
      return;
    }
    onStatus(loadingId, {
      title,
      limited: query.data.features.length >= WFS_VIEWER_FEATURE_LIMIT,
      empty: query.data.features.length === 0,
    });
  }, [query.data, loadingId, title, onStatus]);

  useEffect(() => {
    return () => onStatus(loadingId, undefined);
  }, [loadingId, onStatus]);

  // a drawn layer keeps the style it was created with, so the opacity a user blends a layer to goes
  // to the layer itself; its features stay loaded for it (#750)
  useEffect(() => {
    drawn.current?.setStyle(vectorStyle(opacity));
  }, [opacity]);

  if (query.data === undefined) return null;

  return (
    <GeoJSON
      ref={drawn}
      key={url.href}
      data={query.data}
      pane={FEATURE_PANE}
      style={vectorStyle(opacity)}
      onEachFeature={(layerFeature: Feature, layer) => {
        const select = () => onSelect({ title, properties: layerFeature.properties ?? {} });
        layer.on("click", select);
        // the drawn path is reachable by keyboard, mirroring the live preview's feature display
        layer.on("add", () => {
          const element = (layer as { getElement?: () => HTMLElement | undefined }).getElement?.();
          element?.setAttribute("tabindex", "0");
          element?.setAttribute("role", "button");
          element?.setAttribute("aria-label", title);
        });
        layer.on("keypress", (event) => {
          const originalEvent = (event as { originalEvent?: KeyboardEvent }).originalEvent;
          if (originalEvent?.key === "Enter") {
            originalEvent.preventDefault();
            select();
          }
        });
      }}
    />
  );
};

/**
 * Renders the active WFS feature types of the context for the current viewport. Every type keeps
 * its own bounded request: the negotiated version, type name and GeoJSON format stay exact, the
 * viewport replaces the bounding box and the advertised count parameter bounds the response.
 * A failing type is reported while the working layers keep rendering.
 */
const WebFeatureServiceControl = () => {
  const map = useMap();
  const translate = useTranslate();
  const { owsContext } = useOwsContextBase();
  const [bounds, setBounds] = useState(() => map?.getBounds());
  const [selection, setSelection] = useState<Selection | null>(null);
  const [statuses, setStatuses] = useState<Record<string, FeatureStatus>>({});

  useEffect(() => {
    if (!map) return;

    const updateBounds = () => setBounds(map.getBounds());

    let viewportUpdateTimeout: ReturnType<typeof setTimeout> | undefined;
    const scheduleViewportUpdate = () => {
      if (viewportUpdateTimeout) {
        clearTimeout(viewportUpdateTimeout);
      }
      viewportUpdateTimeout = setTimeout(updateBounds, VIEWPORT_DEBOUNCE_MS);
    };

    updateBounds();
    map.on("viewreset moveend zoomend resize", scheduleViewportUpdate);
    return () => {
      map.off("viewreset moveend zoomend resize", scheduleViewportUpdate);
      if (viewportUpdateTimeout) {
        clearTimeout(viewportUpdateTimeout);
      }
    };
  }, [map]);

  // vectors draw above the raster overlays, whichever mounted first
  useEffect(() => {
    if (map && map.getPane(FEATURE_PANE) === undefined) {
      const pane = map.createPane(FEATURE_PANE);
      pane.style.zIndex = "460";
    }
  }, [map]);

  const requests = useMemo(() => {
    if (bounds === undefined) return [];
    const bbox: [number, number, number, number] = [
      bounds.getWest(),
      bounds.getSouth(),
      bounds.getEast(),
      bounds.getNorth(),
    ];
    return owsContext
      .getWfsFeatureRequests(
        (feature) =>
          feature.properties.active === true &&
          getRenderableGetFeatureOperation(feature) !== undefined,
      )
      .map(({ feature }): FeatureRequest | undefined => {
        const renderable = getRenderableGetFeatureOperation(feature);
        if (renderable === undefined) return undefined;
        const url = prepareViewportGetFeatureUrl(
          renderable.operation,
          renderable.format,
          bbox,
          WFS_VIEWER_FEATURE_LIMIT,
        );
        const authentication = resolveOperationAuthentication(
          owsContext,
          renderable.operation,
          url.href,
        );
        return {
          feature,
          url,
          headers: authentication.headers,
          authenticationError: authentication.error,
        };
      })
      .filter((request): request is FeatureRequest => request !== undefined);
  }, [bounds, owsContext]);

  const onStatus = useCallback(
    (id: string, status: FeatureStatus | undefined) => {
      setStatuses((previous) => {
        if (status === undefined) {
          if (previous[id] === undefined) return previous;
          const next = { ...previous };
          delete next[id];
          return next;
        }
        if (
          previous[id] !== undefined &&
          previous[id].title === status.title &&
          previous[id].limited === status.limited &&
          previous[id].empty === status.empty
        )
          return previous;
        return { ...previous, [id]: status };
      });
    },
    [],
  );

  const reportedStatuses = Object.values(statuses).filter(
    (status) => status.limited || status.empty,
  );

  return (
    <Fragment>
      {requests.map((request) => (
        <FeatureOverlay
          key={request.url.href}
          request={request}
          onSelect={setSelection}
          onStatus={onStatus}
        />
      ))}
      {map &&
        createPortal(
          <Box
            sx={{
              position: "absolute",
              zIndex: 1000,
              right: 16,
              bottom: 30,
              maxWidth: "min(400px, calc(100% - 32px))",
              pointerEvents: "none",
            }}
          >
            {reportedStatuses.length > 0 && (
              <Stack spacing={0.5}>
                {reportedStatuses.map((status, index) => (
                  <Typography
                    key={`${status.title}-${index}`}
                    variant="caption"
                    role="status"
                    sx={{
                      display: "block",
                      bgcolor: "background.paper",
                      color: "text.secondary",
                      px: 1,
                      borderRadius: 1,
                    }}
                  >
                    {status.limited
                      ? translate("viewerFeatures.limited", {
                          title: status.title,
                          count: WFS_VIEWER_FEATURE_LIMIT,
                        })
                      : translate("viewerFeatures.empty", { title: status.title })}
                  </Typography>
                ))}
              </Stack>
            )}
          </Box>,
          map.getContainer(),
        )}
      {selection &&
        map &&
        createPortal(
          <Box
            sx={{
              position: "absolute",
              zIndex: 1100,
              right: 16,
              top: 16,
              maxWidth: "min(400px, calc(100% - 32px))",
            }}
          >
            <Paper
              elevation={6}
              sx={{
                bgcolor: "background.paper",
                color: "text.primary",
                borderRadius: 2,
                overflow: "hidden",
              }}
            >
              <Stack spacing={1} sx={{ p: 2 }}>
                <Stack direction="row" sx={{ alignItems: "center" }}>
                  <Typography variant="h6" sx={{ flex: 1 }}>
                    {translate("viewerFeatures.title")}
                  </Typography>
                  <IconButton
                    size="small"
                    aria-label={translate("viewerFeatures.close")}
                    onClick={() => setSelection(null)}
                  >
                    ×
                  </IconButton>
                </Stack>
                <Typography variant="subtitle2" sx={{ overflowWrap: "anywhere" }}>
                  {selection.title}
                </Typography>
              </Stack>
              <Divider />
              <TableContainer sx={{ maxHeight: "50vh" }}>
                <Table size="small">
                  <TableBody>
                    {Object.entries(selection.properties ?? {}).map(([name, value]) => (
                      <TableRow key={name}>
                        <TableCell
                          component="th"
                          scope="row"
                          sx={{ overflowWrap: "anywhere", width: "40%" }}
                        >
                          {name}
                        </TableCell>
                        <TableCell sx={{ overflowWrap: "anywhere" }}>
                          {propertyValue(value)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
          </Box>,
          map.getContainer(),
        )}
    </Fragment>
  );
};

export default WebFeatureServiceControl;

