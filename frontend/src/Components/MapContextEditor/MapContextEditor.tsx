import { FolderAddOutlined, MinusCircleFilled, SettingFilled } from '@ant-design/icons';
import MapUtil from '@terrestris/ol-util/dist/MapUtil/MapUtil';
import { useMap } from '@terrestris/react-geo';
import { Button, Space, Tooltip } from 'antd';
import { getUid } from 'ol';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import ImageWMS from 'ol/source/ImageWMS';
import { default as React, ReactElement, useEffect, useRef, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useParams } from 'react-router-dom';
import { JsonApiPrimaryData, ResourceIdentifierObject } from '../../Repos/JsonApiRepo';
import { unpage } from '../../Utils/JsonApiUtils';
import { AutoResizeMapComponent } from '../Shared/AutoResizeMapComponent/AutoResizeMapComponent';
import { BottomDrawer } from '../Shared/BottomDrawer/BottomDrawer';
import { LeftDrawer } from '../Shared/LeftDrawer/LeftDrawer';
import './MapContextEditor.css';
import { MapContextLayerTree } from './MapContextLayerTree/MapContextLayerTree';

export const MapContextEditor = (): ReactElement => {

  const { id } = useParams();
  const map = useMap();

  // contains the layer hierarchy of the map context
  const [olLayerGroup, setOlLayerGroup] = useState<LayerGroup>();
  const [selectedLayer, setSelectedLayer] = useState<BaseLayer>();

  // OpenLayers collection events do not distinguish between remove and a remove followed by an add (move)
  // so we track if we started a remove
  const removeLayerInProgress = useRef(false);

  const [
    getMapContext,
    {
      // loading: getMapContextLoading,
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

  // init: handle map context response: build layer group
  useEffect(() => {
    let layerGroup: LayerGroup;
    const buildLayerTree = async () => {
      const fullResponse = await unpage(getMapContextResponse, getMapContextResponseApi);
      // at least one layer *must* exist
      const mapContextLayers = fullResponse.data.included
        .filter((included: any) => included.type === 'MapContextLayer')
        .sort((a: any, b: any) => (
          (a.attributes.treeId - b.attributes.treeId) || (a.attributes.lft - b.attributes.lft))
        );

      // build lookup map: map context layer id -> children
      const layerIdToChildren: any = {};
      mapContextLayers?.forEach((layer: any) => {
        const parentId = layer.relationships?.parent?.data?.id;
        if (parentId) {
          const children: any[] = layerIdToChildren[parentId] || [];
          layerIdToChildren[parentId] = children;
          children.push(layer);
        }
      });

      // recursive function for building OL ImageLayers / LayerGroups from MapContext layer
      const layerToOlLayer = (layer: any): BaseLayer => {
        const childLayers = layerIdToChildren[layer.id] || [];
        let olLayer: any;
        if (!layer.relationships.parent.data || childLayers.length === 0) {
          olLayer = new LayerGroup({
            layers: childLayers
              .map ((childLayer) => layerToOlLayer (childLayer)).reverse(),
            visible: false,
            properties: {
              id: layer.id,
              name: layer.attributes.title,
            }
          });
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
              name: layer.attributes.title,
            },
            visible: false
          });
        }
        return olLayer;
      };

      const rootLayer = mapContextLayers.filter((layer: any) => !layer.relationships.parent.data)[0];
      layerGroup = layerToOlLayer(rootLayer) as LayerGroup;
      map.addLayer(layerGroup);
      setOlLayerGroup(layerGroup);
    };
    if (map && getMapContextResponse) {
      buildLayerTree();
      // componentDidUnmount: remove layer group
      return ( () => {
        layerGroup && map.removeLayer(layerGroup);
      });
    }
  }, [map, getMapContextResponse, getMapContextResponseApi]);

  const onSelectLayer = (selectedKeys: any, info: any) => {
    if (info.selected) {
      setSelectedLayer(MapUtil.getLayerByOlUid(map,info.node.key));
    } else {
      setSelectedLayer(undefined);
    }
  };

  const onCreateLayerGroup = () => {
    const parent: any = selectedLayer instanceof LayerGroup ? selectedLayer : olLayerGroup;
    const layerGroup = new LayerGroup({
      visible: false,
      properties: {
        name: 'New Layer Group',
      }
    });
    parent.getLayers().insertAt(0, layerGroup);
  };

  const onDeleteLayer = () => {
    if (selectedLayer) {
      removeLayerInProgress.current = true;
      MapUtil
        .getAllLayers(map)
        .filter((layer: BaseLayer) => layer instanceof LayerGroup)
        .forEach((layer: LayerGroup) => {
          layer.getLayers().remove(selectedLayer);
        });
      setSelectedLayer(undefined);
    }
  };

  return (
    <>
      <div className='mapcontext-editor-layout'>
        <LeftDrawer map={map}>
          {
            olLayerGroup &&
            <div className='mapcontext-layertree-layout'>
              <div
                className='mapcontext-layertree-header'
              >
                Layers
                <Space>
                  <Tooltip title='Create new layer group'>
                    <Button
                      icon={<FolderAddOutlined />}
                      size='middle'
                      onClick={onCreateLayerGroup}
                    />
                  </Tooltip>
                  <Tooltip title='Delete layer'>
                    <Button
                      icon={<MinusCircleFilled />}
                      size='middle'
                      onClick={onDeleteLayer}
                      disabled={!selectedLayer}
                    />
                  </Tooltip>
                  <Tooltip title='Layer settings'>
                    <Button
                      icon={<SettingFilled />}
                      size='middle'
                      disabled={!selectedLayer}
                    />
                  </Tooltip>
                </Space>
              </div>
              {
                id &&
                <MapContextLayerTree
                  id={id}
                  map={map}
                  olLayerGroup={olLayerGroup}
                  onSelect={onSelectLayer}
                  selectedKeys={selectedLayer ? [getUid(selectedLayer)] : []}
                  removeLayerInProgress={removeLayerInProgress}
                />
              }
            </div>
          }
        </LeftDrawer>
        <AutoResizeMapComponent id='map' />
      </div>
      <BottomDrawer map={map} />
    </>
  );
};
