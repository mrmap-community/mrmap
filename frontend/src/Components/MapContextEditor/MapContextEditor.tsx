import { FolderAddOutlined, MinusCircleFilled, SearchOutlined, SettingFilled, SettingOutlined } from '@ant-design/icons';
import { faLayerGroup } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import MapUtil from '@terrestris/ol-util/dist/MapUtil/MapUtil';
import { useMap } from '@terrestris/react-geo';
import { Button, Space, Tabs, Tooltip } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import { getUid } from 'ol';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import ImageWMS from 'ol/source/ImageWMS';
import { AxiosResponse } from 'openapi-client-axios';
import { default as React, ReactElement, useEffect, useRef, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useParams } from 'react-router-dom';
import { JsonApiPrimaryData, ResourceIdentifierObject } from '../../Repos/JsonApiRepo';
import { unpage } from '../../Utils/JsonApiUtils';
import { AutoResizeMapComponent } from '../Shared/AutoResizeMapComponent/AutoResizeMapComponent';
import { BottomDrawer } from '../Shared/BottomDrawer/BottomDrawer';
import { LeftDrawer } from '../Shared/LeftDrawer/LeftDrawer';
import RepoForm from '../Shared/RepoForm/RepoForm';
import './MapContextEditor.css';
import { MapContextLayerTree } from './MapContextLayerTree/MapContextLayerTree';
import { MapContextSettings } from './MapContextSettings/MapContextSettings';
import { SearchTable } from './SearchTable/SearchTable';

const { TabPane } = Tabs;

