import { MapContext as ReactGeoMapContext } from '@terrestris/react-geo';
import { notification } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import Collection from 'ol/Collection';
import { transformExtent } from 'ol/proj';
import React, { ReactElement, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { JsonApiPrimaryData, JsonApiResponse } from '../../Repos/JsonApiRepo';
import LayerRepo from '../../Repos/LayerRepo';
import MapContextLayerRepo from '../../Repos/MapContextLayerRepo';
import MapContextRepo from '../../Repos/MapContextRepo';
import { LayerUtils } from '../../Utils/LayerUtils';
import { TreeUtils } from '../../Utils/TreeUtils';
import { CreateLayerOpts } from '../LayerManager/LayerManagerTypes';
import { SearchDrawer } from '../SearchDrawer/SearchDrawer';
import { TreeNodeType } from '../Shared/FormFields/TreeFormField/TreeFormFieldTypes';
import { olMap, TheMap } from '../TheMap/TheMap';
import './MapContext.css';
import { MapContextLayerForm } from './MapContextLayerForm';


const mapContextRepo = new MapContextRepo();
const mapContextLayerRepo = new MapContextLayerRepo();
const layerRepo = new LayerRepo();
const layerUtils = new LayerUtils();
const treeUtils = new TreeUtils();

export const MapContext = (): ReactElement => {
  const navigate = useNavigate();
  const [form] = useForm();

  // get the ID parameter from the url
  const { id } = useParams();

  // const [current, setCurrent] = useState(0);
  const [createdMapContextId, setCreatedMapContextId] = useState<string>('');
  const [isSubmittingMapContext, setIsSubmittingMapContext] = useState<boolean>(false);
  const [isRemovingMapContext, setIsRemovingMapContext] = useState<boolean>(false);
  const [initLayerTreeData, setInitLayerTreeData] = useState<Collection<any>>(new Collection());
  const [currentSelectedTreeLayerNode, setCurrentSelectedTreeLayerNode] = useState<TreeNodeType>();

  useEffect(() => {
    // TODO: need to add some sort of loading until the values are fetched
    // olMap.addLayer(mapContextLayersPreviewGroup);
    if (id) {
      const fetchMapContext = async () => {
        try {
          const response = await mapContextRepo.getMapContextWithLayers(String(id));
          form.setFieldsValue({
            // @ts-ignore
            title: response.mapContext.attributes.title || '',
            // @ts-ignore
            abstract: response.mapContext.attributes.abstract || ''
          });
          //  Convert the mapContext layers coming from the server to a compatible tree node list
          const _initLayerTreeData = treeUtils.MPTTListToOLLayerGroup(response.mapContextLayers);
          setInitLayerTreeData(_initLayerTreeData);
        } catch (error) {
          // @ts-ignore
          throw new Error(error);
        }
      };
      fetchMapContext();
    }
  }, [id, form]);
  
  // const nextStep = () => {
  //   setCurrent(current + 1);
  // };

  // const prevStep = () => {
  //   setCurrent(current - 1);
  // };

  // const onSelectLayerInTree = (selectedKeys: any, info: any) => {
  //   setCurrentSelectedTreeLayerNode(info.node);
  // };

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
          // isLeaf: true,
          renderingLayer: renderingLayerDetails.attributes.id,
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
        //@ts-ignore
        throw new Error(error);
      }
  });
};

return(

        <div className='map-context'>
            {/* <MapContextForm
              onSubmit={async (values) => {
                if (!id) {
                  setIsSubmittingMapContext(true);
                  try {
                    const response = await mapContextRepo.create(values);
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
                    // nextStep();
                  }
                } else {
                  // TODO add action to edit
                  setCreatedMapContextId(id);
                  // nextStep();
                }
              }}
              form={form}
            /> */}
          <ReactGeoMapContext.Provider value={olMap}>
            <TheMap 
              createdMapContextId={createdMapContextId}
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
              editLayerDispatchAction={async (nodeId, nodeAttributesToUpdate) => (
                await mapContextLayerRepo?.update(String(nodeId), nodeAttributesToUpdate)
              )}
              dragLayerDispatchAction={async (nodeBeingDraggedInfo) => {
                const dropKey = nodeBeingDraggedInfo.node.key;
                const dragKey = nodeBeingDraggedInfo.dragNode.key;
                let position:string;
                if (nodeBeingDraggedInfo.node.parent === nodeBeingDraggedInfo.dragNode.parent) {
                  position = 'right';
                } else {
                  position = 'first-child';
                }
                return await mapContextLayerRepo?.move(dragKey, dropKey, position);
              }}
              layerGroupName='mrMapMapContextLayers'
              initLayerTreeData={initLayerTreeData}
              layerAttributeForm={(<MapContextLayerForm form={form}/>)}
            />
          </ReactGeoMapContext.Provider>
          
          <SearchDrawer addDatasetToMapAction={onAddDatasetToMapAction}/>

          
        </div>
);
};
