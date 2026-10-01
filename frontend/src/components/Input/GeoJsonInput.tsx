import type { MultiPolygon } from "geojson";
import { useCallback, type ReactNode } from "react";
import { TextInput, useInput, type TextInputProps } from "react-admin";
import { useFormContext } from "react-hook-form";
import GeoJsonMap from "../MapContainer/GeoJsonMap";

import { Box } from "@mui/material";

import FeatureGroupEditor from "./FeatureGroupEditor";

const GeoJsonInput = ({ source, ...props }: TextInputProps): ReactNode => {
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
        />
      </GeoJsonMap>
    </Box>
  );
};

export default GeoJsonInput;
