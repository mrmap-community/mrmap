
import { CloseOutlined } from '@ant-design/icons';
import { MapComponent, useMap } from '@terrestris/react-geo';
import Button from 'antd/lib/button';
import { EventsKey as OlEventsKey } from 'ol/events';
import LayerGroup from 'ol/layer/Group';
import OlLayerTile from 'ol/layer/Tile';
import OlMap from 'ol/Map';
import { unByKey } from 'ol/Observable';
import Overlay from 'ol/Overlay';
import OlSourceOsm from 'ol/source/OSM';
import OlView from 'ol/View';
import React, { useEffect, useState } from 'react';
import { LayerUtils } from '../../Utils/LayerUtils';
import { LayerManager } from '../LayerManager/LayerManager';
import './TheMap.css';

const layerUtils = new LayerUtils();

// TODO: Should be in a separate component or helper
const layerGroup = new LayerGroup({
  // @ts-ignore
  title: 'Layergroup',
  layers: [
    new OlLayerTile({
      source: new OlSourceOsm(),
      // @ts-ignore
      title: 'OSM'
    })
  ]
});

const center = [788453.4890155146, 6573085.729161344]; //BONN

export const olMap = new OlMap({
  view: new OlView({
    center: center,
    zoom: 1 // to show the whole world
  }),
  layers: [layerGroup]
});

const FeatureInfoPopUp = ({ info }: {info: any}): JSX.Element => (
  <div id='popup' className='ol-popup'>
    <Button
      id='popup-close'
      type='link'
      icon={<CloseOutlined />}
      size='small'
    />
  
    <div id='popup-content'>
      {info}
    </div>
  </div>
);

const olListenerKeys: (OlEventsKey[]) = [];

export const TheMap = (): JSX.Element => {
  const map = useMap();

  const [coordinates, setCoordinates] = useState<any>();
  const [isLayerManagerVisible, setIsLayerManagerVisible] = useState<any>(false);
  
  const registerMapClickListener = (_olMap: OlMap, _overlay?: Overlay) => {
    const mapSizeChange = _olMap
      .on('change:size', (event) => console.log(event));
    const getFeatureAttributesClickEventKey = _olMap
      .on('singleclick', (event) => layerUtils.getFeatureAttributes(_olMap, event));
    if(_overlay) {
      const onShowInfoPopUpOnCoordinateClickListener = _olMap
        .on('singleclick', async (event) => {
          setCoordinates('');
          const coordinate = event.coordinate;
          const featureInfo = layerUtils.getFeatureAttributes(_olMap, event);
          _overlay.setPosition(coordinate);
          try {
            const result = await featureInfo;
            if(result) {
              const cena = Object.keys(result).map((key:any) => (`${key}: ${result[key]}`));
              setCoordinates(cena.join('\n'));
            }
          } catch(error) {
            //@ts-ignore
            throw new Error(error);
          }
          
        });
      olListenerKeys.push(onShowInfoPopUpOnCoordinateClickListener);
    }
    olListenerKeys.push(getFeatureAttributesClickEventKey);
    olListenerKeys.push(mapSizeChange);
  };

  useEffect(() => {    
    const close = document.getElementById('popup-close');
    
  
    const infoPopUpBubble: Overlay = new Overlay({
      //@ts-ignore
      element: document.getElementById('popup'),
      autoPan: {
        animation: {
          duration: 250,
        },
      },
    });
    
    if(close) {
      close.onclick = function () {
        infoPopUpBubble.setPosition(undefined);
        close.blur();
        return false;
      };
    }
    
    // const overlay = infoPopUpBubble(container);
    map.setTarget('the-map');
    registerMapClickListener(map, infoPopUpBubble);
    map.addOverlay(infoPopUpBubble);
    return () => {
      // unregister the listener
      unByKey(olListenerKeys);
      map.removeOverlay(infoPopUpBubble);
    };
  }, [map]);

  return (
    <div className='the-map-container'>
      <LayerManager/>
      <MapComponent
        id='the-map'
        map={map}
      />  
      <FeatureInfoPopUp info={coordinates} />
    </div>
  );
};
