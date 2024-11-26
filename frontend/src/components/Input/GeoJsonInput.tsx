
import type { MultiPolygon } from 'geojson';
import { useCallback, type ReactNode } from 'react';
import { TextInput, useInput, type TextInputProps } from 'react-admin';
import { useFormContext, } from "react-hook-form";
import { MapContainer, TileLayer } from 'react-leaflet';

import { Box } from '@mui/material';

import L from 'leaflet';
import FeatureGroupEditor from './FeatureGroupEditor';


const style = {
  //position: 'absolute' as const,
  //top: '50%',
  //left: '50%',
  //transform: 'translate(-50%, -50%)',
  width: '100wh',
  height: '200px',
  // bgcolor: 'background.paper',
  // border: '2px solid #000',
  //boxShadow: 24
  // pt: 2,
  // px: 4,
  // pb: 3,
}

const validateGeoJson = (value, allValues) => {
  try{
    L.geoJSON(value)
  } catch (error){
    console.log('errorrr')
    return 'error'
  }
  
  return undefined
};


const GeoJsonInput = ({
  source,
  ...props
}: TextInputProps): ReactNode => {
  const { id, field: {value, onChange}, fieldState: {invalid, error} } = useInput(
    { 
      source
    }
  );
  const {setValue} = useFormContext();

  const geoJsonCallback = useCallback((multiPolygon: MultiPolygon)=>{
    setValue(source, multiPolygon, { shouldDirty: true })
  },[source])

  return (
    <div style={{width: '100%'}}>
      <TextInput
        source={source}
        parse={(value) => value === '' ? null : JSON.parse(value)}
        format={(value) => value === null ? '' : JSON.stringify(value)}
        // TODO: validate on every change...
       // validate={[validateGeoJson]}
        multiline
        type={'json'}
        {...props}
      />
      <Box sx={{ ...style }}>
        <MapContainer
          id={`${id}-mapcontainer`}
          center={[51.505, -0.09]}
          zoom={2}
          scrollWheelZoom={true}
          style={{ height: '100%', width: '100wh' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <FeatureGroupEditor
            // forces rerendering on every value change for example.
            key={(Math.random() + 1).toString(36).substring(7)}
            geoJson={value}
            geoJsonCallback={geoJsonCallback}
            editable={!props.disabled}
          />
        </MapContainer>

      </Box>
    </div>
  )
}

export default GeoJsonInput
