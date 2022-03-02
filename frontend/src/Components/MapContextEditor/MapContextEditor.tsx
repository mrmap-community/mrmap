import { FolderAddOutlined, InfoCircleOutlined, MinusCircleFilled, SearchOutlined, SettingFilled, SettingOutlined } from '@ant-design/icons';
import { faLayerGroup } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import MapUtil from '@terrestris/ol-util/dist/MapUtil/MapUtil';
import { useMap } from '@terrestris/react-geo';
import { Button, Space, Tabs, Tooltip } from 'antd';
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
import { LayerSettingsForm } from './LayerSettingsForm/LayerSettingsForm';
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

  const [bottomDrawerVisible, setBottomDrawerVisible] = useState(true);
  const [activeTab, setActiveTab] = useState('mapSettings');


  const layerTitleInputRef = useRef<any>();

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
              .map ((childLayer) => layerToOlLayer (childLayer)),
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
      parent.getLayers().push(olLayer);
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
    layers.push(newLayerGroup);
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

  const onOpenLayerSettings = () => {
    setBottomDrawerVisible(true);
    setActiveTab('layerSettings');
    layerTitleInputRef.current?.focus();
  };

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
                <span><FontAwesomeIcon icon={faLayerGroup}/>&nbsp;&nbsp;&nbsp;Ebenen</span>
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
                      onClick={onOpenLayerSettings}
                      disabled={!selectedLayer}
                    />
                  </Tooltip>
                </Space>
              </div>
              <MapContextLayerTree
                mapContextId={id}
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
        <BottomDrawer
          map={map}
          visible={bottomDrawerVisible}
          onExpand={ expanded => setBottomDrawerVisible(!expanded) }
        >
          <Tabs
            tabPosition='left'
            activeKey={activeTab}
            onChange={activeKey => setActiveTab(activeKey)}
          >
            <TabPane
              tab={<span><InfoCircleOutlined />Karteneinstellungen</span>}
              key='mapSettings'
            >
              <MapContextSettings id={id}/>
            </TabPane>
            <TabPane
              tab={<span><SettingOutlined />Ebeneneinstellungen</span>}
              key='layerSettings'
              disabled={!id || !selectedLayer}
            >
              <LayerSettingsForm
                selectedLayer={selectedLayer}
                titleInputRef={layerTitleInputRef}
              />
            </TabPane>
            {/* <TabPane
              tab={<span><SettingOutlined />Layer settings (schema-based)</span>}
              key='layerSettings2'
              disabled={!id || !selectedLayer}
            >
              <MapContextLayerRepoForm
                layerGroup={olLayerGroup}
                selectedLayer={selectedLayer}
              />
            </TabPane> */}
            <TabPane
              tab={<span><SearchOutlined />Inhalte finden &amp; hinzufügen</span>}
              key='datasetSearch'
              disabled={!id}
            >
              <SearchTable addDatasetToMapAction={onAddDataset} />
            </TabPane>
          </Tabs>
        </BottomDrawer>
      }
    </>
  );
};
