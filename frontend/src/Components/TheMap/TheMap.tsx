
import { Key } from 'antd/lib/table/interface';
import React, { ReactNode } from 'react';
import { JsonApiResponse } from '../../Repos/JsonApiRepo';
import { AutoResizeMapComponent } from '../Shared/AutoResizeMapComponent/AutoResizeMapComponent';
import { DropNodeEventType, TreeNodeType } from '../Shared/TreeManager/TreeManagerTypes';
import { LayerManager } from './LayerManager/LayerManager';
import { CreateLayerOpts } from './LayerManager/LayerManagerTypes';
import './TheMap.css';

export const TheMap = ({ 
  addLayerDispatchAction = () => undefined,
  removeLayerDispatchAction = () => undefined,
  editLayerDispatchAction = () => undefined,
  dropLayerDispatchAction = () => undefined,
  selectLayerDispatchAction = () => undefined,
  customLayerManagerTitleAction = () => undefined,
  layerCreateErrorDispatchAction = () => undefined,
  layerRemoveErrorDispatchAction = () => undefined,
  layerEditErrorDispatchAction = () => undefined,
  layerGroupName,
  initLayerTreeData,
  initExpandedLayerIds = [],
  layerAttributeForm,
  layerAttributeInfoIcons = () => (<></>),
  allowMultipleLayerSelection = false,
  showLayerManager = false,
  selectedLayerIds = undefined,
  draggable = true
}: {
  addLayerDispatchAction?:(
    nodeAttributes: any,
    newNodeParent?: string | number | null | undefined) =>
    Promise<CreateLayerOpts> | CreateLayerOpts | void;
  removeLayerDispatchAction?: (nodeToRemove: TreeNodeType) => Promise<JsonApiResponse> | void;
  editLayerDispatchAction?: (nodeId:number|string, nodeAttributesToUpdate: any) => Promise<JsonApiResponse> | void;
  dropLayerDispatchAction?: (dropEvent:DropNodeEventType) => Promise<JsonApiResponse> | void;
  selectLayerDispatchAction?: (selectedKeys: Key[], info: any) => void;
  customLayerManagerTitleAction?: () => void | undefined;
  layerCreateErrorDispatchAction?: (error: any) => undefined | void;
  layerRemoveErrorDispatchAction?: (error: any) => undefined | void;
  layerEditErrorDispatchAction?: (error: any) => undefined | void;
  layerGroupName: string;
  initLayerTreeData: any;
  initExpandedLayerIds?: string[];
  layerAttributeForm: ReactNode;
  layerAttributeInfoIcons?: (nodeData: TreeNodeType) => ReactNode;
  allowMultipleLayerSelection?: boolean;
  showLayerManager?: boolean;
  selectedLayerIds?: string[];
  draggable?: boolean;
}): JSX.Element => {

  return (
    <div className='the-map-container'>
      {showLayerManager && (
        <LayerManager
          initLayerTreeData={initLayerTreeData}
          initExpandedLayerIds={initExpandedLayerIds}
          layerManagerLayerGroupName={layerGroupName}
          asyncTree
          selectLayerDispatchAction={selectLayerDispatchAction}
          addLayerDispatchAction={addLayerDispatchAction}
          removeLayerDispatchAction={removeLayerDispatchAction}
          editLayerDispatchAction={editLayerDispatchAction}
          dropLayerDispatchAction={dropLayerDispatchAction}
          customLayerManagerTitleAction={customLayerManagerTitleAction}
          layerAttributeForm={layerAttributeForm}
          layerCreateErrorDispatchAction={layerCreateErrorDispatchAction}
          layerRemoveErrorDispatchAction={layerRemoveErrorDispatchAction}
          layerEditErrorDispatchAction={layerEditErrorDispatchAction}
          layerAttributeInfoIcons={layerAttributeInfoIcons}
          multipleSelection={allowMultipleLayerSelection}
          selectedLayerIds={selectedLayerIds}
          draggable={draggable}
        />
      )}
      <AutoResizeMapComponent id='the-map' />
    </div>
  );
};
