import { MapContext as ReactGeoMapContext } from '@terrestris/react-geo';
import { Button, notification, Steps } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import Collection from 'ol/Collection';
import LayerGroup, { default as OlLayerGroup } from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import Layer from 'ol/layer/Layer';
import { transformExtent } from 'ol/proj';
import ImageWMS from 'ol/source/ImageWMS';
import React, { ReactElement, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { JsonApiPrimaryData } from '../../Repos/JsonApiRepo';
import LayerRepo from '../../Repos/LayerRepo';
import MapContextLayerRepo from '../../Repos/MapContextLayerRepo';
import MapContextRepo from '../../Repos/MapContextRepo';
import { LayerUtils } from '../../Utils/LayerUtils';
import { TreeUtils } from '../../Utils/TreeUtils';
import { LayerTree } from '../LayerTree/LayerTree';
import { CreateLayerOpts } from '../LayerTree/LayerTreeTypes';
import { SearchDrawer } from '../SearchDrawer/SearchDrawer';
import { TreeNodeType } from '../Shared/FormFields/TreeFormField/TreeFormFieldTypes';
import { olMap, TheMap } from '../TheMap/TheMap';
import './MapContext.css';
import { MapContextForm } from './MapContextForm';
import { MapContextLayerForm } from './MapContextLayerForm';


const mapContextRepo = new MapContextRepo();
const mapContextLayerRepo = new MapContextLayerRepo();
const layerRepo = new LayerRepo();
const layerUtils = new LayerUtils();
const treeUtils = new TreeUtils();

const mapContextLayersGroup = new OlLayerGroup({
  opacity: 1,
  visible: true,
  properties: {
    title: 'mrMapMapContextLayers'
  },
  layers: []
});

export const MapContext = (): ReactElement => {
  const navigate = useNavigate();
  const [form] = useForm();

  // get the ID parameter from the url
  const { id } = useParams();

  const [current, setCurrent] = useState(0);
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

  useEffect(() => {
    mapContextLayersGroup.setLayers(initLayerTreeData);
  }, [initLayerTreeData]);

  
  const nextStep = () => {
    setCurrent(current + 1);
  };

  const prevStep = () => {
    setCurrent(current - 1);
  };

  const onSelectLayerInTree = (selectedKeys: any, info: any) => {
    setCurrentSelectedTreeLayerNode(info.node);
  };

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
        
        layerUtils.addLayerToGroupByMrMapLayerId(
          mapContextLayersGroup, 
          currentSelectedTreeLayerNode?.key as string, 
          renderingLayer
        );
        notification.info({
          message: `Add dataset '${dataset.title}'`
        });
      } catch (error) {
        //@ts-ignore
        throw new Error(error);
      }
  });
};

  const steps = [
    {
      title: 'Map Context',
      content: (
        <>
          <div className='mapcontextform-map-area'>
            <MapContextForm
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
                    nextStep();
                  }
                } else {
                  // TODO add action to edit
                  setCreatedMapContextId(id);
                  nextStep();
                }
              }}
              form={form}
            />
          </div>
          <div className='steps-action'>
            <Button
              type='primary'
              onClick={() => form.submit()}
              disabled={isSubmittingMapContext}
              loading={isSubmittingMapContext}
            >
              Next Step
            </Button>
          </div>

          </>
      )
    },
    {
      title: 'Map Context Layers',
      content: (
        <>
        <ReactGeoMapContext.Provider value={olMap}></ReactGeoMapContext.Provider>
          <div className='Map'>
            <ReactGeoMapContext.Provider value={olMap}>
              <TheMap />
            <div className='layer-section'>
              <LayerTree
                // map={olMap}
                layerGroup={mapContextLayersGroup}
                asyncTree
                selectLayerDispatchAction={onSelectLayerInTree}
                addLayerDispatchAction={async (nodeAttributes, newNodeParent) => {
                  let layerToAdd: OlLayerGroup | ImageLayer<ImageWMS> = new Layer({});
                  try {
                    // create the layer in the DB
                    const createdLayer = await mapContextLayerRepo.create({
                      ...nodeAttributes,
                      parentLayerId: newNodeParent || '',
                      mapContextId: createdMapContextId
                    });
                    // NEXT CODE SHOULD BE HANDLED AUTOMATICALLY BY THE LAYER TREE
                    // @ts-ignore
                    if(createdLayer.data?.data?.relationships?.rendering_layer?.data?.id) {
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
                          ...createdLayer.data.data.attributes,
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
                          key: createdLayer.data.data.id
                        }
                      };
                      //@ts-ignore
                      const renderingLayerId = createdLayer.data?.data?.relationships.rendering_layer?.data?.id;
                      if(renderingLayerId) {
                        const rl = await layerRepo.autocompleteInitialValue(renderingLayerId);
                        layerToAdd = layerUtils.createMrMapOlWMSLayer({
                          ...layerOpts,
                          url: rl.attributes.WMSParams.url,
                          version: rl.attributes.WMSParams.version,
                          format: 'image/png',
                          layers: rl.attributes.WMSParams.layer,
                          serverType: rl.attributes.WMSParams.serviceType,
                          legendUrl: rl.attributes.WMSParams.legendUrl,
                        });
                      } else {
                        // add a layer without the definitions coming from rl
                        layerToAdd = layerUtils.createMrMapOlWMSLayer(layerOpts);
                      }
                    } else {
                      layerToAdd = new OlLayerGroup({
                        opacity: 1,
                        visible: false,
                        properties: {
                          //@ts-ignore
                          title: createdLayer.data.data.attributes.title,
                          //@ts-ignore
                          description: createdLayer?.data?.data?.attributes.description,
                          //@ts-ignore
                          layerId: createdLayer?.data?.data?.id,
                          //@ts-ignore
                          parent: createdLayer?.data?.data?.relationships?.parent?.data?.id
                        },
                        layers: []
                      }); 
                    }
                    // add the layer to the parent, where the layer or group is being created
                    layerUtils.addLayerToGroupByMrMapLayerId(
                      mapContextLayersGroup, 
                      newNodeParent as string, 
                      layerToAdd
                    );
                    
                    return createdLayer;
                  } catch (error) {
                    //@ts-ignore
                    throw new Error(error);
                  }
                }}
                removeLayerDispatchAction={async (nodeToRemove) => {
                  let layersToKeep;
                  try {
                    // get the parent of the layer to remove
                    const layerToRemoveParent = layerUtils.getAllMapLayers(mapContextLayersGroup)
                      .find((l: any) => l.getProperties().layerId === nodeToRemove.parent);
                    if(layerToRemoveParent && layerToRemoveParent instanceof LayerGroup) {
                      layersToKeep = layerToRemoveParent
                        .getLayers()
                        .getArray()
                        .filter((l:any) => l.getProperties().layerId !== nodeToRemove.key);
                      layerToRemoveParent.setLayers(new Collection(layersToKeep));
                    } else {
                      // if there is no parent, its root.Remove itself from the layer group
                      layersToKeep = mapContextLayersGroup
                        .getLayers()
                        .getArray()
                        .filter((l:any) => l.getProperties().layerId !== nodeToRemove.key);
                      mapContextLayersGroup.setLayers(new Collection(layersToKeep));
                    }
                    setCurrentSelectedTreeLayerNode(undefined);
                    return await mapContextLayerRepo?.delete(String(nodeToRemove.key));
                  } catch (error) {
                    //@ts-ignore
                    throw new Error(error);
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
                layerAttributeForm={(<MapContextLayerForm form={form}/>)}
              />
            </div>
            </ReactGeoMapContext.Provider>
          </div>

          <SearchDrawer addDatasetToMapAction={onAddDatasetToMapAction}/>

          <div className='steps-action'>
            <Button
              type='primary'
              onClick={async () => {
                if (!id) {
                  setIsRemovingMapContext(true);
                  try {
                    return await mapContextRepo.delete(createdMapContextId);
                  } catch (error) {
                    setIsRemovingMapContext(false);
                    // @ts-ignore
                    throw new Error(error);
                  } finally {
                    setIsRemovingMapContext(false);
                    prevStep();
                  }
                } else {
                  prevStep();
                }
              }}
              disabled={isRemovingMapContext}
              loading={isRemovingMapContext}
            >
              Previous
            </Button>
            <Button
              type='primary'
              htmlType='submit'
              onClick={() => {
                navigate('/registry/mapcontexts/');
              }}
            >
              Finish
            </Button>
          </div>
        </>
      )
    }
  ];

  return (
    <>
      <Steps current={current}>
      {steps.map(item => (
          <Steps.Step key={item.title} title={item.title} />
      ))}
      </Steps>
      <div className='steps-content'>{steps[current].content}</div>
    </>
  );
};
