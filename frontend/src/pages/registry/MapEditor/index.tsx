import { AutoResizeMapComponent } from '@/components/AutoResizeMapComponent';
import { BottomDrawer } from '@/components/BottomDrawer';
import { LeftDrawer } from '@/components/LeftDrawer';
import type { JsonApiPrimaryData, ResourceIdentifierObject } from '@/utils/jsonapi';
import { unpage } from '@/utils/jsonapi';
import {
  FolderAddOutlined,
  InfoCircleOutlined,
  MinusCircleFilled,
  SearchOutlined,
  SettingFilled,
  SettingOutlined,
} from '@ant-design/icons';
import { faLayerGroup } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import MapUtil from '@terrestris/ol-util/dist/MapUtil/MapUtil';
import { useMap } from '@terrestris/react-geo';
import { Button, Space, Tabs, Tooltip } from 'antd';
import { getUid } from 'ol';
import type BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import ImageWMS from 'ol/source/ImageWMS';
import type { ReactElement } from 'react';
import { useEffect, useRef, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useParams } from 'react-router-dom';
import { FormattedMessage, useIntl } from 'umi';
import LayerSettingsForm from './components/LayerSettingsForm';
import MapEditorLayerTree from './components/MapEditorLayerTree';
import MapSettingsForm from './components/MapSettingsForm';
import SearchTable from './components/SearchTable';
import './index.css';

const { TabPane } = Tabs;

