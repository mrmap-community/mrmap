import { SyncOutlined } from '@ant-design/icons';
import { LayerTree, useMap } from '@terrestris/react-geo';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import ImageWMS from 'ol/source/ImageWMS';
import React, { ReactElement, useEffect, useState } from 'react';
import { useParams } from 'react-router';
import { operation, unpage } from '../../Repos/JsonApi';
import { olMap } from '../../Utils/MapUtils';
import { AutoResizeMapComponent } from '../Shared/AutoResizeMapComponent/AutoResizeMapComponent';
import { AreaDigitizeToolbar } from './AreaDigitizeToolbar/AreaDigitizeToolbar';
import { LeftDrawer } from './LeftDrawer/LeftDrawer';
import { RulesDrawer } from './RulesDrawer/RulesDrawer';
import './WmsSecuritySettings.css';

export const WmsSecuritySettings = (): ReactElement => {

  const map = useMap();
  const { wmsId } = useParams();
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [selectedLayerIds, setSelectedLayerIds] = useState<string[]>([]);
  const [selectedLayerKeys, setSelectedLayerKeys] = useState<string[]>([]);
  // only when rule editing is active, are layers selectable and digitizing visible
  const [isRuleEditingActive, setIsRuleEditingActive] = useState<boolean>(false);

  useEffect(() => {
    if (wmsId) {
      setIsLoading(true);
      let wmsOlRootLayer: BaseLayer | undefined;
      const fetchWmsAndLayers = async () => {
        try {
          let jsonApiResponse = await operation(
            'retrieve/api/v1/registry/wms/{id}/',
            [{
              in: 'path',
              name: 'id',
              value: String(wmsId),
            },
            {
              in: 'query',
              name: 'include',
              value: 'operationUrls'
            }]
          );          
          const getMapUrl = jsonApiResponse.data.included.filter((opUrl:any) => {
            return opUrl.attributes.method === 'Get' && opUrl.attributes.operation === 'GetMap';
          }).map ((opUrl:any) => {
            return opUrl.attributes.url;
          }).reduce ( 
            (acc:string, curr:string) => curr, null
          );
          const wmsAttrs = jsonApiResponse.data.data.attributes;
          const wmsVersion = wmsAttrs.version;

          jsonApiResponse = await operation(
            'List/api/v1/registry/wms/{parent_lookup_service}/layers/',
            [
              {
                in: 'path',
                name: 'parent_lookup_service',
                value: String(wmsId),
              },
              {
                in: 'query',
                name: 'fields[Layer]',
                value: 'title,identifier,parent'
              },
              {
                in: 'query',
                name: 'page[size]',
                value: '1000'
              },              
            ]
          );
          jsonApiResponse = await unpage(jsonApiResponse);

          // build children lookup dictionary
          const layerIdToChildren: any = {};
          jsonApiResponse.data?.data.forEach((layer: any) => {
            const parentId = layer.relationships?.parent?.data?.id;
            if (parentId) {
              const children: any[] = layerIdToChildren[parentId] || [];
              layerIdToChildren[parentId] = children;
              children.push(layer);
            }
          });

          const layerToOlLayer = (layer: any): BaseLayer => {
            const childLayers: [] | undefined = layerIdToChildren[layer.id];
            if (childLayers) {
              return new LayerGroup({
                layers: childLayers.map ((childLayer) => layerToOlLayer (childLayer)),
                visible: false,
                properties: {
                  key: layer.id,
                  name: layer.attributes.title,
                  isSecurityLayer: true
                }
              });
            }
            return new ImageLayer({
              source: new ImageWMS({
                url: getMapUrl,
                params: {
                  'LAYERS': layer.attributes.identifier,
                  'VERSION': wmsVersion,
                  'TRANSPARENT': true
                }
              }),
              properties: {
                name: layer.attributes.title,
                isSecurityLayer: true
              },                 
              visible: false              
            });
          };          
          wmsOlRootLayer = jsonApiResponse.data?.data
            .filter((layer: any) => !layer.relationships.parent.data)
            .map ((root: any) => {
              return layerToOlLayer (root);
            })[0];
          map.addLayer(wmsOlRootLayer as BaseLayer);
        } finally {
          setIsLoading(false);
        }
      };      
      fetchWmsAndLayers();
      return ( () => {
        wmsOlRootLayer && map.removeLayer(wmsOlRootLayer);
      });
    }
  }, [wmsId, map]);

  useEffect(() => {
    if (!isRuleEditingActive) {
      setSelectedLayerKeys([]);
    }
  }, [isRuleEditingActive]);

  if(isLoading) {
    return (<SyncOutlined spin />);
  }

  // add / remove clicked layer key (and descendants)
  const onLayerClick = (selectedKeys: any, info: any) => {
    if (!isRuleEditingActive) {
      return;
    }
    const keys: string[] = [];
    const addChildKeys = (node: any) => {
      keys.push(node.key);
      node.children?.forEach((child: any) => {
        addChildKeys(child);
      });
    };
    addChildKeys(info.node);
    const currentKeySet = new Set(selectedLayerKeys);
    if (info.selected) {
      keys.forEach( (key) => currentKeySet.add(key));
    } else {
      keys.forEach( (key) => currentKeySet.delete(key));
    }
    setSelectedLayerKeys(Array.from(currentKeySet).sort());
  };

  return (
    <>
      <div className='wms-security-layout'>
        <LeftDrawer>
          <LayerTree
            multiple
            showLine
            defaultExpandParent
            map={map}
            draggable={false}
            onSelect={onLayerClick}
            selectedKeys={selectedLayerKeys}
            filterFunction={ (value: any, index: number, array: any[]) => {
              return value.get('isSecurityLayer');
            }}
          />
        </LeftDrawer>
        <AutoResizeMapComponent id='the-map' />
        { 
          wmsId && 
            <RulesDrawer 
              wmsId={wmsId}
              selectedLayerIds={selectedLayerIds}
              setSelectedLayerIds={setSelectedLayerIds}
              setIsRuleEditingActive={setIsRuleEditingActive}
            /> 
        }
        {
          olMap && isRuleEditingActive && <AreaDigitizeToolbar map={olMap} /> 
        }
      </div>
    </>
  );
};
