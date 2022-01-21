
import { CloseOutlined } from '@ant-design/icons';
import { MapComponent, useMap } from '@terrestris/react-geo';
import Button from 'antd/lib/button';
import { Key } from 'antd/lib/table/interface';
import { EventsKey as OlEventsKey } from 'ol/events';
import LayerGroup from 'ol/layer/Group';
import OlLayerTile from 'ol/layer/Tile';
import OlMap from 'ol/Map';
import { unByKey } from 'ol/Observable';
import Overlay from 'ol/Overlay';
import OlSourceOsm from 'ol/source/OSM';
import OlView from 'ol/View';
import React, { ReactNode, useEffect, useState } from 'react';
import { JsonApiResponse } from '../../Repos/JsonApiRepo';
import { LayerUtils } from '../../Utils/LayerUtils';
import { LayerManager } from '../LayerManager/LayerManager';
import { CreateLayerOpts } from '../LayerManager/LayerManagerTypes';
import { TreeNodeType } from '../Shared/FormFields/TreeFormField/TreeFormFieldTypes';
import './TheMap.css';

const layerUtils = new LayerUtils();

const backgroundLayersLayerGroup = new LayerGroup({
  // @ts-ignore
  properties: {
    title: 'Background layers',
  },
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
  layers: [backgroundLayersLayerGroup]
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

export const TheMap = ({ 
  addLayerDispatchAction = () => undefined,
  removeLayerDispatchAction = () => undefined,
  editLayerDispatchAction = () => undefined,
  dragLayerDispatchAction = () => undefined,
  selectLayerDispatchAction = () => undefined,
  customLayerManagerTitleAction = () => undefined,
  layerGroupName,
  initLayerTreeData,
  layerAttributeForm
}: {
  addLayerDispatchAction?:(
    nodeAttributes: any,
    newNodeParent?: string | number | null | undefined) =>
    Promise<CreateLayerOpts> | CreateLayerOpts | void;
  removeLayerDispatchAction?: (nodeToRemove: TreeNodeType) => Promise<JsonApiResponse> | void;
  editLayerDispatchAction?: (nodeId:number|string, nodeAttributesToUpdate: any) => Promise<JsonApiResponse> | void;
  dragLayerDispatchAction?: (nodeBeingDraggedInfo: any) => Promise<JsonApiResponse> | void;
  selectLayerDispatchAction?: (selectedKeys: Key[], info: any) => void;
  customLayerManagerTitleAction?: () => void | undefined;
  layerGroupName: string;
  initLayerTreeData: any;
  layerAttributeForm: ReactNode;
}): JSX.Element => {
  const map = useMap();

  const [coordinates, setCoordinates] = useState<any>();
  
  const registerMapClickListener = (_olMap: OlMap, _overlay?: Overlay) => {
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
    
    //map.render();  
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
      <LayerManager
        initLayerTreeData={initLayerTreeData}
        layerManagerLayerGroupName={layerGroupName}
        asyncTree
        selectLayerDispatchAction={selectLayerDispatchAction}
        addLayerDispatchAction={addLayerDispatchAction}
        removeLayerDispatchAction={removeLayerDispatchAction}
        editLayerDispatchAction={editLayerDispatchAction}
        dragLayerDispatchAction={dragLayerDispatchAction}
        customLayerManagerTitleAction={customLayerManagerTitleAction}
        layerAttributeForm={layerAttributeForm}
      />
      <MapComponent
        id='the-map'
        map={map}
      />  
      <FeatureInfoPopUp info={coordinates} />
    </div>
  );
};
