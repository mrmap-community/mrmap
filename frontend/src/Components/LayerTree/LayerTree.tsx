import { Key } from 'antd/lib/table/interface';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import OlMap from 'ol/Map';
import ImageWMS from 'ol/source/ImageWMS';
import { getUid } from 'ol/util';
import React, { ReactNode, useEffect, useState } from 'react';
import { JsonApiResponse } from '../../Repos/JsonApiRepo';
import LayerRepo from '../../Repos/LayerRepo';
import { TreeFormField, TreeNodeType } from '../Shared/FormFields/TreeFormField/TreeFormField';

type OlWMSServerType = 'ESRI' | 'GEOSERVER' | 'MAPSERVER' | 'QGIS';

export interface CreateLayerOpts {
  url: string;
  version: '1.1.0' | '1.1.1' | '1.3.0';
  format: 'image/jpeg' | 'image/png';
  layers: string;
  visible: boolean;
  serverType: OlWMSServerType;
  mrMapLayerId?: string | number;
  legendUrl: string;
  title: string;
  name?: string;
  properties: Record<string, string>;
  extent?: any[]
}

interface LayerTreeProps {
  map: OlMap
  layerGroup?: LayerGroup;
  asyncTree?: boolean;
  addLayerDispatchAction?:(
    nodeAttributes: any,
    newNodeParent?: string | number | null | undefined) =>
    Promise<JsonApiResponse> | void;
  removeLayerDispatchAction?: (nodeToRemove: TreeNodeType) => Promise<JsonApiResponse> | void;
  editLayerDispatchAction?: (nodeId:number|string, nodeAttributesToUpdate: any) => Promise<JsonApiResponse> | void;
  dragLayerDispatchAction?: (nodeBeingDraggedInfo: any) => Promise<JsonApiResponse> | void;
  layerAttributeForm?: ReactNode;
}

// export const setLayerSourceWMSParams = (layer: ImageLayer<ImageWMS>) => {
//   const source = layer.getSource();
//   source.setUrl('');
//   source.serverType:
// }

export const getAllMapLayers = (collection:OlMap | LayerGroup ) => {
  if (!(collection instanceof OlMap) && !(collection instanceof LayerGroup)) {
    console.error('Input parameter collection must be from type `ol.Map` or `ol.layer.Group`.');
    return [];
  }

  const layers = collection.getLayers().getArray();
  const allLayers:any = [];

  layers.forEach((layer) => {
    if (layer instanceof LayerGroup) {
      getAllMapLayers(layer).forEach((layeri:any) => allLayers.push(layeri));
    }
    allLayers.push(layer);
  });
  
  return allLayers;
};

export const createMrMapOlWMSLayer = (opts: CreateLayerOpts): ImageLayer<ImageWMS> => {
  const olLayerSource = new ImageWMS({
    url: opts.url,
    params: {
      'LAYERS': opts.layers,
      'VERSION': opts.version,
      'FORMAT': opts.format,
      'TRANSPARENT': true
    },
    serverType: opts.serverType
  });

  const olWMSLayer = new ImageLayer({
    source: olLayerSource,
    visible: opts.visible,
  });

  olWMSLayer.setProperties({
    mrMapLayerId: opts.mrMapLayerId,
    legendUrl: opts.legendUrl,
    title: opts.title,
    name: opts.name,
    extent: opts.extent,
    ...opts.properties
  });

  return olWMSLayer;
};

export const getLayerByMrMapLayerIdName= (map: OlMap, id: string | number): LayerGroup | BaseLayer => {
  const layersToSearch = getAllMapLayers(map);
  return layersToSearch.find((layer:any) => {
    return String(layer.getProperties().mrMapLayerId) === String(id);
  });
};

export const getLayerGroupByName = (map: OlMap, layerGroupName: string): LayerGroup | undefined=> {
  const requiredLayerGroup =  map
    .getLayerGroup()
    .getLayers()
    .getArray()
    .find(layer => layer.getProperties().name === layerGroupName);
  if(requiredLayerGroup instanceof LayerGroup){
    return requiredLayerGroup;
  }
};

