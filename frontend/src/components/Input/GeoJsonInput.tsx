import type { MultiPolygon } from "geojson";

import { useCallback, type ReactNode } from "react";
import { TextInput, useInput, type TextInputProps } from "react-admin";
import { useFormContext } from "react-hook-form";

import { Box } from "@mui/material";

import GeoJsonMap from "../MapContainer/GeoJsonMap";
import FeatureGroupEditor from "./FeatureGroupEditor";

export interface GeoJsonInputProps extends TextInputProps {
  /** which drawing tools the map editor offers; both by default */
  drawRectangle?: boolean;
  drawPolygon?: boolean;
}

const GeoJsonInput = ({
  source,
  drawRectangle = true,
  drawPolygon = true,
  ...props
}: GeoJsonInputProps): ReactNode => {
  const {
    id,
    field: { value },
  } = useInput({
    source,
  });
  const { setValue } = useFormContext();

  const geoJsonCallback = useCallback(
    (multiPolygon: MultiPolygon) => {
      setValue(source, multiPolygon, { shouldDirty: true });
    },
    [source, setValue],
  );

  return (
    <Box sx={{ width: "100%" }}>
      <TextInput
        source={source}
        parse={(value) => (value === "" ? null : JSON.parse(value))}
        format={(value) => (value === null ? "" : JSON.stringify(value))}
        multiline
        type={"json"}
        {...props}
      />
      <GeoJsonMap id={`${id}-mapcontainer`}>
        <FeatureGroupEditor
          geoJson={value}
          geoJsonCallback={geoJsonCallback}
          editable={!props.disabled}
          drawRectangle={drawRectangle}
          drawPolygon={drawPolygon}
        />
      </GeoJsonMap>
    </Box>
  );
};

export default GeoJsonInput;
