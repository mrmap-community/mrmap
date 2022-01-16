
import { MapComponent, useMap } from '@terrestris/react-geo';
import LayerGroup from 'ol/layer/Group';
import OlLayerTile from 'ol/layer/Tile';
import OlMap from 'ol/Map';
import OlSourceOsm from 'ol/source/OSM';
import OlView from 'ol/View';
import React, { useEffect } from 'react';
import './TheMap.css';

// TODO: Should be in a separate component or helper
const layerGroup = new LayerGroup({
  // @ts-ignore
  name: 'Layergroup',
  layers: [
    new OlLayerTile({
      source: new OlSourceOsm(),
      // @ts-ignore
      name: 'OSM'
    })
  ]
});

const center = [788453.4890155146, 6573085.729161344];

export const olMap = new OlMap({
  view: new OlView({
    center: center,
    zoom: 16
  }),
  layers: [layerGroup]
});

export const TheMap = () => {
  const map = useMap();

  useEffect(() => {
    map.setTarget('the-map');
  }, [map]);
  
  
  return (
    <MapComponent
      id='the-map'
      map={map}
    />
  );
};
