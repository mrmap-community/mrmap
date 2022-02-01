import { ExpandOutlined } from '@ant-design/icons/lib/icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useMap } from '@terrestris/react-geo';
import { Button, Menu, Tooltip } from 'antd';
import { Key } from 'antd/lib/table/interface';
import Collection from 'ol/Collection';
import BaseEvent from 'ol/events/Event';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import Layer from 'ol/layer/Layer';
import { transformExtent } from 'ol/proj';
import ImageWMS from 'ol/source/ImageWMS';
import { getUid } from 'ol/util';
import React, { useEffect, useState } from 'react';
import { JsonApiResponse } from '../../../Repos/JsonApiRepo';
import LayerRepo from '../../../Repos/LayerRepo';
import { LayerManagerUtils } from '../../../Utils/LayerManagerUtils';
import { LayerUtils } from '../../../Utils/LayerUtils';
import { TreeUtils } from '../../../Utils/TreeUtils';
import { TreeFormField } from '../../Shared/FormFields/TreeFormField/TreeFormField';
import { TreeFormFieldDropNodeEventType, TreeNodeType } from '../../Shared/FormFields/TreeFormField/TreeFormFieldTypes';
import './LayerManager.css';
import { CreateLayerOpts, LayerManagerProps } from './LayerManagerTypes';


const treeUtils =  new TreeUtils();
const layerUtils =  new LayerUtils();
const layerManagerUtils = new LayerManagerUtils();

const layerManagerLayerGroup = new LayerGroup({
  opacity: 1,
  visible: true,
  layers: []
});

