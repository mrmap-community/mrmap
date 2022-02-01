import { SyncOutlined } from '@ant-design/icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { MapContext as ReactGeoMapContext } from '@terrestris/react-geo';
import { Button, notification, Tooltip } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import Collection from 'ol/Collection';
import { transformExtent } from 'ol/proj';
import React, { ReactElement, useEffect, useState } from 'react';
import { useParams } from 'react-router';
import { JsonApiPrimaryData, JsonApiResponse } from '../../Repos/JsonApiRepo';
import LayerRepo from '../../Repos/LayerRepo';
import MapContextLayerRepo from '../../Repos/MapContextLayerRepo';
import MapContextRepo from '../../Repos/MapContextRepo';
import { LayerUtils } from '../../Utils/LayerUtils';
import { TreeUtils } from '../../Utils/TreeUtils';
import { TreeFormFieldDropNodeEventType, TreeNodeType } from '../Shared/FormFields/TreeFormField/TreeFormFieldTypes';
import { CreateLayerOpts } from '../TheMap/LayerManager/LayerManagerTypes';
import { olMap, TheMap } from '../TheMap/TheMap';
import { AttributesForm } from './AttributesForm/AttributesForm';
import './MapContext.css';
import { MapContextLayerForm } from './MapContextLayerForm';
import { MapContextSearchDrawer } from './MapContextSearchDrawer';


const mapContextRepo = new MapContextRepo();
const mapContextLayerRepo = new MapContextLayerRepo();
const layerRepo = new LayerRepo();
const layerUtils = new LayerUtils();
const treeUtils = new TreeUtils();

