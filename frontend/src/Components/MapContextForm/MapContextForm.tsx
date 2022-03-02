import { SyncOutlined } from '@ant-design/icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { notification, Tooltip } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import Collection from 'ol/Collection';
import { transformExtent } from 'ol/proj';
import React, { ReactElement, useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useNavigate, useParams } from 'react-router';
import { JsonApiPrimaryData, JsonApiResponse, ResourceIdentifierObject } from '../../Repos/JsonApiRepo';
import LayerRepo from '../../Repos/LayerRepo';
import MapContextLayerRepo from '../../Repos/MapContextLayerRepo';
import { LayerUtils } from '../../Utils/LayerUtils';
import { olMap } from '../../Utils/MapUtils';
import { TreeUtils } from '../../Utils/TreeUtils';
import RepoForm from '../Shared/RepoForm/RepoForm';
import { DropNodeEventType, TreeNodeType } from '../Shared/TreeManager/TreeManagerTypes';
import { CreateLayerOpts } from '../TheMap/LayerManager/LayerManagerTypes';
import { TheMap } from '../TheMap/TheMap';
import './MapContextForm.css';
import { TabsDrawer } from './TabsDrawer/TabsDrawer';


const mapContextLayerRepo = new MapContextLayerRepo();
const layerRepo = new LayerRepo();
const layerUtils = new LayerUtils();
const treeUtils = new TreeUtils();

