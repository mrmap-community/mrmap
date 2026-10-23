import { Fragment, ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useTranslate } from "react-admin";
import { createPortal } from "react-dom";
import { Marker, Tooltip, useMap, useMapEvent } from "react-leaflet";

import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Alert,
  Box,
  Button,
  Divider,
  IconButton,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { DomEvent, point, type LatLng } from "leaflet";
import proj4 from "proj4";

import { resolveOperationAuthentication } from "../../ows-lib/OwsContext/authentication";
import { OptimizedUrlsMap } from "../../ows-lib/OwsContext/core";
import { updateOrAppendSearchParam } from "../../ows-lib/OwsContext/utils";
import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase";
import { useMapViewerBase } from "../MapViewer/MapViewerBase";
import { FeatureInfoResult } from "../Resource/Generic/ServiceShow/LivePreview/LivePreview";
import { AuthImageOverlay } from "./AuthImageOverlay";

const VIEWPORT_DEBOUNCE_MS = 300;

export interface Tile {
  leafletTile: ReactNode;
  getMapUrl?: URL;
  getFeatureinfoUrl?: URL;
}

const FeatureInfoRequest = ({ request }: { request: OptimizedUrlsMap }) => {
  const { owsContext } = useOwsContextBase();
  const translate = useTranslate();
  const { headers, error: authError } = resolveOperationAuthentication(
    owsContext,
    request.operations[0],
    request.url.href,
  );
  const query = useQuery({
    queryKey: [
      "viewerFeatureInfo",
      request.url.href,
      headers ? Array.from(headers) : undefined,
      authError,
    ],
    enabled: !authError,
    retry: false,
    gcTime: 0,
    queryFn: async ({ signal }) => {
      const response = await fetch(request.url.href, {
        headers,
        signal,
        redirect: "error",
        credentials: "omit",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return {
        text: await response.text(),
        contentType: response.headers.get("content-type") ?? "text/plain",
      };
    },
  });
  if (authError)
    return (
      <Alert severity="error">{translate(`viewerAuth.${authError}`)}</Alert>
    );
  const layers =
    request.url.searchParams.get("QUERY_LAYERS") ??
    request.url.searchParams.get("query_layers") ??
    "Feature Info";
  return (
    <Accordion
      defaultExpanded
      disableGutters
      elevation={0}
      sx={{
        border: 1,
        borderColor: "divider",
        "&:before": { display: "none" },
      }}
    >
      <AccordionSummary expandIcon={<span>⌄</span>}>
        <Typography variant="subtitle2" sx={{ overflowWrap: "anywhere" }}>
          {layers}
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={1}>
          {query.isPending && (
            <>
              <Typography variant="body2">
                {translate("viewerFeatureInfo.loading")}
              </Typography>
              <LinearProgress />
            </>
          )}
          {query.error && (
            <Stack spacing={0.5}>
              <Alert
                severity="error"
                action={
                  <Button onClick={() => query.refetch()}>
                    {translate("ra.action.retry")}
                  </Button>
                }
              >
                {translate("viewerFeatureInfo.error")}
              </Alert>
              <Link
                to={request.url.href}
                target="_blank"
                rel="noopener noreferrer"
              >
                {translate("viewerFeatureInfo.raw")}
              </Link>
            </Stack>
          )}
          {query.data && <FeatureInfoResult {...query.data} paginate />}
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
};

const WebMapServiceControl = () => {
  const map = useMap();
  const translate = useTranslate();
  const [bounds, setBounds] = useState(map?.getBounds());
  const [size, setSize] = useState(map?.getSize());
  const { owsContext } = useOwsContextBase();
  const { selectedCrs, atomicGetMapUrls, atomicGetFeatureInfoUrls } =
    useMapViewerBase();
  const [position, setPosition] = useState<LatLng | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [identifying, setIdentifying] = useState(false);
  const [identifyViewport, setIdentifyViewport] = useState<{
    bbox: [number, number, number, number];
    size: { x: number; y: number };
  }>();
  const [layerPoint, setLayerPoint] = useState<{ x: number; y: number } | null>(
    null,
  );

  const bbox = useMemo<[number, number, number, number]>(() => {
    const sw = bounds?.getSouthWest();
    const ne = bounds?.getNorthEast();
    let minXy = point(sw.lng, sw.lat);
    let maxXy = point(ne.lng, ne.lat);

    if (selectedCrs.stringRepresentation !== "EPSG:4326") {
      const proj = proj4("EPSG:4326", selectedCrs.wkt);
      minXy = proj.forward(minXy);
      maxXy = proj.forward(maxXy);
    }

    return [minXy.x, minXy.y, maxXy.x, maxXy.y];
  }, [bounds, selectedCrs]);

  const tiles = useMemo(() => {
    const _tiles: Tile[] = [];

    if (bounds === undefined || size === undefined) {
      return _tiles;
    }

    const getMapUrls = [...atomicGetMapUrls].reverse();

    getMapUrls.forEach((atomicGetMapUrl) => {
      const params = atomicGetMapUrl.url.searchParams;
      const version = params.get("version") ?? params.get("VERSION");
      if (version === "1.3.0") {
        if (selectedCrs.isXyOrder) {
          // no axis order correction needed.
          updateOrAppendSearchParam(
            params,
            "BBOX",
            `${bbox[0]},${bbox[1]},${bbox[2]},${bbox[3]}`,
          );
        } else {
          updateOrAppendSearchParam(
            params,
            "BBOX",
            `${bbox[1]},${bbox[0]},${bbox[3]},${bbox[2]}`,
          );
        }
        updateOrAppendSearchParam(
          params,
          "CRS",
          selectedCrs.stringRepresentation,
        );
      } else {
        // always minx,miny,maxx,maxy (minLng,minLat,maxLng,maxLat)
        updateOrAppendSearchParam(
          params,
          "BBOX",
          `${bbox[0]},${bbox[1]},${bbox[2]},${bbox[3]}`,
        );
        updateOrAppendSearchParam(
          params,
          "SRS",
          selectedCrs.stringRepresentation,
        );
      }
      updateOrAppendSearchParam(params, "WIDTH", size.x.toString());
      updateOrAppendSearchParam(params, "HEIGHT", size.y.toString());
      if (![...params.keys()].some((key) => key.toUpperCase() === "STYLES")) {
        updateOrAppendSearchParam(params, "STYLES", "");
      }
      const authentication = resolveOperationAuthentication(
        owsContext,
        atomicGetMapUrl.operations[0],
        atomicGetMapUrl.url.href,
      );
      _tiles.push({
        leafletTile: (
          <AuthImageOverlay
            key={atomicGetMapUrl.url.href}
            bounds={bounds}
            interactive={true}
            optimiuedUrl={atomicGetMapUrl}
            auth={authentication.headers}
            authenticationError={authentication.error}
          />
        ),
        getMapUrl: atomicGetMapUrl.url,
        getFeatureinfoUrl: undefined,
      });
    });

    return _tiles;
  }, [bounds, size, atomicGetMapUrls, selectedCrs, owsContext]);

  const getFeatureInfoUrls = useMemo(() => {
    if (
      layerPoint &&
      position &&
      identifyViewport &&
      atomicGetFeatureInfoUrls.length > 0
    ) {
      const { bbox, size } = identifyViewport;
      const getFeatureInfoUrls = [...atomicGetFeatureInfoUrls]
        .reverse()
        .map((request) => ({ ...request, url: new URL(request.url.href) }));
      getFeatureInfoUrls.forEach((atomicGetFeatureInfoUrl) => {
        const params = atomicGetFeatureInfoUrl.url.searchParams;
        const version = params.get("version") ?? params.get("VERSION");
        // WMS 1.3.0 asks for the pixel through I/J, earlier versions through X/Y;
        // sending the foreign pair makes strict servers reject or misplace the query.
        if (version === "1.3.0") {
          updateOrAppendSearchParam(
            params,
            "I",
            layerPoint.x.toFixed(0).toString(),
          );
          updateOrAppendSearchParam(
            params,
            "J",
            layerPoint.y.toFixed(0).toString(),
          );
          params.delete("X");
          params.delete("Y");
        } else {
          updateOrAppendSearchParam(
            params,
            "X",
            layerPoint.x.toFixed(0).toString(),
          );
          updateOrAppendSearchParam(
            params,
            "Y",
            layerPoint.y.toFixed(0).toString(),
          );
          params.delete("I");
          params.delete("J");
        }
        updateOrAppendSearchParam(params, "WIDTH", size.x.toString());
        updateOrAppendSearchParam(params, "HEIGHT", size.y.toString());
        if (![...params.keys()].some((key) => key.toUpperCase() === "LAYERS")) {
          updateOrAppendSearchParam(
            params,
            "LAYERS",
            params.get("QUERY_LAYERS") ?? params.get("query_layers") ?? "",
          );
        }
        updateOrAppendSearchParam(
          params,
          "INFO_FORMAT",
          params.get("INFO_FORMAT") ??
            params.get("info_format") ??
            "application/json",
        );
        updateOrAppendSearchParam(
          params,
          "FEATURE_COUNT",
          params.get("FEATURE_COUNT") ?? params.get("feature_count") ?? "10",
        );
        if (![...params.keys()].some((key) => key.toUpperCase() === "STYLES")) {
          updateOrAppendSearchParam(params, "STYLES", "");
        }

        if (version === "1.3.0") {
          if (selectedCrs.isXyOrder) {
            // no axis order correction needed.
            updateOrAppendSearchParam(
              params,
              "BBOX",
              `${bbox[0]},${bbox[1]},${bbox[2]},${bbox[3]}`,
            );
          } else {
            updateOrAppendSearchParam(
              params,
              "BBOX",
              `${bbox[1]},${bbox[0]},${bbox[3]},${bbox[2]}`,
            );
          }
          updateOrAppendSearchParam(
            params,
            "CRS",
            selectedCrs.stringRepresentation,
          );
        } else {
          // always minx,miny,maxx,maxy (minLng,minLat,maxLng,maxLat)
          updateOrAppendSearchParam(
            params,
            "BBOX",
            `${bbox[0]},${bbox[1]},${bbox[2]},${bbox[3]}`,
          );
          updateOrAppendSearchParam(
            params,
            "SRS",
            selectedCrs.stringRepresentation,
          );
        }
      });
      return getFeatureInfoUrls;
    }
  }, [
    layerPoint,
    position,
    atomicGetFeatureInfoUrls,
    identifyViewport,
    selectedCrs,
  ]);

  useEffect(() => {
    if (!map) return;

    const updateBounds = () => {
      setBounds(map.getBounds());
      setSize(map.getSize());
    };

    let viewportUpdateTimeout: ReturnType<typeof setTimeout> | undefined;
    const scheduleViewportUpdate = () => {
      if (viewportUpdateTimeout) {
        clearTimeout(viewportUpdateTimeout);
      }
      viewportUpdateTimeout = setTimeout(updateBounds, VIEWPORT_DEBOUNCE_MS);
    };

    updateBounds();
    map.on("viewreset moveend zoomend", scheduleViewportUpdate);
    return () => {
      map.off("viewreset moveend zoomend", scheduleViewportUpdate);
      if (viewportUpdateTimeout) {
        clearTimeout(viewportUpdateTimeout);
      }
    };
  }, [map]);

  const identify = (event: {
    latlng: LatLng;
    containerPoint: { x: number; y: number };
  }) => {
    if (atomicGetFeatureInfoUrls.length > 0) {
      setCollapsed(false);
      setIdentifyViewport({ bbox, size });
      setPosition(event.latlng);
      setLayerPoint(event.containerPoint);
    } else {
      setPosition(null);
      setLayerPoint(null);
    }
  };
  useMapEvent("contextmenu", identify);
  useMapEvent("click", (event) => {
    if (identifying) identify(event);
  });
  const clear = () => {
    setPosition(null);
    setLayerPoint(null);
  };

  return (
    <Fragment>
      {tiles.map((tile) => tile.leafletTile)}
      {position && (
        <Marker position={position}>
          <Tooltip direction="top">
            {translate("viewerFeatureInfo.tooltip")}
          </Tooltip>
        </Marker>
      )}
      {createPortal(
        <Box
          ref={(node: HTMLDivElement | null) => {
            if (node) {
              DomEvent.disableClickPropagation(node);
              DomEvent.disableScrollPropagation(node);
            }
          }}
          sx={{
            position: "absolute",
            zIndex: 1100,
            right: { xs: 8, sm: 16 },
            top: { xs: position && !collapsed ? "auto" : 16, sm: 16 },
            bottom: { xs: position && !collapsed ? 30 : "auto", sm: "auto" },
            width: {
              xs: position && !collapsed ? "calc(100% - 16px)" : "auto",
              sm: position && !collapsed ? 400 : "auto",
            },
            maxWidth: "calc(100% - 32px)",
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
            {(!position || collapsed) && (
              <Button
                onClick={() => {
                  if (position) setCollapsed(false);
                  else setIdentifying((value) => !value);
                }}
                variant={identifying ? "contained" : "text"}
              >
                {translate(
                  position
                    ? "viewerFeatureInfo.reopen"
                    : "viewerFeatureInfo.identify",
                )}
              </Button>
            )}
            {position && (
              <Box
                sx={{
                  display: collapsed ? "none" : "flex",
                  flexDirection: "column",
                  maxHeight: {
                    xs: size.y * 0.55,
                    sm: Math.max(180, size.y - 32),
                  },
                }}
                role="region"
                aria-label={translate("viewerFeatureInfo.title")}
              >
                <Stack spacing={1} sx={{ p: 2 }}>
                  <Stack direction="row" sx={{ alignItems: "center" }}>
                    <Typography variant="h6" sx={{ flex: 1 }}>
                      {translate("viewerFeatureInfo.title")}
                    </Typography>
                    <IconButton
                      size="small"
                      aria-label={translate("viewerFeatureInfo.collapse")}
                      onClick={() => setCollapsed(true)}
                    >
                      −
                    </IconButton>
                    <IconButton
                      size="small"
                      aria-label={translate("ra.action.close")}
                      onClick={clear}
                    >
                      ×
                    </IconButton>
                  </Stack>
                  <Typography variant="caption" color="text.secondary">
                    {position.lat.toFixed(5)}°, {position.lng.toFixed(5)}°
                  </Typography>
                </Stack>
                <Divider />
                <Stack
                  spacing={1}
                  sx={{ p: 1.5, overflow: "auto", minHeight: 0 }}
                >
                  {getFeatureInfoUrls?.map((request) => (
                    <FeatureInfoRequest
                      request={request}
                      key={request.url.href}
                    />
                  ))}
                </Stack>
                <Divider />
                <Stack
                  direction="row"
                  sx={{ px: 2, py: 0.5, alignItems: "center" }}
                >
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ flex: 1 }}
                  >
                    {translate("viewerFeatureInfo.hint")}
                  </Typography>
                  <Button size="small" onClick={clear}>
                    {translate("viewerFeatureInfo.clear")}
                  </Button>
                </Stack>
              </Box>
            )}
          </Paper>
        </Box>,
        map.getContainer(),
      )}
    </Fragment>
  );
};

export default WebMapServiceControl;
