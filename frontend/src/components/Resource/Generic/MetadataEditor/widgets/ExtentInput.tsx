import type { MetadataWidgetProps } from "./types";

import { useState, type ReactElement, type ReactNode } from "react";
import { useTranslate } from "react-admin";

import { Box, ToggleButton, ToggleButtonGroup, Typography } from "@mui/material";

import GeoJsonInput from "../../../../Input/GeoJsonInput";

type DrawMode = "bbox" | "polygon";

/**
 * Spatial extent editor for the `boundingGeometry` attribute (#1246).
 *
 * `GeoJsonInput` is already the map-plus-JSON editor of this project — the
 * GeoJSON text area stays the source of truth and the drawing writes into
 * it. This widget adds the two things the extent field needs on top: the
 * bbox/polygon mode switch, which restricts the drawing tools to rectangles
 * or free polygons (mrmap writes a rectangle without holes as
 * `EX_GeographicBoundingBox` and anything else as `EX_BoundingPolygon`), and
 * the reminder that the coordinates are WGS84, since the drawn GeoJSON is
 * stored exactly as it is drawn.
 */
const ExtentInput = ({
  helperText,
  label,
  source,
  ...rest
}: MetadataWidgetProps): ReactElement => {
  const translate = useTranslate();
  const [mode, setMode] = useState<DrawMode>("bbox");

  const fullHelperText: ReactNode = (
    <>
      {helperText ?? null}
      <Typography variant="caption" component="div" color="text.secondary">
        {translate("metadataEditor.extent.wgs84Hint")}
      </Typography>
    </>
  );

  return (
    <Box sx={{ width: "100%" }}>
      <ToggleButtonGroup
        exclusive
        size="small"
        value={mode}
        onChange={(_, next: DrawMode | null) => next !== null && setMode(next)}
        sx={{ mb: 1 }}
      >
        <ToggleButton value="bbox" sx={{ textTransform: "none" }}>
          {translate("metadataEditor.extent.bbox")}
        </ToggleButton>
        <ToggleButton value="polygon" sx={{ textTransform: "none" }}>
          {translate("metadataEditor.extent.polygon")}
        </ToggleButton>
      </ToggleButtonGroup>
      <GeoJsonInput
        {...rest}
        source={source}
        label={label}
        helperText={fullHelperText}
        drawRectangle={mode === "bbox"}
        drawPolygon={mode === "polygon"}
      />
    </Box>
  );
};

export default ExtentInput;