export const MapContext = (): ReactElement => {
  const [form] = useForm();

  // get the ID parameter from the url
  const { id } = useParams();

  const [createdMapContextId, setCreatedMapContextId] = useState<string>('');
  const [isLoadingMapContextInfo, setIsLoadingMapContextInfo] = useState<boolean>(false);
  const [isSubmittingMapContext, setIsSubmittingMapContext] = useState<boolean>(false);
  const [initLayerTreeData, setInitLayerTreeData] = useState<Collection<any>>(new Collection());
  const [currentSelectedTreeLayerNode, setCurrentSelectedTreeLayerNode] = useState<TreeNodeType>();
  const [isMapContextSearchDrawerVisible, setIsMapContextSearchDrawerVisible] = useState<boolean>(false);

  useEffect(() => {
    // TODO: need to add some sort of loading until the values are fetched
    // olMap.addLayer(mapContextLayersPreviewGroup);
    if (id) {
      setIsLoadingMapContextInfo(true);
      setCreatedMapContextId(id);
      const fetchMapContext = async () => {
        try {
          const response = await mapContextRepo.getMapContextWithLayers(String(id));
          form.setFieldsValue({
            // @ts-ignore
            title: response.mapContext.attributes.title || '',
            // @ts-ignore
            abstract: response.mapContext.attributes.abstract || ''
          });
          // Convert the mapContext layers coming from the server to a compatible tree node list
          const _initLayerTreeData = treeUtils.mapContextLayersToOlLayerGroup(response.mapContextLayers);
          setInitLayerTreeData(_initLayerTreeData);
        } catch (error) {
          // @ts-ignore
          throw new Error(error);
        } finally {
          setIsLoadingMapContextInfo(false);
        }
      };
      fetchMapContext();
    } else {
      setIsMapContextSearchDrawerVisible(true);
    }
  }, [id, form]);
  

  const onAddDatasetToMapAction = async(dataset:any) => {
    dataset.layers.forEach(async (layer: string) => {
      const getParentId = (): string => {
        const currentSelectedIsNodeOnRoot = currentSelectedTreeLayerNode &&
          !currentSelectedTreeLayerNode?.parent &&
          !currentSelectedTreeLayerNode?.isLeaf;
        const currentSelectedIsLeafOnRoot = currentSelectedTreeLayerNode &&
          !currentSelectedTreeLayerNode?.parent &&
          currentSelectedTreeLayerNode?.isLeaf;
        const currentSelectedIsNodeWithParent = currentSelectedTreeLayerNode &&
          currentSelectedTreeLayerNode?.parent &&
          !currentSelectedTreeLayerNode?.isLeaf;
        const currentSelectedIsLeafWithParent = currentSelectedTreeLayerNode && currentSelectedTreeLayerNode?.parent &&
          currentSelectedTreeLayerNode?.isLeaf;

        if(currentSelectedIsNodeOnRoot) {
          return String(currentSelectedTreeLayerNode?.key);
        }
        if(currentSelectedIsLeafOnRoot) {
          return '';
        }
        if(currentSelectedIsNodeWithParent) {
          return String(currentSelectedTreeLayerNode?.key);
        }
        if(currentSelectedIsLeafWithParent) {
          return String(currentSelectedTreeLayerNode?.parent);
        }

        return '';
      };
      // make call
      try {
        // get the layer details with the id and create an OL Layer
        const renderingLayerDetails = await layerRepo.autocompleteInitialValue(layer);
        // this layer needs to be persisted in the DB. Create this layer in the DB
        const createdLayer = await mapContextLayerRepo.create({
          title:renderingLayerDetails.attributes.title,
          description:renderingLayerDetails.attributes.abstract,
          layerScaleMax:renderingLayerDetails.attributes.scaleMax,
          layerScaleMin:renderingLayerDetails.attributes.scaleMin,
          renderingLayer: renderingLayerDetails.attributes.id,
          datasetMetadata: dataset.id,
          parentLayerId: getParentId(),
          mapContextId: createdMapContextId
        });
        //@ts-ignore
        const layerOpts: CreateLayerOpts = {
          url: '',
          version: '1.1.0',
          format: 'image/png',
          layers: '',
          serverType: 'MAPSERVER',
          legendUrl: 'string',
          visible: false,
          //@ts-ignore
          title: createdLayer.data.data.attributes.title,
          //@ts-ignore
          description: createdLayer.data.data.attributes.description,
          //@ts-ignore
          layerId: createdLayer.data.data.id,
          properties: {
            //@ts-ignore
            datasetMetadata: createdLayer.data.data.relationships.dataset_metadata.data?.id,
            //@ts-ignore
            renderingLayer: createdLayer.data.data.relationships.rendering_layer.data?.id,
            //@ts-ignore
            scaleMin: createdLayer.data.data.attributes.layer_scale_min,
            //@ts-ignore
            scaleMax: createdLayer.data.data.attributes.layer_scale_max,
            //@ts-ignore
            style: createdLayer.data.data.relationships.layer_style.data?.id,
            //@ts-ignore
            featureSelectionLayer: createdLayer.data.data.relationships.selection_layer.data?.id,
            //@ts-ignore
            parent: createdLayer?.data?.data?.relationships?.parent?.data?.id,
            //@ts-ignore
            key: createdLayer.data.data.id,
          }
        };
        const renderingLayer = layerUtils.createMrMapOlWMSLayer({
          ...layerOpts,
          url: renderingLayerDetails.attributes.WMSParams.url,
          version: renderingLayerDetails.attributes.WMSParams.version,
          format: 'image/png',
          layers: renderingLayerDetails.attributes.WMSParams.layer,
          serverType: renderingLayerDetails.attributes.WMSParams.serviceType,
          legendUrl: renderingLayerDetails.attributes.WMSParams.legendUrl,
        });

        // TODO: This code is repeated in the layer tree.
        // Make this action more centralized or automatic when users adds it to the tree
        const res = await new LayerRepo().autocompleteInitialValue(renderingLayer.getProperties().renderingLayer);
        if(res.attributes.WMSParams.bbox) {
          olMap.getView().fit(transformExtent(res.attributes.WMSParams.bbox, 'EPSG:4326', 'EPSG:3857'));
        }

        const mapContextLayersGroup = layerUtils.getLayerGroupByGroupTitle(olMap, 'mrMapMapContextLayers');

        if(mapContextLayersGroup) {
          layerUtils.addLayerToGroupByMrMapLayerId(
            mapContextLayersGroup,
            currentSelectedTreeLayerNode?.key as string,
            renderingLayer
          );
        }

        notification.info({
          message: `Add dataset '${dataset.title}'`
        });
      } catch (error) {
        if(!createdMapContextId) {
          // TODO: Why is this not working?
          setIsMapContextSearchDrawerVisible(true);
          notification.warn({
            message: 'No MapContext was created. Please create a valid Map '+
              'Context before adding Map Context Layers'
          });
        } else {
          notification.error({
            message: 'Something went wrong while trying to create the layer'
          });
        }
      }
    });
  };

  // TODO: replace for a decent loading screen
  if(isLoadingMapContextInfo) {
    return (<SyncOutlined spin />);
  }

  return (
    <>
      <div className='map-context'>
        <ReactGeoMapContext.Provider value={olMap}>
          <TheMap
            showLayerManager={!!createdMapContextId}
            selectLayerDispatchAction={(selectedKeys, info) => setCurrentSelectedTreeLayerNode(info.node)}
            addLayerDispatchAction={async (nodeAttributes, newNodeParent) => {
              let renderingLayerInfo = null;
              try {
                // create the layer in the DB
                const createdLayer: JsonApiResponse = await mapContextLayerRepo.create({
                  ...nodeAttributes,
                  parentLayerId: newNodeParent || '',
                  mapContextId: createdMapContextId
                });

                // return createdLayer;
                //@ts-ignore
                const renderingLayerId = createdLayer.data?.data?.relationships.rendering_layer?.data?.id;
                if(renderingLayerId) {
                  renderingLayerInfo = await layerRepo.autocompleteInitialValue(renderingLayerId);
                }

                return {
                  url: renderingLayerInfo?.attributes.WMSParams.url,
                  version: renderingLayerInfo?.attributes.WMSParams.version,
                  format: 'image/png',
                  layers: renderingLayerInfo?.attributes.WMSParams.layer,
                  serverType: renderingLayerInfo?.attributes.WMSParams.serviceType,
                  legendUrl: renderingLayerInfo?.attributes.WMSParams.legendUrl,
                  visible: false,
                  layerId: (createdLayer?.data?.data as JsonApiPrimaryData).id,
                  title: (createdLayer?.data?.data as JsonApiPrimaryData).attributes.title,
                  description: (createdLayer?.data?.data as JsonApiPrimaryData).attributes.description,
                  properties: {
                    ...(createdLayer?.data?.data as JsonApiPrimaryData).attributes,
                    datasetMetadata: (createdLayer?.data?.data as JsonApiPrimaryData)
                      .relationships.dataset_metadata.data?.id,
                    renderingLayer: (createdLayer?.data?.data as JsonApiPrimaryData).relationships
                      .rendering_layer.data?.id,
                    scaleMin: (createdLayer?.data?.data as JsonApiPrimaryData).attributes.layer_scale_min,
                    scaleMax: (createdLayer?.data?.data as JsonApiPrimaryData).attributes.layer_scale_max,
                    style: (createdLayer?.data?.data as JsonApiPrimaryData).relationships.layer_style.data?.id,
                    featureSelectionLayer: (createdLayer?.data?.data as JsonApiPrimaryData)
                      .relationships.selection_layer.data?.id,
                    parent: (createdLayer?.data?.data as JsonApiPrimaryData).relationships?.parent?.data?.id,
                    key: (createdLayer?.data?.data as JsonApiPrimaryData).id
                  }
                };
              } catch (error) {
                //@ts-ignore
                throw new Error(error);
              }
            }}
            removeLayerDispatchAction={async (nodeToRemove) => {
              try {
                // setCurrentSelectedTreeLayerNode(undefined);
                return await mapContextLayerRepo?.delete(String(nodeToRemove.key));
              } catch (error) {
                //@ts-ignore
                throw new Error(error);
              } finally {
                // setCurrentSelectedTreeLayerNode(undefined);
              }
            }}
            editLayerDispatchAction={async (nodeId, nodeAttributesToUpdate) => {
              try {
                return await mapContextLayerRepo?.update(String(nodeId), nodeAttributesToUpdate);
              } catch(error) {
                //@ts-ignore
                throw new Error(error);
              }

            }}
            dropLayerDispatchAction={async (dropEvent:TreeFormFieldDropNodeEventType): Promise<JsonApiResponse> => {
              try {
                const isDroppingToGap = dropEvent.dropToGap;
                const dragKey = dropEvent.dragNode.key;
                const dropKey = dropEvent.node.key;
                let position:string;

                // if tree element is beeing dropped to a gap, it means
                if(isDroppingToGap) {
                  position = 'right';
                } else {
                  position = 'first-child';
                }

                return await mapContextLayerRepo?.move(dragKey, dropKey, position);

              } catch(error) {
                //@ts-ignore
                throw new Error(error);
              }
            }}
            layerGroupName='mrMapMapContextLayers'
            initLayerTreeData={initLayerTreeData}
            layerAttributeForm={(
              <MapContextLayerForm
                key={currentSelectedTreeLayerNode?.key}
                form={form}
              />
            )}
            layerCreateErrorDispatchAction={(error: any) => {
              if(!createdMapContextId) {
                notification.warn({
                  message: 'No MapContext was created. Please create a valid Map '+
                    'Context before adding Map Context Layers'
                });

              } else {
                notification.error({
                  message: 'Something went wrong while trying to create the layer'
                });
              }
            }}
            layerRemoveErrorDispatchAction={(error: any) => {
              notification.error({
                message: 'Something went wrong while trying to remove the layer'
              });
            }}
            layerEditErrorDispatchAction={(error: any) => {
              notification.error({
                message: 'Something went wrong while trying to edit the layer'
              });
            }}
            layerAttributeInfoIcons={(nodeData:TreeNodeType) => {
              if(!nodeData.isLeaf) {
                return (<></>);
              }
              return (
                <>
                  {nodeData.properties.datasetMetadata && (
                    <Tooltip title='Dataset Metadata is set' >
                      <FontAwesomeIcon icon={['fas','eye']} />
                    </Tooltip>
                  )}
                  <Tooltip
                    title={
                      nodeData.properties.renderingLayer ?
                        'Rendering Layer is set' :
                        'Rendering Layer is not set'
                    }
                  >
                    <FontAwesomeIcon
                      icon={['fas',`${nodeData.properties.renderingLayer ? 'eye' : 'eye-slash'}`]}
                    />
                  </Tooltip>
                  <Tooltip
                    title={
                      nodeData.properties.featureSelectionLayer ?
                        'Feature Selection Layer is set' :
                        'Feature Selection Layer is not set'
                    }
                  >
                    <FontAwesomeIcon
                      style={{ color: nodeData.properties.featureSelectionLayer ? '' : 'lightgray' }}
                      icon={[`${nodeData.properties.featureSelectionLayer ? 'fas' : 'far'}`,'check-circle']}
                    />
                  </Tooltip>
                </>
              );
            }}
          />
        </ReactGeoMapContext.Provider>
      </div>
      <MapContextSearchDrawer
        isVisible={isMapContextSearchDrawerVisible}
        defaultOpenTab={!createdMapContextId ? '0' : ''}
        addDatasetToMapAction={onAddDatasetToMapAction}
        mapContextForm={(
          <>
            <AttributesForm
              onSubmit={async (values) => {
                let response;
                if (!id) {
                  setIsSubmittingMapContext(true);
                  try {
                    response = await mapContextRepo.create(values);
                    if (response.data?.data && (response.data.data as JsonApiPrimaryData).id) {
                      setCreatedMapContextId((response.data.data as JsonApiPrimaryData).id);
                    }
                    return response;
                  } catch (error) {
                    setIsSubmittingMapContext(false);
                    // @ts-ignore
                    throw new Error(error);
                  } finally {
                    setIsSubmittingMapContext(false);
                  }
                } else {
                  // TODO add action to edit
                  response = await mapContextRepo.update(id, values);
                  setCreatedMapContextId(id);
                }
              }}
              form={form}
            />
            <Button
              type='primary'
              onClick={() => form.submit()}
              disabled={isSubmittingMapContext}
              loading={isSubmittingMapContext}
            >
              {!createdMapContextId ? 'Submit' : 'Change' }
            </Button>
          </>
        )}
      />
    </>
  );
};
