import { SyncOutlined } from '@ant-design/icons';
import { LayerTree, useMap } from '@terrestris/react-geo';
import { getUid } from 'ol';
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
  // only when rule editing is active, are layers selectable and digitizing visible
  const [isRuleEditingActive, setIsRuleEditingActive] = useState<boolean>(false);

  const [selectedLayerIds, setSelectedLayerIds] = useState<string[]>([]);
  const [selectedOlUids, setSelectedOlUids] = useState<string[]>([]);
  const [layerIdToOlUid, setLayerIdToOlUid]  = useState(new Map<string, string>());
  const [olUidToLayerId, setOlUidToLayerId] = useState(new Map<string, string>());

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

          const newLayerIdToOlUid = new Map<string,string>();
          const newOlUidToLayerId = new Map<string,string>();

          const layerToOlLayer = (layer: any): BaseLayer => {
            const childLayers: [] | undefined = layerIdToChildren[layer.id];
            let olLayer;
            if (childLayers) {
              olLayer = new LayerGroup({
                layers: childLayers.map ((childLayer) => layerToOlLayer (childLayer)).reverse(),
                visible: false,
                properties: {
                  key: layer.id,
                  name: layer.attributes.title,
                  isSecurityLayer: true
                }
              });
            } else {
              olLayer = new ImageLayer({
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
            }
            newLayerIdToOlUid.set(layer.id, getUid(olLayer));
            newOlUidToLayerId.set(getUid(olLayer), layer.id);
            return olLayer;
          };          
          wmsOlRootLayer = jsonApiResponse.data?.data
            .filter((layer: any) => !layer.relationships.parent.data)
            .map ((root: any) => {
              return layerToOlLayer (root);
            })[0];
          map.addLayer(wmsOlRootLayer as BaseLayer);
          setLayerIdToOlUid(newLayerIdToOlUid);
          setOlUidToLayerId(newOlUidToLayerId);
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
      setSelectedLayerIds([]);
    }
  }, [isRuleEditingActive]);

  useEffect(() => {
    setSelectedOlUids(selectedLayerIds.map( (layerId) => layerIdToOlUid.get(layerId) as string));
  }, [selectedLayerIds, layerIdToOlUid]);

  if(isLoading) {
    return (<SyncOutlined spin />);
  }

  // the backend always expects complete layer subtrees to be selected
  // when selecting a layer, we also select all ancestors
  // when unselecting layer, we also unselect all descendants
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
    const currentKeySet = new Set(selectedLayerIds.map( (id) => layerIdToOlUid.get(id) || ''));
    if (info.selected) {
      keys.forEach( (key) => currentKeySet.add(key));
    } else {
      keys.forEach( (key) => currentKeySet.delete(key));
    }
    setSelectedLayerIds(Array.from(currentKeySet).map( (key) => (olUidToLayerId.get(key) as string)).sort());
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
            selectedKeys={selectedOlUids}
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
