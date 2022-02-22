import { MinusCircleFilled, SettingFilled } from '@ant-design/icons';
import { LayerTree, useMap } from '@terrestris/react-geo';
import { Button, Dropdown, Menu, Tooltip } from 'antd';
import { getUid } from 'ol';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import ImageWMS from 'ol/source/ImageWMS';
import { default as React, ReactElement, ReactNode, useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useParams } from 'react-router-dom';
import { JsonApiPrimaryData, ResourceIdentifierObject } from '../../Repos/JsonApiRepo';
import { unpage } from '../../Utils/JsonApiUtils';
import { AutoResizeMapComponent } from '../Shared/AutoResizeMapComponent/AutoResizeMapComponent';
import { LeftDrawer } from '../Shared/LeftDrawer/LeftDrawer';
import './MapContextEditor.css';

export const MapContextEditor = (): ReactElement => {

  const { id } = useParams();
  const map = useMap();

  // contains the layer hierarchy of the map context
  const [olLayerGroup, setOlLayerGroup] = useState<LayerGroup>();
  const [selectedLayer, setSelectedLayer] = useState<BaseLayer>();
  // lookup map for the OpenLayer layer objects, for a layer object, the ids can be retrieved like this:
  // - Layer id: property 'id'
  // - OpenLayers Uid: getUid(layer)
  const [olUidToLayer, setOlUidToLayer] = useState(new Map<string, BaseLayer>());

  const [
    getMapContext,
    {
      loading: getMapContextLoading,
      response: getMapContextResponse,
      api: getMapContextResponseApi
    }
  ] = useOperationMethod('getMapContext');

  // init: request map context and related data (map context layers, rendering layer, operation urls)
  useEffect(() => {
    if (id) {
      getMapContext([
        { name: 'id', value: String(id), in: 'path' },
        { name: 'include', value: 'mapContextLayers.renderingLayer.service.operationUrls', in: 'query' }
      ]);
    }
  }, [getMapContext, id]);

  // init: handle map context response: build layer tree
  useEffect(() => {
    let layerGroup: LayerGroup;
    const buildLayerTree = async () => {
      const fullResponse = await unpage(getMapContextResponse, getMapContextResponseApi);
      const mapContextLayers = fullResponse.data.included
        .filter((included: any) => included.type === 'MapContextLayer')
        .sort((a: any, b: any) => (
          (a.attributes.treeId - b.attributes.treeId) || (a.attributes.lft - b.attributes.lft))
        );

      // build lookup map: map context layer id -> children
      const layerIdToChildren: any = {};
      mapContextLayers.forEach((layer: any) => {
        const parentId = layer.relationships?.parent?.data?.id;
        if (parentId) {
          const children: any[] = layerIdToChildren[parentId] || [];
          layerIdToChildren[parentId] = children;
          children.push(layer);
        }
      });

      const newOlUidToLayer = new Map<string,BaseLayer>();

      // recursive function for building OL ImageLayers / LayerGroups from a MapContext layer
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
              name: layer.attributes.title
            }
          });
          olLayer.getLayers().forEach ( (childLayer: any) => childLayer.set('parent', olLayer));
        } else {
          let wmsLayer, wmsUrl, wmsVersion;
          // step 1: get WMS Layer
          if (layer.relationships?.renderingLayer?.data?.id) {
            const renderingLayer = fullResponse.data?.included.filter(
              (included: JsonApiPrimaryData) => included.type === 'Layer'
              && included.id === layer.relationships?.renderingLayer?.data?.id
            )[0];
            wmsLayer = renderingLayer.attributes.identifier;
            // step 2: get WebMapService
            const wms = fullResponse.data?.included.filter(
              (included: JsonApiPrimaryData) =>
                included.type === 'WebMapService' && included.id === renderingLayer.relationships.service.data.id
            )[0];
            wmsVersion = wms.attributes.version;
            // step 3: get OperationUrl ('GetMap')
            const getMapUrl = fullResponse.data?.included.filter(
              (item: JsonApiPrimaryData) =>
                item.type === 'WebMapServiceOperationUrl' &&
                wms.relationships.operationUrls.data.map (
                  (operationUrl: ResourceIdentifierObject) => operationUrl.id).includes(item.id) &&
                item.attributes.operation === 'GetMap' &&
                item.attributes.method === 'Get'
            )[0];
            wmsUrl = getMapUrl.attributes.url;
          }
          olLayer = new ImageLayer({
            source: new ImageWMS({
              url: wmsUrl || 'undefined',
              params: {
                'VERSION': wmsVersion,
                'LAYERS': wmsLayer,
                'TRANSPARENT': true
              }
            }),
            properties: {
              id: layer.id,
              name: layer.attributes.title
            },
            visible: false
          });
        }
        newOlUidToLayer.set(getUid(olLayer), olLayer);
        return olLayer;
      };

      const rootLayers = mapContextLayers.filter((layer: any) => !layer.relationships.parent.data);
      const olLayers = rootLayers.map((root: any) => layerToOlLayer(root));
      layerGroup = new LayerGroup({
        layers: olLayers.reverse(),
        visible: false,
        properties: {
          name: 'mrmap-mapcontext-layers'
        }
      });
      map.addLayer(layerGroup);
      setOlLayerGroup(layerGroup);
      setOlUidToLayer(newOlUidToLayer);
    };
    if (map && getMapContextResponse) {
      buildLayerTree();
      // componentDidUnmount: remove layer group
      return ( () => {
        layerGroup && map.removeLayer(layerGroup);
      });
    }
  }, [map, getMapContextResponse, getMapContextResponseApi]);

  const onSelect = (selectedKeys: any, info: any) => {
    if (info.selected) {
      setSelectedLayer(olUidToLayer.get(info.node.key) as BaseLayer);
    } else {
      setSelectedLayer(undefined);
    }
  };

  const renderNodeContextMenu = (layer: BaseLayer): ReactElement => {
    const removeLayer = () => {
      // TODO handle nested layers
      olLayerGroup?.getLayers().remove(layer);
    };

    return (
      <Menu
        className='tree-manager-context-menu'>
        <Menu.Item
          onClick={removeLayer}
          icon={<MinusCircleFilled />}
          key='remove-node'
        >
        Delete
        </Menu.Item>
      </Menu>
    );
  };

  const renderNodeTitle = (layer: BaseLayer): ReactNode => {
    return (
      <div className='mapcontext-layertree-node'>
        <div className='mapcontext-layertree-node-title'>{ layer.get('name') }</div>
        <div className='mapcontext-layertree-node-actions'>
          <Dropdown
            overlay={renderNodeContextMenu(layer)}
            trigger={['click']}
          >
            <Tooltip title='Node options'>
              <Button
                type='text'
                icon={<SettingFilled />}
              />
            </Tooltip>
          </Dropdown>
        </div>
      </div>
    );
  };

  const allowDrop = ({ dropNode, dropPosition }: {dropNode: any, dropPosition: any}) => {
    const layer = olUidToLayer.get(dropNode.key);
    // dropPosition: -1 (previous sibling)
    // dropPosition: 1 (next sibling)
    // dropPosition: 0 (first child)
    console.log('dropNode', dropNode);
    console.log('dropPosition', dropPosition);
    // disable dropping a new child of non-group layer
    return dropPosition !== 0 || layer instanceof LayerGroup;
  };

  return (
    <>
      <div className='mapcontext-editor-layout'>
        <LeftDrawer map={map}>
          {
            olLayerGroup &&
            <LayerTree
              draggable
              allowDrop={allowDrop}
              map={map}
              layerGroup={olLayerGroup}
              onSelect={onSelect}
              selectedKeys={selectedLayer ? [getUid(selectedLayer)] : []}
              nodeTitleRenderer={renderNodeTitle}
            />
          }
        </LeftDrawer>
        <AutoResizeMapComponent id='map' />
      </div>
    </>
  );
};