export const MapContextForm = (): ReactElement => {
  const navigate = useNavigate();
  const [form] = useForm();
  const { id } = useParams();
  const [initLayerTreeData, setInitLayerTreeData] = useState<Collection<any>>(new Collection());
  const [currentSelectedTreeLayerNode, setCurrentSelectedTreeLayerNode] = useState<TreeNodeType>();
  const [isMapContextSearchDrawerVisible, setIsMapContextSearchDrawerVisible] = useState<boolean>(false);

  const [
    getMapContext,
    {
      loading: getMapContextLoading,
      response: getMapContextResponse
    }] = useOperationMethod('getMapContext');

  const [deleteMapContextLayer, ] = useOperationMethod('deleteMapContextLayer');


  useEffect(() => {
    if (getMapContextResponse){
      form.setFieldsValue({
        // @ts-ignore
        title: getMapContextResponse.data.data.attributes.title || '',
        // @ts-ignore
        abstract: getMapContextResponse.data.data.attributes.abstract || ''
      });
      // Convert the mapContext layers coming from the server to a compatible tree node list
      const _initLayerTreeData = treeUtils.mapContextLayersToOlLayerGroup(getMapContextResponse);
      setInitLayerTreeData(_initLayerTreeData);
    }
  }, [form, getMapContextResponse]);

  useEffect(() => {
    if (id) {
      getMapContext([
        { name: 'id', value: String(id), in: 'path' },
        { name: 'include', value: 'mapContextLayers.renderingLayer.service.operationUrls', in: 'query' }
      ]);
    } else {
      setIsMapContextSearchDrawerVisible(true);
    }
  }, [getMapContext, id]);


  const onAddDatasetToMapAction = async(dataset:any) => {
    if (id){
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
          const currentSelectedIsLeafWithParent = currentSelectedTreeLayerNode &&
            currentSelectedTreeLayerNode?.parent &&
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
            mapContextId: id
          });
          //@ts-ignore
          const layerOpts: CreateLayerOpts = {
            url: '',
            version: '1.1.1',
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
              datasetMetadata: createdLayer.data.data.relationships.datasetMetadata.data?.id,
              //@ts-ignore
              renderingLayer: createdLayer.data.data.relationships.renderingLayer.data?.id,
              //@ts-ignore
              scaleMin: createdLayer.data.data.attributes.layerScaleMin,
              //@ts-ignore
              scaleMax: createdLayer.data.data.attributes.layerScaleMax,
              //@ts-ignore
              style: createdLayer.data.data.relationships.layerStyle.data?.id,
              //@ts-ignore
              featureSelectionLayer: createdLayer.data.data.relationships.selectionLayer.data?.id,
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
          if(!id) {
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
    }

  };

  // TODO: replace for a decent loading screen
  if(getMapContextLoading) {
    return (<SyncOutlined spin />);
  }

  return (
    <>
      <div className='map-context-layout'>
        <TheMap
          showLayerManager={!!id}
          selectLayerDispatchAction={(selectedKeys, info) => setCurrentSelectedTreeLayerNode(info.node)}
          addLayerDispatchAction={async (nodeAttributes, newNodeParent) => {
            let renderingLayerInfo = null;
            try {
              // create the layer in the DB
              const createdLayer: JsonApiResponse = await mapContextLayerRepo.create({
                ...nodeAttributes,
                parentLayerId: newNodeParent || '',
                mapContextId: id
              });
              const responsePrimary = createdLayer?.data?.data as JsonApiPrimaryData;
              // eslint-disable-next-line max-len
              const datasetMetadata = responsePrimary?.relationships['datasetMetadata']?.data as ResourceIdentifierObject;
              const renderingLayer = responsePrimary?.relationships['renderingLayer']?.data as ResourceIdentifierObject;
              const selectionLayer = responsePrimary?.relationships['selectionLayer']?.data as ResourceIdentifierObject;
              const layerStyle = responsePrimary?.relationships['layerStyle']?.data as ResourceIdentifierObject;
              const parent = responsePrimary?.relationships['parent']?.data as ResourceIdentifierObject;


              // return createdLayer;
              //@ts-ignore
              const renderingLayerId = createdLayer.data?.data?.relationships.renderingLayer?.data?.id;
              if(renderingLayerId) {
                renderingLayerInfo = await layerRepo.autocompleteInitialValue(renderingLayerId);
              }

              return {
                url: (renderingLayerInfo as any).attributes.WMSParams.url,
                version: (renderingLayerInfo as any).attributes.WMSParams.version,
                format: 'image/png',
                layers: (renderingLayerInfo as any).attributes.WMSParams.layer,
                serverType: (renderingLayerInfo as any).attributes.WMSParams.serviceType,
                legendUrl: (renderingLayerInfo as any).attributes.WMSParams.legendUrl,
                visible: false,
                layerId: (createdLayer?.data?.data as JsonApiPrimaryData).id,
                title: (createdLayer?.data?.data as JsonApiPrimaryData).attributes.title,
                description: (createdLayer?.data?.data as JsonApiPrimaryData).attributes.description,
                properties: {
                  ...(createdLayer?.data?.data as JsonApiPrimaryData).attributes,
                  datasetMetadata: datasetMetadata.id,
                  renderingLayer: renderingLayer.id,
                  scaleMin: (createdLayer?.data?.data as JsonApiPrimaryData).attributes.layerScaleMin,
                  scaleMax: (createdLayer?.data?.data as JsonApiPrimaryData).attributes.layerScaleMax,
                  style: layerStyle.id,
                  featureSelectionLayer: selectionLayer.id,
                  parent: parent.id,
                  key: (createdLayer?.data?.data as JsonApiPrimaryData).id
                }
              };
            } catch (error) {
              //@ts-ignore
              throw new Error(error);
            }
          }}
          removeLayerDispatchAction={(nodeToRemove) => {
            return deleteMapContextLayer([{ name: 'id', value: nodeToRemove.key, in: 'path' }]);
          }}
          editLayerDispatchAction={async (nodeId, nodeAttributesToUpdate) => {
            try {
              return await mapContextLayerRepo?.update(String(nodeId), nodeAttributesToUpdate);
            } catch(error) {
              //@ts-ignore
              throw new Error(error);
            }

          }}
          dropLayerDispatchAction={async (dropEvent:DropNodeEventType): Promise<JsonApiResponse> => {
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
            <RepoForm
              resourceType={'MapContextLayer'}
              resourceId={currentSelectedTreeLayerNode?.key}
              form={form}
              // TODO: onSuccess={}
            />
          )}
          layerCreateErrorDispatchAction={(error: any) => {
            if(!id) {
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
      </div>
      <TabsDrawer
        isVisible={isMapContextSearchDrawerVisible}
        defaultOpenTab={!id ? '0' : ''}
        addDatasetToMapAction={onAddDatasetToMapAction}
        mapContextForm={(
          <>
            <RepoForm
              resourceType='MapContext'
              resourceId={id}
              form={form}
              onSuccess={(response, created) => {
                const mapContextId = (response.data.data as JsonApiPrimaryData).id;
                navigate(`/registry/mapcontexts/${mapContextId}/edit`);
              }}
            />
          </>
        )}
      />
    </>
  );
};