const MapEditor = (): ReactElement => {
  const { id } = useParams<{ id: string }>();
  const map = useMap();
  const intl = useIntl();

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

  const [getMapContext, { response: getMapContextResponse, api: getMapContextResponseApi }] =
    useOperationMethod('getMapContext');

  const [getLayer, { response: getLayerResponse }] = useOperationMethod('getLayer');

  // init: request map context and related data (map context layers, rendering layer, operation urls)
  useEffect(() => {
    if (id) {
      getMapContext([
        { name: 'id', value: String(id), in: 'path' },
        {
          name: 'include',
          value: 'mapContextLayers.renderingLayer.service.operationUrls',
          in: 'query',
        },
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
        .sort(
          (a: any, b: any) =>
            a.attributes.treeId - b.attributes.treeId || a.attributes.lft - b.attributes.lft,
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
            (included: JsonApiPrimaryData) =>
              included.type === 'Layer' &&
              included.id === layer.relationships?.renderingLayer?.data?.id,
          )[0];
          const wmsLayer = renderingLayer.attributes.identifier;
          // step 2: get WebMapService
          const wms = fullResponse.data?.included.filter(
            (included: JsonApiPrimaryData) =>
              included.type === 'WebMapService' &&
              included.id === renderingLayer.relationships.service.data.id,
          )[0];
          const wmsVersion = wms.attributes.version;
          // step 3: get OperationUrl ('GetMap')
          const getMapUrl = fullResponse.data?.included.filter(
            (item: JsonApiPrimaryData) =>
              item.type === 'WebMapServiceOperationUrl' &&
              wms.relationships.operationUrls.data
                .map((operationUrl: ResourceIdentifierObject) => operationUrl.id)
                .includes(item.id) &&
              item.attributes.operation === 'GetMap' &&
              item.attributes.method === 'Get',
          )[0];
          const wmsUrl = getMapUrl.attributes.url;
          olLayer = new ImageLayer({
            source: new ImageWMS({
              url: wmsUrl || 'undefined',
              params: {
                VERSION: wmsVersion,
                LAYERS: wmsLayer,
                TRANSPARENT: true,
              },
            }),
            properties: {
              mapContextLayer: layer,
            },
            visible: false,
          });
        } else {
          olLayer = new LayerGroup({
            layers: childLayers.map((childLayer: any) => layerToOlLayer(childLayer)),
            visible: false,
            properties: {
              mapContextLayer: layer,
            },
          });
        }
        return olLayer;
      };

      const rootLayer = mapContextLayers.filter(
        (layer: any) => !layer.relationships.parent.data,
      )[0];
      layerGroup = layerToOlLayer(rootLayer) as LayerGroup;
      if (map) {
        map.addLayer(layerGroup);
      }
      setOlLayerGroup(layerGroup);
    };

    if (map && getMapContextResponse) {
      buildLayerTree();
      // componentDidUnmount: remove layer group
      return () => {
        if (layerGroup) {
          map.removeLayer(layerGroup);
        }
      };
    }
    return () => {};
  }, [map, getMapContextResponse, getMapContextResponseApi]);

  // update: handle layer response (when adding a dataset)
  useEffect(() => {
    if (olLayerGroup && getLayerResponse) {
      const layerId = getLayerResponse.data.data.attributes.identifier;
      const wms = getLayerResponse.data?.included.filter(
        (included: JsonApiPrimaryData) =>
          included.type === 'WebMapService' &&
          included.id === getLayerResponse.data.data.relationships.service.data.id,
      )[0];
      const wmsVersion = wms.attributes.version;
      const getMapUrl = getLayerResponse.data?.included.filter(
        (item: JsonApiPrimaryData) =>
          item.type === 'WebMapServiceOperationUrl' &&
          wms.relationships.operationUrls.data
            .map((operationUrl: ResourceIdentifierObject) => operationUrl.id)
            .includes(item.id) &&
          item.attributes.operation === 'GetMap' &&
          item.attributes.method === 'Get',
      )[0];
      const wmsUrl = getMapUrl.attributes.url;
      const olLayer = new ImageLayer({
        source: new ImageWMS({
          url: wmsUrl || 'undefined',
          params: {
            VERSION: wmsVersion,
            LAYERS: layerId,
            TRANSPARENT: true,
          },
        }),
        properties: {
          mapContextLayer: {
            type: 'MapContextLayer',
            attributes: {
              title: getLayerResponse.data.data.attributes.title,
              description: addingDataset.current.abstract,
            },
            relationships: {
              datasetMetadata: {
                data: {
                  type: 'DatasetMetadata',
                  id: addingDataset.current.id,
                },
              },
              renderingLayer: {
                data: {
                  type: 'Layer',
                  id: addingDataset.current.relationships.selfPointingLayers.data[0].id,
                },
              },
            },
          },
        },
        visible: false,
      });
      const parent: any = selectedLayer instanceof LayerGroup ? selectedLayer : olLayerGroup;
      parent.getLayers().push(olLayer);
    }
  }, [olLayerGroup, getLayerResponse, selectedLayer]);

  const onSelectLayer = (selectedKeys: any, info: any) => {
    if (map && info.selected) {
      setSelectedLayer(MapUtil.getLayerByOlUid(map, info.node.key));
    } else {
      setSelectedLayer(undefined);
    }
  };

  const onCreateLayerGroup = () => {
    const parent: any = selectedLayer instanceof LayerGroup ? selectedLayer : olLayerGroup;
    const layers = parent.getLayers();
    let free = 1;
    const groupNameTaken = (i: number) => {
      return layers
        .getArray()
        .some(
          (l: BaseLayer) =>
            l.get('mapContextLayer').attributes.title ===
            (i === 1
              ? intl.formatMessage({ id: 'pages.mapEditor.index.newLayerGroup' })
              : intl.formatMessage(
                  { id: 'pages.mapEditor.index.newLayerGroupWithNumber' },
                  { num: i },
                )),
        );
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
            title:
              free === 1
                ? intl.formatMessage({ id: 'pages.mapEditor.index.newLayerGroup' })
                : intl.formatMessage(
                    { id: 'pages.mapEditor.index.newLayerGroupWithNumber' },
                    { num: free },
                  ),
          },
        },
      },
    });
    layers.push(newLayerGroup);
  };

  const onDeleteLayer = () => {
    if (map && selectedLayer) {
      removeLayerInProgress.current = true;
      MapUtil.getAllLayers(map)
        .filter((layer: BaseLayer) => layer instanceof LayerGroup)
        .forEach((layer: any) => {
          layer.getLayers().remove(selectedLayer);
        });
      setSelectedLayer(undefined);
    }
  };

  const onAddDataset = (dataset: any) => {
    const relatedLayers = dataset.relationships?.selfPointingLayers?.data;
    if (!relatedLayers || relatedLayers.length !== 1) {
      alert(`Dataset ${dataset.id} does not have exactly one layer.`);
      return;
    }
    addingDataset.current = dataset;
    getLayer([
      { name: 'id', value: relatedLayers[0].id, in: 'path' },
      { name: 'include', value: 'service.operationUrls', in: 'query' },
    ]);
  };

  const onOpenLayerSettings = () => {
    setBottomDrawerVisible(true);
    setActiveTab('layerSettings');
    layerTitleInputRef.current?.focus();
  };

  if (!map) {
    return <></>;
  }

  return (
    <>
      <div className="mapeditor-layout">
        {id && (
          <LeftDrawer map={map}>
            {olLayerGroup && (
              <div className="mapeditor-layertree-layout">
                <div className="mapeditor-layertree-header">
                  <span>
                    <FontAwesomeIcon icon={faLayerGroup} />
                    &nbsp;&nbsp;&nbsp;
                    <FormattedMessage id="pages.mapEditor.index.layers" />
                  </span>
                  <Space>
                    <Tooltip
                      title={intl.formatMessage({ id: 'pages.mapEditor.index.createLayerGroup' })}
                    >
                      <Button
                        icon={<FolderAddOutlined />}
                        size="middle"
                        onClick={onCreateLayerGroup}
                      />
                    </Tooltip>
                    <Tooltip
                      title={intl.formatMessage({ id: 'pages.mapEditor.index.deleteLayer' })}
                    >
                      <Button
                        icon={<MinusCircleFilled />}
                        size="middle"
                        onClick={onDeleteLayer}
                        disabled={!selectedLayer}
                      />
                    </Tooltip>
                    <Tooltip
                      title={intl.formatMessage({ id: 'pages.mapEditor.index.layerSettings' })}
                    >
                      <Button
                        icon={<SettingFilled />}
                        size="middle"
                        onClick={onOpenLayerSettings}
                        disabled={!selectedLayer}
                      />
                    </Tooltip>
                  </Space>
                </div>
                <MapEditorLayerTree
                  mapContextId={id}
                  map={map}
                  olLayerGroup={olLayerGroup}
                  onSelect={onSelectLayer}
                  selectedKeys={selectedLayer ? [getUid(selectedLayer)] : []}
                  removeLayerInProgress={removeLayerInProgress}
                  filterFunction={() => true}
                />
              </div>
            )}
          </LeftDrawer>
        )}
        <AutoResizeMapComponent id="map" />
      </div>
      {
        <BottomDrawer
          map={map}
          visible={bottomDrawerVisible}
          onExpand={(expanded) => setBottomDrawerVisible(!expanded)}
        >
          <Tabs
            tabPosition="left"
            activeKey={activeTab}
            onChange={(activeKey) => setActiveTab(activeKey)}
          >
            <TabPane
              tab={
                <span>
                  <InfoCircleOutlined />
                  <FormattedMessage id="pages.mapEditor.index.mapSettings" />
                </span>
              }
              key="mapSettings"
            >
              <MapSettingsForm id={id} />
            </TabPane>
            <TabPane
              tab={
                <span>
                  <SettingOutlined />
                  <FormattedMessage id="pages.mapEditor.index.layerSettings" />
                </span>
              }
              key="layerSettings"
              disabled={!id || !selectedLayer}
            >
              <LayerSettingsForm selectedLayer={selectedLayer} titleInputRef={layerTitleInputRef} />
            </TabPane>
            <TabPane
              tab={
                <span>
                  <SearchOutlined />
                  <FormattedMessage id="pages.mapEditor.index.searchAndAdd" />
                </span>
              }
              key="datasetSearch"
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

export default MapEditor;
