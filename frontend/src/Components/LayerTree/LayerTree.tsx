import OlMap from 'ol/Map';
import React, { ReactNode } from 'react';

import { JsonApiResponse } from '../../Repos/JsonApiRepo';
import { TreeFormField, TreeNodeType } from '../Shared/FormFields/TreeFormField/TreeFormField';

interface LayerTreeProps {
  map: OlMap
  layers: TreeNodeType[];
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

export const LayerTree = ({
  // TODO: remove eslint disaable when using the map
  map,  // eslint-disable-line
  layers,
  asyncTree = false,
  addLayerDispatchAction = () => undefined,
  removeLayerDispatchAction = () => undefined,
  editLayerDispatchAction = () => undefined,
  dragLayerDispatchAction = () => undefined,
  layerAttributeForm
}: LayerTreeProps): JSX.Element => {
  // TODO: all logic to handle layers or interaction between map and layers should be handled here,
  // not to the tree form field component.
  // The tree form field component handles generic logic for a tree, not for the layers or interaction with map.
  // Only change it if you detect aa bug thaat could be traced baack deep to the tree form field

  // NOTE: Layers should be parsed as a tree node. Openlayers structure is very similar
  return (
    <TreeFormField
      treeData={layers}
      asyncTree={asyncTree}
      addNodeDispatchAction={addLayerDispatchAction}
      removeNodeDispatchAction={removeLayerDispatchAction}
      editNodeDispatchAction={editLayerDispatchAction}
      dragNodeDispatchAction={dragLayerDispatchAction}
      draggable
      nodeAttributeForm={layerAttributeForm}
      attributeContainer='drawer'
      contextMenuOnNode
      checkableNodes
    />
  );
};