export const LayerManager = ({
  layerManagerLayerGroupName = 'mrMapLayerTreeLayerGroup',
  asyncTree = false,
  addLayerDispatchAction = () => undefined,
  removeLayerDispatchAction = () => undefined,
  editLayerDispatchAction = () => undefined,
  dropLayerDispatchAction = () => undefined,
  selectLayerDispatchAction = () => undefined,
  customLayerManagerTitleAction = () => undefined,
  layerCreateErrorDispatchAction = () => undefined,
  layerRemoveErrorDispatchAction = () => undefined,
  layerEditErrorDispatchAction = () => undefined,
  layerAttributeInfoIcons = () => (<></>),
  layerAttributeForm,
  initLayerTreeData,
  multipleSelection = false
}: LayerManagerProps): JSX.Element => {
  // TODO: all logic to handle layers or interaction between map and layers should be handled here,
  // not to the tree form field component.
  // The tree form field component handles generic logic for a tree, not for the layers or interaction with map.
  // Only change it if you detect aa bug thaat could be traced baack deep to the tree form field
  const map = useMap();
  const [treeData, setTreeData] = useState<TreeNodeType[]>([]);
  const [isTreeContainerVisible, setIsTreeContainerVisible] = useState<boolean>(true); 
  // const [currentSelectedTreeLayerNode, setCurrentSelectedTreeLayerNode] = useState<TreeNodeType>(); // TODO

  useEffect(() => {
    map.updateSize();  
  },[isTreeContainerVisible, map]);

  useEffect(() => {
    const onLayerGroupReceivedNewLayer = (e: BaseEvent) => {       
      setTreeData(treeUtils.OlLayerGroupToTreeNodeList(layerManagerLayerGroup));
    };
    const setWMSParams = async(theLayer: ImageLayer<ImageWMS>) => {
      try {
        const source = theLayer.getSource();
        const res = await new LayerRepo().autocompleteInitialValue(theLayer.getProperties().renderingLayer);
        source.setUrl(res.attributes.WMSParams.url);
        source.getParams().LAYERS = res.attributes.WMSParams.layer;
        source.getParams().VERSION = res.attributes.WMSParams.version;
        source.set('serverType',res.attributes.WMSParams.serviceType);
      } catch (error) {
        //@ts-ignore
        throw new Error(error);
      }
    };
    
    layerManagerLayerGroup.set('title', layerManagerLayerGroupName);
    layerManagerLayerGroup.setLayers(initLayerTreeData);

    map.addLayer(layerManagerLayerGroup);
    setTreeData(treeUtils.OlLayerGroupToTreeNodeList(layerManagerLayerGroup));
    
    const allMapLayers = layerUtils.getAllMapLayers(layerManagerLayerGroup);
    
    allMapLayers.forEach((mapLayer: any) => {
      if(mapLayer instanceof ImageLayer) {
        const src: ImageWMS = mapLayer.getSource();
        // loaded layers from the DB will not have any information regarding the WMS parameters
        // get them here
        // TODO: Maybe they can be included in the initial response
        if(!src.getUrl() && mapLayer.getProperties().renderingLayer){
          setWMSParams(mapLayer);
        }
      }
    });
    

    layerManagerLayerGroup.on('change', onLayerGroupReceivedNewLayer);
    
    return () => {
      layerManagerLayerGroup.un('change', onLayerGroupReceivedNewLayer);
      map.removeLayer(layerManagerLayerGroup);
    };

  }, [layerManagerLayerGroupName, map, initLayerTreeData]);

  const onCheckLayer = (checkedKeys: (Key[] | {checked: Key[]; halfChecked: Key[];}), info: any) => {
    const { checked } = info;
    const eventKey = info.node.key;
    const layer = layerUtils.getLayerByMrMapLayerId(map, eventKey);
    setLayerVisibility(layer, checked);
  };

  const setLayerVisibility = (
    layer: BaseLayer | LayerGroup | ImageLayer<ImageWMS> | undefined, 
    visibility: boolean
  ) => {
    // if (!(layer instanceof BaseLayer) || !(layer instanceof LayerGroup)) {
    //   console.error('setLayerVisibility called without layer or layer group.');
    //   return;
    // }
    if(layer) {
      if (layer instanceof LayerGroup) {
        layer.setVisible(visibility);
        layer.getLayers().forEach((subLayer) => {
          setLayerVisibility(subLayer, visibility);
        });
      } else {
        layer.setVisible(visibility);
        // if layer has a parent folder, make it visible too
        if (visibility) {
          const group = layerManagerLayerGroup ? layerManagerLayerGroup : map.getLayerGroup();
          setParentFoldersVisible(group, getUid(layer), group);
        }
      }
    }
  };

  const setParentFoldersVisible = (currentGroup: LayerGroup, olUid: string, masterGroup: LayerGroup) => {
    const items = currentGroup.getLayers().getArray();
    const groups = items.filter(l => l instanceof LayerGroup) as LayerGroup[];
    const match = items.find(i => getUid(i) === olUid);
    if (match) {
      currentGroup.setVisible(true);
      setParentFoldersVisible(masterGroup, getUid(currentGroup), masterGroup);
      return;
    }
    groups.forEach(g => {
      setParentFoldersVisible(g, olUid, masterGroup);
    });
  };

  const onFitToLayerExtent = async(layerId: string) => {
    try {
      const res = await new LayerRepo().autocompleteInitialValue(layerId);
      if(res.attributes.WMSParams.bbox) {
        map.getView().fit(transformExtent(res.attributes.WMSParams.bbox, 'EPSG:4326', 'EPSG:3857'));
      }
    } catch(error) {
      //@ts-ignore
      throw new Error(error);
    }
  };

  const layerActions = (nodeData: TreeNodeType|undefined): any => {
    return (
      <>
        <Menu.Item
          onClick={async() => {
          // fit to layer extent
            const theLayer = layerUtils.getAllMapLayers(layerManagerLayerGroup)
              .find(l => { 
                return l.getProperties().key === nodeData?.key;
              });
            if(theLayer && theLayer.get('renderingLayer')) {
              onFitToLayerExtent(theLayer.get('renderingLayer'));
            } else {
              console.warn('Layer not found');
            }
          }}
          icon={<ExpandOutlined/>}
          key='zoom-to-extent'
        >
        Zoom to layer Extent
        </Menu.Item>
      </>
    );
  }; 

  const onCreateLayer = async(nodeAttributes:any, newNodeParent:any) => {
    // NOTE it is assumed that the object returned by the addDispatchLayerAction, is of type CreateLayerOpts
    let layerToAdd: LayerGroup | ImageLayer<ImageWMS> = new Layer({});
    // if method is asnyc, we need to get the result by resolving the promise
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    if(addLayerDispatchAction instanceof Object.getPrototypeOf(async function(){}).constructor){
      try {
        const response: CreateLayerOpts | void = await addLayerDispatchAction(nodeAttributes, newNodeParent);
        
        if(response?.properties.rendering_layer) {
          layerToAdd = layerUtils.createMrMapOlWMSLayer(response);
        } else {
          layerToAdd = new LayerGroup({
            opacity: 1,
            visible: false,
            properties: {
              title: response?.title,
              description: response?.description,
              layerId: response?.layerId,
              parent: response?.properties.parent
            },
            layers: []
          });
        }
        // add the layer to the parent, where the layer or group is being created
        layerUtils.addLayerToGroupByMrMapLayerId(
          layerManagerLayerGroup, 
          newNodeParent as string, 
          layerToAdd
        );
        return response;
      } catch(error: any) {
        return layerCreateErrorDispatchAction(error);
      }
    // Non Async version
    } else {
      const layerOpts = addLayerDispatchAction(nodeAttributes, newNodeParent);
      if(layerOpts) {
        //@ts-ignore
        layerToAdd = layerUtils.createMrMapOlWMSLayer(layerOpts);
      } 
    } 
    // add the layer to the parent, where the layer or group is being created
    layerUtils.addLayerToGroupByMrMapLayerId(
      layerManagerLayerGroup, 
      newNodeParent as string, 
      layerToAdd
    );
  };

  const onDeleteLayer = async(nodeToRemove: TreeNodeType) => {
    let layersToKeep;
    // if method is asnyc, we need to get the result by resolving the promise
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    if(removeLayerDispatchAction instanceof Object.getPrototypeOf(async function(){}).constructor) {
      try {
        return await removeLayerDispatchAction(nodeToRemove);
      } catch (error: any) {
        layerRemoveErrorDispatchAction(error);
      } finally {
        const layerToRemoveParent = layerUtils.getAllMapLayers(layerManagerLayerGroup)
          .find((l: any) => l.getProperties().layerId === nodeToRemove.parent);
        if(layerToRemoveParent && layerToRemoveParent instanceof LayerGroup) {
          layersToKeep = layerToRemoveParent
            .getLayers()
            .getArray()
            .filter((l:any) => l.getProperties().layerId !== nodeToRemove.key);
          layerToRemoveParent.setLayers(new Collection(layersToKeep));
        } else {
          // if there is no parent, its root.Remove itself from the layer group
          layersToKeep = layerManagerLayerGroup
            .getLayers()
            .getArray()
            .filter((l:any) => l.getProperties().layerId !== nodeToRemove.key);
          layerManagerLayerGroup.setLayers(new Collection(layersToKeep));
        }
      } 
    // Non Async version
    } else {
      removeLayerDispatchAction(nodeToRemove);
      const layerToRemoveParent = layerUtils.getAllMapLayers(layerManagerLayerGroup)
        .find((l: any) => l.getProperties().layerId === nodeToRemove.parent);
      if(layerToRemoveParent && layerToRemoveParent instanceof LayerGroup) {
        layersToKeep = layerToRemoveParent
          .getLayers()
          .getArray()
          .filter((l:any) => l.getProperties().layerId !== nodeToRemove.key);
        layerToRemoveParent.setLayers(new Collection(layersToKeep));
      } else {
        // if there is no parent, its root.Remove itself from the layer group
        layersToKeep = layerManagerLayerGroup
          .getLayers()
          .getArray()
          .filter((l:any) => l.getProperties().layerId !== nodeToRemove.key);
        layerManagerLayerGroup.setLayers(new Collection(layersToKeep));
      }
    }
    // setCurrentSelectedTreeLayerNode(undefined);
  };

  const onEditLayer = async(nodeId:number|string, nodeAttributesToUpdate: any) => {
    // if method is asnyc, we need to get the result by resolving the promise
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    if(editLayerDispatchAction instanceof Object.getPrototypeOf(async function(){}).constructor) {
      try {
        const editedLayer = await editLayerDispatchAction(nodeId, nodeAttributesToUpdate);
        // update the layer properties
        const layerToUpdate = layerUtils.getAllMapLayers(layerManagerLayerGroup)
          .find((l: any) => l.getProperties().layerId === nodeId);
        if(layerToUpdate) {
          layerToUpdate.setProperties({ 
            ...layerToUpdate.getProperties(), 
            ...nodeAttributesToUpdate 
          });
        }
        return editedLayer;
      } catch(error: any) {
        layerEditErrorDispatchAction(error);
      }
    // Non Async version
    } else {
      editLayerDispatchAction(nodeId, nodeAttributesToUpdate);
    }
  };

  const asyncDropLayer = async(dropEvent:TreeFormFieldDropNodeEventType) : Promise<JsonApiResponse> => {
    try {
      layerManagerUtils.updateLayerGroupOnDrop(dropEvent, layerManagerLayerGroup);
      return await dropLayerDispatchAction(dropEvent) as JsonApiResponse;
    } catch (error) {
      // @ts-ignore
      throw new Error(error);
    }
  };

  const onDropLayer = (dropEvent:TreeFormFieldDropNodeEventType): Promise<JsonApiResponse> | void => {
    // if method is asnyc, we need to get the result by resolving the promise
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    if(dropLayerDispatchAction instanceof Object.getPrototypeOf(async function(){}).constructor) {
      layerManagerUtils.updateLayerGroupOnDrop(dropEvent, layerManagerLayerGroup);
      return asyncDropLayer(dropEvent);
      // Non Async version
    } else {
      dropLayerDispatchAction(dropEvent);
      layerManagerUtils.updateLayerGroupOnDrop(dropEvent, layerManagerLayerGroup);
    }
  };

  const onSelectLayer = (selectedKeys: React.Key[], info: any) => {
    selectLayerDispatchAction(selectedKeys, info);
  };

  return (
    <div className='layer-manager'>
      <Tooltip
        title={isTreeContainerVisible ? 'Hide layer manager' : 'Show layer manager'}
        placement='right'
      >
        <Button
          className='layer-manager-toggle'
          type='primary'
          style={{
            left: isTreeContainerVisible ? '500px' : 0
          }}
          icon={(
            <FontAwesomeIcon 
              icon={['fas', isTreeContainerVisible ? 'angle-double-left' : 'angle-double-right']} 
            />
          )} 
          onClick={() => setIsTreeContainerVisible(!isTreeContainerVisible)}
        />
      </Tooltip>
      {isTreeContainerVisible && (
        <TreeFormField
          draggable
          contextMenuOnNode
          checkableNodes
          attributeContainer='drawer'
          className='layer-manager-tree'
          title='Layers'
          treeData={treeData}
          asyncTree={asyncTree}
          extendedNodeActions={layerActions}
          //@ts-ignore
          addNodeDispatchAction={onCreateLayer}
          //@ts-ignore
          removeNodeDispatchAction={onDeleteLayer}
          //@ts-ignore
          editNodeDispatchAction={onEditLayer}
          dropNodeDispatchAction={onDropLayer}
          checkNodeDispacthAction={onCheckLayer}
          selectNodeDispatchAction={onSelectLayer}
          customTreeTitleAction={customLayerManagerTitleAction}
          nodeAttributeForm={layerAttributeForm}
          treeNodeTitlePreIcons={layerAttributeInfoIcons}
          multipleSelection={multipleSelection}
        />
      )}
    </div>
  );
};
