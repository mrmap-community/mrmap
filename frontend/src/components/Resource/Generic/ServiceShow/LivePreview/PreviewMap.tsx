import type { LiveRecord } from "./usePreview";
import type { FeatureCollection } from "geojson";

import { useCallback, useEffect, useState } from "react";
import { useTranslate } from "react-admin";
import {
  GeoJSON,
  ImageOverlay,
  MapContainer,
  Rectangle,
  useMap,
  useMapEvents,
} from "react-leaflet";

import { Box, Button, Stack, Typography } from "@mui/material";
import { CRS, Map as LeafletMap, latLngBounds } from "leaflet";

import AutoResizeMapContainer from "../../../../MapContainer/ResizeAbleMapContainer";

export interface Viewport {
  bbox: string;
  width: number;
  height: number;
}
export const validExtent = (
  extent?: number[] | null,
): extent is [number, number, number, number] =>
  Boolean(
    extent &&
    extent.length === 4 &&
    extent.every(Number.isFinite) &&
    -180 <= extent[0] &&
    extent[0] < extent[2] &&
    extent[2] <= 180 &&
    -90 <= extent[1] &&
    extent[1] < extent[3] &&
    extent[3] <= 90,
  );

const extentBounds = (extent: number[]) =>
  latLngBounds([extent[1], extent[0]], [extent[3], extent[2]]);
const ViewportEvents = ({
  onViewport,
  onIdentify,
}: {
  onViewport: (viewport: Viewport) => void;
  onIdentify?: (x: number, y: number) => void;
}) => {
  const map = useMap();
  const update = useCallback(() => {
    const bounds = map.getBounds();
    const size = map.getSize();
    // Limit the first increment to one WGS84 viewport, including wrapped worlds.
    const west = Math.max(-180, bounds.getWest());
    const east = Math.min(180, bounds.getEast());
    const south = Math.max(-85, bounds.getSouth());
    const north = Math.min(85, bounds.getNorth());
    if (west < east && south < north && size.x > 0 && size.y > 0)
      onViewport({
        bbox: [west, south, east, north].join(","),
        width: Math.min(2048, size.x),
        height: Math.min(2048, size.y),
      });
  }, [map, onViewport]);
  useMapEvents({
    moveend: update,
    resize: update,
    contextmenu: (event) => {
      const bounds = map.getBounds();
      const size = map.getSize();
      const west = Math.max(-180, bounds.getWest());
      const east = Math.min(180, bounds.getEast());
      const south = Math.max(-85, bounds.getSouth());
      const north = Math.min(85, bounds.getNorth());
      const width = Math.min(2048, size.x);
      const height = Math.min(2048, size.y);
      if (west < east && south < north)
        onIdentify?.(
          Math.min(
            width - 1,
            Math.max(
              0,
              Math.floor(((event.latlng.lng - west) / (east - west)) * width),
            ),
          ),
          Math.min(
            height - 1,
            Math.max(
              0,
              Math.floor(
                ((north - event.latlng.lat) / (north - south)) * height,
              ),
            ),
          ),
        );
    },
  });
  useEffect(update, [update]);
  return null;
};

const FitSelection = ({
  extent,
  revision,
}: {
  extent?: number[] | null;
  revision: number;
}) => {
  const map = useMap();
  useEffect(() => {
    if (validExtent(extent))
      map.fitBounds(extentBounds(extent), { padding: [20, 20], maxZoom: 12 });
  }, [map, extent?.join(","), revision]);
  return null;
};

