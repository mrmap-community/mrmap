
import { type ReactNode } from 'react';
import { sanitizeFieldRestProps, useFieldValue, useRecordContext, useTranslate, type TextFieldProps } from 'react-admin';
import { MapContainer, TileLayer } from 'react-leaflet';

import { Box, Typography } from '@mui/material';

import FeatureGroupEditor from '../Input/FeatureGroupEditor';
import AutoResizeMapContainer from '../MapContainer/ResizeAbleMapContainer';


const style = {
  width: '100wh',
  height: '200px',
}

const GeoJsonField = ({
  ...props
}: TextFieldProps): ReactNode => {

  const record = useRecordContext();
  const translate = useTranslate();

  const value = useFieldValue(props);
  const { className, emptyText, ...rest } = props;

  return (
    <div style={{width: '100%'}}>
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
      <Box sx={{ ...style }}>
        <MapContainer
          id={`${record?.id}-mapcontainer`}
          center={[51.505, -0.09]}
          zoom={2}
          scrollWheelZoom={true}
          style={{ height: '100%', width: '100wh' }}
        >
          <AutoResizeMapContainer/>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <FeatureGroupEditor
            // forces rerendering on every value change for example.
            key={(Math.random() + 1).toString(36).substring(7)}
            geoJson={value}
            editable={false}
          />
        </MapContainer>
      </Box>
    </div>
  )
}

export default GeoJsonField
