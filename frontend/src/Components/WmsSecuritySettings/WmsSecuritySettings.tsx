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
import { LayerUtils } from '../../Utils/LayerUtils';
import { olMap } from '../../Utils/MapUtils';
import { AutoResizeMapComponent } from '../Shared/AutoResizeMapComponent/AutoResizeMapComponent';
import { AreaDigitizeToolbar } from './AreaDigitizeToolbar/AreaDigitizeToolbar';
import { LeftDrawer } from './LeftDrawer/LeftDrawer';
import { RulesDrawer } from './RulesDrawer/RulesDrawer';
import './WmsSecuritySettings.css';

const layerUtils = new LayerUtils();

export const WmsSecuritySettings = (): ReactElement => {

  const map = useMap();
  const { wmsId } = useParams();
  const [isLoading, setIsLoading] = useState<boolean>(false);
  // only when rule editing is active, are layers selectable and digitizing visible
  const [isRuleEditingActive, setIsRuleEditingActive] = useState<boolean>(false);

  // inconveniently, we have to deal with two ids per layer here
  // - Layer id (backend id)
  // - OpenLayers Uid (used by OpenLayers and the antd Tree component)
  const [selectedLayerIds, setSelectedLayerIds] = useState<string[]>([]);
  const [selectedOlUids, setSelectedOlUids] = useState<string[]>([]);
  // lookup maps for the OpenLayer layer objects, for a layer object, the ids can be retrieved like this:
  // - Layer id: property 'id'
  // - OpenLayers Uid: getUid(layer)
  const [olUidToLayer, setOlUidToLayer] = useState(new Map<string, BaseLayer>());
  const [layerIdToLayer, setLayerIdToLayer]  = useState(new Map<string, BaseLayer>());

  const [expandedOlUids, setExpandedOlUids] = useState<string[]>([]);

  useEffect(() => {
    if (wmsId) {
      setIsLoading(true);
      let wmsOlRootLayer: BaseLayer | undefined;
      const fetchWmsAndLayers = async () => {
        try {
          let jsonApiResponse = await operation(
            'getWebMapService',
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
            'listLayer',
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

          const newLayerIdToLayer = new Map<string,BaseLayer>();
          const newOlUidToLayer = new Map<string,BaseLayer>();
          const newExpandedOlUids: string[] = [];

          const layerToOlLayer = (layer: any): BaseLayer => {
            const childLayers: [] | undefined = layerIdToChildren[layer.id];
            let olLayer: any;
            if (childLayers) {
              olLayer = new LayerGroup({
                layers: childLayers
                  .map ((childLayer) => layerToOlLayer (childLayer)).reverse(),
                visible: false,
                properties: {
                  id: layer.id,
                  name: layer.attributes.title,
                  isSecurityLayer: true
                }
              });
              olLayer.getLayers().forEach ( (childLayer: any) => childLayer.set('parent', olLayer));
              newExpandedOlUids.push(getUid(olLayer));
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
                  id: layer.id,
                  name: layer.attributes.title,
                  isSecurityLayer: true
                },
                visible: false
              });
            }
            newLayerIdToLayer.set(layer.id, olLayer);
            newOlUidToLayer.set(getUid(olLayer), olLayer);
            return olLayer;
          };
          wmsOlRootLayer = jsonApiResponse.data?.data
            .filter((layer: any) => !layer.relationships.parent.data)
            .map ((root: any) => {
              return layerToOlLayer (root);
            })[0];
          map.addLayer(wmsOlRootLayer as BaseLayer);
          setOlUidToLayer(newOlUidToLayer);
          setLayerIdToLayer(newLayerIdToLayer);
          setExpandedOlUids(newExpandedOlUids);
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
    setSelectedOlUids(selectedLayerIds.map( (layerId) => getUid(layerIdToLayer.get(layerId))));
  }, [selectedLayerIds, layerIdToLayer]);

  if(isLoading) {
    return (<SyncOutlined spin />);
  }

  // the backend always expects complete layer subtrees to be selected
  // when selecting a layer, we also select all descendants
  // when unselecting layer, we find the root of the current subtree and unselect all its descendants
  const onSelect = (selectedKeys: any, info: any) => {
    if (!isRuleEditingActive) {
      return;
    }
    let olLayer: BaseLayer = olUidToLayer.get(info.node.key) as BaseLayer;
    const newSelectedLayerIds = new Set(selectedLayerIds);
    if (info.selected) {
      layerUtils
        .getAllSubtreeLayers(olLayer)
        .forEach (layer => newSelectedLayerIds.add(layer.get('id')));
    } else {
      // when unselecting, use root of the selection subtree the clicked node belongs to
      let parentLayer = olLayer.get('parent');
      // eslint-disable-next-line no-loop-func
      while (parentLayer && selectedKeys.some ((key: any) => key === getUid(parentLayer) )) {
        olLayer = parentLayer;
        parentLayer = olLayer.get('parent');
      }
      layerUtils
        .getAllSubtreeLayers(olLayer)
        .forEach (layer => newSelectedLayerIds.delete(layer.get('id')));
    }
    setSelectedLayerIds(Array.from(newSelectedLayerIds).sort());
  };

  return (
    <>
      <div className='wms-security-layout'>
        <LeftDrawer>
          <LayerTree
            multiple
            showLine
            map={map}
            draggable={false}
            onSelect={onSelect}
            selectedKeys={selectedOlUids}
            filterFunction={ (value: any, index: number, array: any[]) => {
              return value.get('isSecurityLayer');
            }}
            expandedKeys={expandedOlUids}
            switcherIcon={<></>}
            /* workaround for node expansion bug: https://codesandbox.io/s/antd-reproduction-template-forked-zxzdf */
            defaultExpandParent={false}
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
