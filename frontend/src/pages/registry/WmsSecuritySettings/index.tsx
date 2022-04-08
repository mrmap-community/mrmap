import { AutoResizeMapComponent } from '@/components/AutoResizeMapComponent';
import { LeftDrawer } from '@/components/LeftDrawer';
import { unpage } from '@/utils/jsonapi';
import { getAllSubtreeLayers } from '@/utils/map';
import { SyncOutlined } from '@ant-design/icons';
import { LayerTree, useMap } from '@terrestris/react-geo';
import { getUid } from 'ol';
import type BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import ImageWMS from 'ol/source/ImageWMS';
import type { ReactElement } from 'react';
import { useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useParams } from 'react-router';
import AreaDigitizeToolbar from './components/AreaDigitizeToolbar';
import { RulesDrawer } from './components/RulesDrawer';
import './WmsSecuritySettings.css';

export const WmsSecuritySettings = (): ReactElement => {
  const map = useMap();
  const { id } = useParams<{ id: string }>();
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
  const [layerIdToLayer, setLayerIdToLayer] = useState(new Map<string, BaseLayer>());

  const [expandedOlUids, setExpandedOlUids] = useState<string[]>([]);

  const [getWebMapService, { loading: getWMSLoading, response: getWMSResponse }] =
    useOperationMethod('getWebMapService');
  const [listLayer, { loading: listLayerLoading, response: listLayerResponse, api: listLayerApi }] =
    useOperationMethod('listLayerByWebMapService');

  useEffect(() => {
    let olLayerGroup: LayerGroup;
    // TODO: move unpaging in custom useOperationMethod hook?
    async function buildLayerTree() {
      // WMS specific stuff
      const getMapUrl = getWMSResponse.data.included
        .filter((opUrl: any) => {
          return opUrl.attributes.method === 'Get' && opUrl.attributes.operation === 'GetMap';
        })
        .map((opUrl: any) => {
          return opUrl.attributes.url;
        })
        .reduce((acc: string, curr: string) => curr, null);
      const wmsAttrs = getWMSResponse.data.data.attributes;
      const wmsVersion = wmsAttrs.version;

      // layer specific stuff
      // build children lookup dictionary
      const unpagedLayerResponse = await unpage(listLayerResponse, listLayerApi);

      const layerIdToChildren: any = {};
      unpagedLayerResponse.data?.data.forEach((layer: any) => {
        const parentId = layer.relationships?.parent?.data?.id;
        if (parentId) {
          const children: any[] = layerIdToChildren[parentId] || [];
          layerIdToChildren[parentId] = children;
          children.push(layer);
        }
      });

      const newLayerIdToLayer = new Map<string, BaseLayer>();
      const newOlUidToLayer = new Map<string, BaseLayer>();
      const newExpandedOlUids: string[] = [];

      const layerToOlLayer = (layer: any): BaseLayer => {
        const childLayers: [] | undefined = layerIdToChildren[layer.id];
        let olLayer: any;
        if (childLayers) {
          olLayer = new LayerGroup({
            layers: childLayers.map((childLayer) => layerToOlLayer(childLayer)).reverse(),
            visible: false,
            properties: {
              id: layer.id,
              name: layer.attributes.title,
              isSecurityLayer: true,
            },
          });
          olLayer.getLayers().forEach((childLayer: any) => childLayer.set('parent', olLayer));
          newExpandedOlUids.push(getUid(olLayer));
        } else {
          olLayer = new ImageLayer({
            source: new ImageWMS({
              url: getMapUrl,
              params: {
                LAYERS: layer.attributes.identifier,
                VERSION: wmsVersion,
                TRANSPARENT: true,
              },
            }),
            properties: {
              id: layer.id,
              name: layer.attributes.title,
              isSecurityLayer: true,
            },
            visible: false,
          });
        }
        newLayerIdToLayer.set(layer.id, olLayer);
        newOlUidToLayer.set(getUid(olLayer), olLayer);
        return olLayer;
      };

      olLayerGroup = unpagedLayerResponse.data?.data
        .filter((layer: any) => !layer.relationships.parent.data)
        .map((root: any) => {
          return layerToOlLayer(root);
        })[0];

      if (map) {
        map.addLayer(olLayerGroup);
      }
      setOlUidToLayer(newOlUidToLayer);
      setLayerIdToLayer(newLayerIdToLayer);
      setExpandedOlUids(newExpandedOlUids);
    }
    if (getWMSResponse && listLayerResponse) {
      buildLayerTree();
      // componentDidUnmount: remove layer group
      return () => {
        if (olLayerGroup && map) {
          map.removeLayer(olLayerGroup);
        }
      };
    }
  }, [getWMSResponse, listLayerApi, listLayerResponse, map]);

  console.log('id', id);

  useEffect(() => {
    if (id) {
      getWebMapService([
        {
          in: 'path',
          name: 'id',
          value: String(id),
        },
        {
          in: 'query',
          name: 'include',
          value: 'operationUrls',
        },
      ]);

      listLayer([
        {
          in: 'path',
          name: 'parent_lookup_service',
          value: String(id),
        },
        {
          in: 'query',
          name: 'fields[Layer]',
          value: 'title,identifier,parent',
        },
        {
          in: 'query',
          name: 'page[size]',
          value: '1000',
        },
      ]);
    }
  }, [getWebMapService, listLayer, id]);

  useEffect(() => {
    if (!isRuleEditingActive) {
      setSelectedLayerIds([]);
    }
  }, [isRuleEditingActive]);

  useEffect(() => {
    setSelectedOlUids(selectedLayerIds.map((layerId) => getUid(layerIdToLayer.get(layerId))));
  }, [selectedLayerIds, layerIdToLayer]);

  if (getWMSLoading || listLayerLoading) {
    return <SyncOutlined spin />;
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
      getAllSubtreeLayers(olLayer).forEach((layer: BaseLayer) =>
        newSelectedLayerIds.add(layer.get('id')),
      );
    } else {
      // when unselecting, use root of the selection subtree the clicked node belongs to
      let parentLayer = olLayer.get('parent');
      // eslint-disable-next-line no-loop-func
      const hasParentLayer = (key: any) => key === getUid(parentLayer);
      while (parentLayer && selectedKeys.some(hasParentLayer)) {
        olLayer = parentLayer;
        parentLayer = olLayer.get('parent');
      }
      getAllSubtreeLayers(olLayer).forEach((layer) => newSelectedLayerIds.delete(layer.get('id')));
    }
    setSelectedLayerIds(Array.from(newSelectedLayerIds).sort());
  };

  return (
    <div className="wms-security-layout">
      {map && (
        <LeftDrawer map={map}>
          <LayerTree
            multiple
            showLine
            map={map}
            draggable={false}
            onSelect={onSelect}
            selectedKeys={selectedOlUids}
            filterFunction={(value: any) => {
              return value.get('isSecurityLayer');
            }}
            expandedKeys={expandedOlUids}
            switcherIcon={<></>}
            /* workaround for node expansion bug: https://codesandbox.io/s/antd-reproduction-template-forked-zxzdf */
            defaultExpandParent={false}
          />
        </LeftDrawer>
      )}
      <AutoResizeMapComponent id="map" />
      {map && id && (
        <RulesDrawer
          map={map}
          wmsId={id}
          selectedLayerIds={selectedLayerIds}
          setSelectedLayerIds={setSelectedLayerIds}
          setIsRuleEditingActive={setIsRuleEditingActive}
        />
      )}
      {map && isRuleEditingActive && <AreaDigitizeToolbar map={map} />}
    </div>
  );
};

export default WmsSecuritySettings;