export const MapContextEditor = (): ReactElement => {

  const { id } = useParams();
  const map = useMap();

  // we use this OpenLayers layer group as the source of truth, each layer / group has the corresponding JSON:API
  // MapContextLayer entity attached to it (property 'mapContextLayer')
  const [olLayerGroup, setOlLayerGroup] = useState<LayerGroup>();
  const [selectedLayer, setSelectedLayer] = useState<BaseLayer>();

  // OpenLayers collection events do not distinguish between remove and a remove followed by an add (move)
  // so we track if we started a remove
  const removeLayerInProgress = useRef(false);

  const addingDataset = useRef<any>();

  const [
    getMapContext,
    {
      response: getMapContextResponse,
      api: getMapContextResponseApi
    }
  ] = useOperationMethod('getMapContext');

  const [
    getLayer,
    {
      response: getLayerResponse
    }
  ] = useOperationMethod('getLayer');

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
        // no rendering layer -> WMS Layer in tree
        if (layer.relationships?.renderingLayer?.data?.id) {
          // step 1: get WMS Layer
          const renderingLayer = fullResponse.data?.included.filter(
            (included: JsonApiPrimaryData) => included.type === 'Layer'
              && included.id === layer.relationships?.renderingLayer?.data?.id
          )[0];
          const wmsLayer = renderingLayer.attributes.identifier;
          // step 2: get WebMapService
          const wms = fullResponse.data?.included.filter(
            (included: JsonApiPrimaryData) =>
              included.type === 'WebMapService' && included.id === renderingLayer.relationships.service.data.id
          )[0];
          const wmsVersion = wms.attributes.version;
          // step 3: get OperationUrl ('GetMap')
          const getMapUrl = fullResponse.data?.included.filter(
            (item: JsonApiPrimaryData) =>
              item.type === 'WebMapServiceOperationUrl' &&
                wms.relationships.operationUrls.data.map (
                  (operationUrl: ResourceIdentifierObject) => operationUrl.id).includes(item.id) &&
                item.attributes.operation === 'GetMap' &&
                item.attributes.method === 'Get'
          )[0];
          const wmsUrl = getMapUrl.attributes.url;
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
              mapContextLayer: layer
            },
            visible: false
          });
        } else {
          olLayer = new LayerGroup({
            layers: childLayers
              .map ((childLayer) => layerToOlLayer (childLayer)).reverse(),
            visible: false,
            properties: {
              mapContextLayer: layer
            }
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

  // update: handle layer response (when adding a dataset)
  useEffect(() => {
    if (olLayerGroup && getLayerResponse) {
      const layerId = getLayerResponse.data.data.attributes.identifier;
      const wms = getLayerResponse.data?.included.filter(
        (included: JsonApiPrimaryData) =>
          included.type === 'WebMapService' &&
          included.id === getLayerResponse.data.data.relationships.service.data.id
      )[0];
      const wmsVersion = wms.attributes.version;
      const getMapUrl = getLayerResponse.data?.included.filter(
        (item: JsonApiPrimaryData) =>
          item.type === 'WebMapServiceOperationUrl' &&
          wms.relationships.operationUrls.data.map (
            (operationUrl: ResourceIdentifierObject) => operationUrl.id).includes(item.id) &&
            item.attributes.operation === 'GetMap' &&
            item.attributes.method === 'Get'
      )[0];
      const wmsUrl = getMapUrl.attributes.url;
      const olLayer = new ImageLayer({
        source: new ImageWMS({
          url: wmsUrl || 'undefined',
          params: {
            'VERSION': wmsVersion,
            'LAYERS': layerId,
            'TRANSPARENT': true
          }
        }),
        properties: {
          mapContextLayer: {
            type: 'MapContextLayer',
            attributes: {
              title: getLayerResponse.data.data.attributes.title,
              description: addingDataset.current.abstract
            },
            relationships: {
              datasetMetadata: {
                data: {
                  type: 'DatasetMetadata',
                  id: addingDataset.current.id
                }
              },
              renderingLayer: {
                data: {
                  type: 'Layer',
                  id: addingDataset.current.layers[0]
                }
              }
            }
          }
        },
        visible: false
      });
      const parent: any = selectedLayer instanceof LayerGroup ? selectedLayer : olLayerGroup;
      parent.getLayers().insertAt(0, olLayer);
    }
  }, [olLayerGroup, getLayerResponse]);

  const onSelectLayer = (selectedKeys: any, info: any) => {
    if (info.selected) {
      setSelectedLayer(MapUtil.getLayerByOlUid(map,info.node.key));
    } else {
      setSelectedLayer(undefined);
    }
  };

  const onCreateLayerGroup = () => {
    const parent: any = selectedLayer instanceof LayerGroup ? selectedLayer : olLayerGroup;
    const layers = parent.getLayers();
    let free = 1;
    const groupNameTaken = (i: number) => {
      return layers.getArray().some( (l: BaseLayer) =>
        l.get('mapContextLayer').attributes.title === (i === 1 ? 'New Layer Group' : `New Layer Group (${i})`));
    };
    while (groupNameTaken(free)) {
      free++;
    }
    const newLayerGroup = new LayerGroup({
      visible: false,
      properties: {
        mapContextLayer: {
          type: 'MapContextLayer',
          attributes: {
            title: (free === 1 ? 'New Layer Group' : `New Layer Group (${free})`)
          }
        }
      }
    });
    layers.insertAt(0, newLayerGroup);
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

  const onAddDataset = (dataset: any) => {
    if (!dataset.layers || dataset.layers.length !== 1) {
      alert(`Dataset ${dataset.id} does not have exactly one layer.`);
      return;
    }
    addingDataset.current = dataset;
    const layerId = dataset.layers[0];
    getLayer([
      { name: 'id', value: layerId, in: 'path' },
      { name: 'include', value: 'service.operationUrls', in: 'query' }
    ]);
  };

  const onLayerSettingsChanged = (response: AxiosResponse) => {
    const layer: BaseLayer = MapUtil
      .getAllLayers(olLayerGroup)
      .filter((l: BaseLayer) => l.get('mapContextLayer').id === response.data.data.id)[0];
    layer.set('mapContextLayer', response.data.data);
    layer.changed();
  };

  const [form] = useForm();

  return (
    <>
      <div className='mapcontext-editor-layout'>
        { id && <LeftDrawer map={map}>
          {
            olLayerGroup &&
            <div className='mapcontext-layertree-layout'>
              <div
                className='mapcontext-layertree-header'
              >
                <span><FontAwesomeIcon icon={faLayerGroup}/>&nbsp;&nbsp;&nbsp;Layers</span>
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
              <MapContextLayerTree
                id={id}
                map={map}
                olLayerGroup={olLayerGroup}
                onSelect={onSelectLayer}
                selectedKeys={selectedLayer ? [getUid(selectedLayer)] : []}
                removeLayerInProgress={removeLayerInProgress}
              />
            </div>
          }
        </LeftDrawer>
        }
        <AutoResizeMapComponent id='map' />
      </div>
      {
        <BottomDrawer map={map}>
          <Tabs tabPosition='left'>
            <TabPane tab={<span><SettingOutlined />Map settings</span>} key='1'>
              <MapContextSettings id={id}/>
            </TabPane>
            <TabPane tab={<span><SettingOutlined />Layer settings</span>} key='2' disabled={!id || !selectedLayer}>
              <RepoForm
                resourceType='MapContextLayer'
                resourceId={selectedLayer && selectedLayer.get('mapContextLayer').id}
                form={form}
                onSuccess={onLayerSettingsChanged}
              />
            </TabPane>
            <TabPane tab={<span><SearchOutlined />Dataset search</span>} key='3' disabled={!id}>
              <SearchTable addDatasetToMapAction={onAddDataset} />
            </TabPane>
          </Tabs>
        </BottomDrawer>
      }
    </>
  );
};