const FeatureLayer = ({ collection }: { collection: FeatureCollection }) => {
  const [properties, setProperties] = useState<Record<string, unknown>>();
  const translate = useTranslate();
  return (
    <>
      <GeoJSON
        data={collection}
        onEachFeature={(feature, layer) => {
          layer.on("click", () => setProperties(feature.properties ?? {}));
          layer.on("add", () => {
            const element =
              "getElement" in layer
                ? (
                    layer as { getElement: () => Element | undefined }
                  ).getElement()
                : undefined;
            element?.setAttribute("tabindex", "0");
            element?.setAttribute("role", "button");
            element?.setAttribute(
              "aria-label",
              translate("livePreview.attributes"),
            );
            element?.addEventListener("keydown", (event) => {
              if ((event as KeyboardEvent).key === "Enter")
                setProperties(feature.properties ?? {});
            });
          });
        }}
      />
      {properties && (
        <Box
          role="status"
          sx={{
            position: "absolute",
            bottom: 10,
            left: 10,
            zIndex: 1000,
            bgcolor: "background.paper",
            p: 2,
            maxHeight: 160,
            maxWidth: "80%",
            overflow: "auto",
          }}
        >
          <Button onClick={() => setProperties(undefined)}>
            {translate("ra.action.close")}
          </Button>
          {Object.entries(properties).map(([key, value]) => (
            <Typography key={key} component="div" variant="body2">
              {key}:{" "}
              {typeof value === "object"
                ? JSON.stringify(value)
                : String(value ?? "")}
            </Typography>
          ))}
        </Box>
      )}
    </>
  );
};

const PreviewMap = ({
  viewport,
  onViewport,
  image,
  features,
  records,
  selectedRecord,
  onSelectRecord,
  extent,
  onIdentify,
  identifyAvailable,
  onMap,
}: {
  viewport?: Viewport;
  onViewport: (viewport: Viewport) => void;
  image?: string;
  features?: FeatureCollection;
  records?: LiveRecord[];
  selectedRecord?: number;
  onSelectRecord?: (index: number) => void;
  extent?: number[] | null;
  onIdentify?: (x: number, y: number) => void;
  identifyAvailable?: boolean;
  onMap?: (map: LeafletMap | null) => void;
}) => {
  const [expanded, setExpanded] = useState(false);
  const [zoom, setZoom] = useState(0);
  const translate = useTranslate();
  const bbox = viewport?.bbox.split(",").map(Number);
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
        <Button
          disabled={!validExtent(extent)}
          onClick={() => setZoom((value) => value + 1)}
        >
          {translate("livePreview.zoom")}
        </Button>
        <Button
          onClick={() => setExpanded((value) => !value)}
          aria-pressed={expanded}
        >
          {translate(
            expanded ? "livePreview.collapseMap" : "livePreview.expandMap",
          )}
        </Button>
        {identifyAvailable && (
          <Button
            onClick={() =>
              onIdentify?.(
                Math.floor((viewport?.width ?? 0) / 2),
                Math.floor((viewport?.height ?? 0) / 2),
              )
            }
          >
            {translate("livePreview.identify")}
          </Button>
        )}
      </Stack>
      {!validExtent(extent) && (
        <Typography variant="body2">
          {translate("livePreview.noExtent")}
        </Typography>
      )}
      <Box
        sx={{
          height: expanded ? "75vh" : 380,
          position: "relative",
          width: "100%",
        }}
      >
        <MapContainer
          ref={onMap}
          crs={CRS.EPSG4326}
          center={[30, 0]}
          zoom={2}
          keyboard
          scrollWheelZoom
          maxBounds={[
            [-85, -180],
            [85, 180],
          ]}
          style={{ height: "100%", width: "100%" }}
        >
          <AutoResizeMapContainer />
          <ViewportEvents onViewport={onViewport} onIdentify={onIdentify} />
          <FitSelection extent={extent} revision={zoom} />
          {image && validExtent(bbox) && (
            <ImageOverlay url={image} bounds={extentBounds(bbox)} />
          )}
          {features && (
            <FeatureLayer
              key={JSON.stringify(features)}
              collection={features}
            />
          )}
          {records?.map(
            (record, index) =>
              validExtent(record.extent) && (
                <Rectangle
                  key={`${record.identifier}-${index}`}
                  bounds={extentBounds(record.extent)}
                  pathOptions={{
                    color: index === selectedRecord ? "#c14400" : "#1976d2",
                    weight: index === selectedRecord ? 4 : 1,
                  }}
                  eventHandlers={{ click: () => onSelectRecord?.(index) }}
                />
              ),
          )}
        </MapContainer>
      </Box>
      {records && (
        <Typography variant="caption">
          {translate("livePreview.coverage")}
        </Typography>
      )}
    </Stack>
  );
};

export default PreviewMap;
