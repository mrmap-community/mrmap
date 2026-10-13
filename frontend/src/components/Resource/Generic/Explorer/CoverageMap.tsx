import { Box, Button, Stack, Typography } from "@mui/material";
import L from "leaflet";
import { useEffect, useRef } from "react";
import {
  type Identifier,
  type RaRecord,
  RecordContextProvider,
  ShowButton,
  useTranslate,
} from "react-admin";
import {
  MapContainer,
  Popup,
  Rectangle,
  TileLayer,
  useMap,
} from "react-leaflet";
import AutoResizeMapContainer from "../../../MapContainer/ResizeAbleMapContainer";

export interface CoverageEntry {
  record: RaRecord;
  bounds: L.LatLngBounds;
}

const FitCoverage = ({
  entries,
  selected,
  preserveViewport,
}: {
  entries: CoverageEntry[];
  selected?: Identifier;
  preserveViewport?: boolean;
}) => {
  const map = useMap();
  const fitted = useRef(false);
  useEffect(() => {
    if (preserveViewport && fitted.current && selected === undefined) return;
    const entry = entries.find(({ record }) => record.id === selected);
    const bounds =
      entry?.bounds ??
      entries.reduce(
        (result, item) => result.extend(item.bounds),
        L.latLngBounds([]),
      );
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: 14 });
      fitted.current = true;
    }
  }, [map, entries, selected, preserveViewport]);
  return null;
};

const SearchArea = ({
  onSearch,
  namespace,
}: {
  onSearch: (geometry: string) => void;
  namespace: string;
}) => {
  const map = useMap();
  const translate = useTranslate();
  return (
    <Button
      variant="contained"
      sx={{ position: "absolute", zIndex: 1000, top: 12, right: 12 }}
      onClick={() => {
        const bounds = map.getBounds();
        const west = Math.max(-180, bounds.getWest());
        const east = Math.min(180, bounds.getEast());
        const south = Math.max(-90, bounds.getSouth());
        const north = Math.min(90, bounds.getNorth());
        onSearch(
          JSON.stringify({
            type: "Polygon",
            coordinates: [
              [
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
              ],
            ],
          }),
        );
      }}
    >
      {translate(`${namespace}.searchArea`)}
    </Button>
  );
};

export interface CoverageMapProps {
  entries: CoverageEntry[];
  selected?: Identifier;
  onSelect: (id: Identifier) => void;
  namespace?: string;
  showDetails?: boolean;
  onSearchArea?: (geometry: string) => void;
}

const CoverageMap = ({
  entries,
  selected,
  onSelect,
  namespace = "datasetExplorer",
  onSearchArea,
  showDetails = true,
}: CoverageMapProps) => {
  const translate = useTranslate();
  return (
    <Stack sx={{ minWidth: 0 }} spacing={1}>
      <Typography variant="subtitle1">
        {translate(`${namespace}.coverage`)}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {translate(`${namespace}.scope`, { count: entries.length })}
      </Typography>
      <Box
        sx={{
          height: { xs: 360, md: 600 },
          position: "relative",
          borderRadius: 1,
          overflow: "hidden",
        }}
      >
        <MapContainer
          center={[50, 8]}
          zoom={4}
          maxBounds={[
            [-90, -180],
            [90, 180],
          ]}
          maxBoundsViscosity={1}
          style={{ height: "100%", width: "100%" }}
        >
          <AutoResizeMapContainer />
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <FitCoverage
            entries={entries}
            selected={selected}
            preserveViewport={!!onSearchArea}
          />
          {onSearchArea && (
            <SearchArea onSearch={onSearchArea} namespace={namespace} />
          )}
          {entries.map(({ record, bounds }) => (
            <Rectangle
              key={record.id}
              bounds={bounds}
              pathOptions={{
                color: selected === record.id ? "#e65100" : "#1976d2",
                weight: selected === record.id ? 3 : 1,
                fillOpacity: selected === record.id ? 0.25 : 0.08,
              }}
              eventHandlers={{ click: () => onSelect(record.id) }}
            >
              <Popup>
                <RecordContextProvider value={record}>
                  <Typography variant="subtitle2">
                    {record.title || record.stringRepresentation}
                  </Typography>
                  <Button size="small" onClick={() => onSelect(record.id)}>
                    {translate(`${namespace}.select`)}
                  </Button>
                  {showDetails && <ShowButton />}
                </RecordContextProvider>
              </Popup>
            </Rectangle>
          ))}
        </MapContainer>
      </Box>
      {!entries.length && (
        <Typography color="text.secondary">
          {translate(`${namespace}.noCoverage`)}
        </Typography>
      )}
      <Typography variant="caption" color="text.secondary">
        {translate(`${namespace}.legend`)}
      </Typography>
    </Stack>
  );
};

export default CoverageMap;
