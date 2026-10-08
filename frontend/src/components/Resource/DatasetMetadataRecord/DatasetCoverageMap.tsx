import { Box, Button, Stack, Typography } from "@mui/material";
import L from "leaflet";
import { useEffect } from "react";
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
import AutoResizeMapContainer from "../../MapContainer/ResizeAbleMapContainer";

export interface CoverageEntry {
  record: RaRecord;
  bounds: L.LatLngBounds;
}

const FitCoverage = ({
  entries,
  selected,
}: {
  entries: CoverageEntry[];
  selected?: Identifier;
}) => {
  const map = useMap();
  useEffect(() => {
    const entry = entries.find(({ record }) => record.id === selected);
    const bounds =
      entry?.bounds ??
      entries.reduce(
        (result, item) => result.extend(item.bounds),
        L.latLngBounds([]),
      );
    if (bounds.isValid())
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: 14 });
  }, [map, entries, selected]);
  return null;
};

const DatasetCoverageMap = ({
  entries,
  selected,
  onSelect,
}: {
  entries: CoverageEntry[];
  selected?: Identifier;
  onSelect: (id: Identifier) => void;
}) => {
  const translate = useTranslate();
  return (
    <Stack sx={{ minWidth: 0 }} spacing={1}>
      <Typography variant="subtitle1">
        {translate("datasetExplorer.coverage")}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {translate("datasetExplorer.scope", { count: entries.length })}
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
          style={{ height: "100%", width: "100%" }}
        >
          <AutoResizeMapContainer />
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <FitCoverage entries={entries} selected={selected} />
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
                    {translate("datasetExplorer.select")}
                  </Button>
                  <ShowButton />
                </RecordContextProvider>
              </Popup>
            </Rectangle>
          ))}
        </MapContainer>
      </Box>
      {!entries.length && (
        <Typography color="text.secondary">
          {translate("datasetExplorer.noCoverage")}
        </Typography>
      )}
      <Typography variant="caption" color="text.secondary">
        {translate("datasetExplorer.legend")}
      </Typography>
    </Stack>
  );
};

export default DatasetCoverageMap;