export const addLayerToGroup = (map:OlMap, layerGroupName: string, layerToAdd: LayerGroup | BaseLayer): void => {
  const layerGroup: LayerGroup | undefined = getLayerGroupByName(map, layerGroupName);
  if(layerGroup) {
    const layerArray = layerGroup.getLayers();
    layerArray.push(layerToAdd);
    layerGroup.setLayers(layerArray);
  } else {
    console.warn(`No layer group with the name ${layerGroupName}, was found on the map`);
  }
};

export const OlLayerGroupToTreeNodeList = (layerGroup: LayerGroup): TreeNodeType[] => {
  return layerGroup.getLayers().getArray().map((layer: LayerGroup | BaseLayer) => {
    const node: any = {
      key: layer.getProperties().mrMapLayerId,
      title: layer.getProperties().title,
      parent: layer.getProperties().parent,
      properties: layer.getProperties(),
      isLeaf: true,
      expanded: layer instanceof LayerGroup,
      children: []
    }; 
    if (layer instanceof LayerGroup ) {
      node.children = OlLayerGroupToTreeNodeList(layer);
      node.isLeaf = false;
    }
    return node;
  });
};

export const OlLayerToTreeNode = (layer: BaseLayer): TreeNodeType => {
  const node: any = {
    key: layer.getProperties().mrMapLayerId,
    title: layer.getProperties().title,
    parent: layer.getProperties().parent,
    properties: layer.getProperties(),
    isLeaf: true,
    expanded: layer instanceof LayerGroup,
    children: []
  }; 
  return node;
};

export const getLayerWMSDetailsById = async(layerId: string) => {
  try {
  const response = await new LayerRepo().autocompleteInitialValue(layerId);
  return response;
  } catch (error) {
    //@ts-ignore
    throw new Error(error);
  }
};

const layerTreeLayerGroup = new LayerGroup({
  opacity: 1,
  visible: true,
  properties: {
    name: 'mrMapLayerTreeLayerGroup'
  },
  layers: []
});

export const LayerTree = ({
  map,
  layerGroup = layerTreeLayerGroup,
  asyncTree = false,
  addLayerDispatchAction = () => undefined,
  removeLayerDispatchAction = () => undefined,
  editLayerDispatchAction = () => undefined,
  dragLayerDispatchAction = () => undefined,
  layerAttributeForm,
}: LayerTreeProps): JSX.Element => {
  // TODO: all logic to handle layers or interaction between map and layers should be handled here,
  // not to the tree form field component.
  // The tree form field component handles generic logic for a tree, not for the layers or interaction with map.
  // Only change it if you detect aa bug thaat could be traced baack deep to the tree form field

  const [treeData, setTreeData] = useState<TreeNodeType[]>([]);

  useEffect(() => {
    const onLayerGroupChange = (e:any) => {
        setTreeData(OlLayerGroupToTreeNodeList(layerGroup));
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
    map.addLayer(layerGroup);
    setTreeData(OlLayerGroupToTreeNodeList(layerGroup));
    const allMapLayers = getAllMapLayers(layerGroup);
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
    layerGroup.on('change', onLayerGroupChange);
    return () => {
      layerGroup.un('change', onLayerGroupChange);
      map.removeLayer(layerGroup);
    };

  }, [layerGroup, map]);

  const onCheckLayer = (checkedKeys: (Key[] | {checked: Key[]; halfChecked: Key[];}), info: any) => {
    const { checked } = info;
    const eventKey = info.node.key;
    const layer = getLayerByMrMapLayerIdName(map, eventKey);
    setLayerVisibility(layer, checked);
  };

  const setLayerVisibility = (layer: BaseLayer | LayerGroup, visibility: boolean) => {
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
        const group = layerGroup ? layerGroup : map.getLayerGroup();
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

  return (
    <TreeFormField
      title='Layers'
      treeData={treeData}
      asyncTree={asyncTree}
      addNodeDispatchAction={addLayerDispatchAction}
      removeNodeDispatchAction={removeLayerDispatchAction}
      editNodeDispatchAction={editLayerDispatchAction}
      dragNodeDispatchAction={dragLayerDispatchAction}
      checkNodeDispacthAction={onCheckLayer}
      draggable
      nodeAttributeForm={layerAttributeForm}
      attributeContainer='drawer'
      contextMenuOnNode
      checkableNodes
      createRootNode
    />
  );
};
