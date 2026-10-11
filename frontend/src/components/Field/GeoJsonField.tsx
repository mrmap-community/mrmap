import { type ReactNode } from "react";
import {
  sanitizeFieldRestProps,
  useFieldValue,
  useRecordContext,
  useTranslate,
  type TextFieldProps,
} from "react-admin";

import { Box, Typography } from "@mui/material";

import FeatureGroupEditor from "../Input/FeatureGroupEditor";
import GeoJsonMap from "../MapContainer/GeoJsonMap";

const GeoJsonField = ({ ...props }: TextFieldProps): ReactNode => {
  const record = useRecordContext();
  const translate = useTranslate();

  const value = useFieldValue(props);
  const { className, emptyText, ...rest } = props;
  return (
    <Box sx={{ width: "100%" }}>
      <Typography
        component="span"
        variant="body2"
        className={className}
        {...sanitizeFieldRestProps(rest)}
      >
        {value != null
          ? JSON.stringify(value)
          : value ||
            (emptyText ? translate(emptyText, { _: emptyText }) : null)}
      </Typography>
      <GeoJsonMap id={`${record?.id}-mapcontainer`}>
        <FeatureGroupEditor geoJson={value} editable={false} />
      </GeoJsonMap>
    </Box>
  );
};

export default GeoJsonField;
