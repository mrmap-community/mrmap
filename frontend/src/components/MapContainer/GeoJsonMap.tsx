import { Box } from "@mui/material";
import type { PropsWithChildren } from "react";
import { MapContainer, TileLayer, type MapContainerProps } from "react-leaflet";
import AutoResizeMapContainer from "./ResizeAbleMapContainer";

const GeoJsonMap = ({
  id,
  children,
}: PropsWithChildren<Pick<MapContainerProps, "id">>) => (
  <Box sx={{ height: "200px", width: "100%" }}>
    <MapContainer
      id={id}
      center={[51.505, -0.09]}
      zoom={2}
      scrollWheelZoom
      style={{ height: "100%", width: "100%" }}
    >
      <AutoResizeMapContainer />
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {children}
    </MapContainer>
  </Box>
);

export default GeoJsonMap;
