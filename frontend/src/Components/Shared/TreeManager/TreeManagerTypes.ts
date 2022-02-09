import { Key } from 'antd/lib/table/interface';
import { DataNode, EventDataNode } from 'antd/lib/tree';
import { ReactNode } from 'react';
import { JsonApiResponse } from '../../../Repos/JsonApiRepo';

// copied from AntD definition
export type DropNodeEventType = {
    node: EventDataNode;
    dragNode: EventDataNode;
    dragNodesKeys: Key[];
    dropPosition: number;
    dropToGap: boolean;
}
interface MPTTJsonApiAttributeType {
    title: string;
    description: string;
    layerScaleMin?: string;
    layerScaleMax?: string;
    previewImage?: string;
    lft: number;
    rght: number;
    treeId: number;
    level: number
  }
  
  interface MPTTJsonApiRelashionshipDataType {
    data?: {
      type: string;
      id: string;
    }
  }
  
export interface MPTTJsonApiRelashionshipType {
    parent: MPTTJsonApiRelashionshipDataType;
    mapContext: MPTTJsonApiRelashionshipDataType;
    datasetMetadata: MPTTJsonApiRelashionshipDataType;
    renderingLayer: MPTTJsonApiRelashionshipDataType;
    layerStyle: MPTTJsonApiRelashionshipDataType;
    selectionLayer: MPTTJsonApiRelashionshipDataType;
  }
export interface MPTTJsonApiTreeNodeType{
    type: string;
    id: string;
    attributes: MPTTJsonApiAttributeType;
    relationships: MPTTJsonApiRelashionshipType;
    links: {
      self: string;
    }
    children?: TreeNodeType[];
  }
export interface TreeNodeType extends DataNode {
    title: string;
    key: string | number;
    parent?: string | number | null;
    children: TreeNodeType[];
    properties?: any;
    expanded?: boolean;
  }
  
export interface TreeManagerProps {
    treeData: TreeNodeType[];
    asyncTree?: boolean;
    addNodeDispatchAction?:(
      nodeAttributes: any,
      newNodeParent?: string | number | null | undefined) =>
      Promise<JsonApiResponse> | void | undefined;
    removeNodeDispatchAction?: (nodeToRemove: TreeNodeType) => Promise<JsonApiResponse> | void;
    editNodeDispatchAction?: (nodeId:number|string, nodeAttributesToUpdate: any) => Promise<JsonApiResponse> | void;
    dropNodeDispatchAction?: (dropEvent:DropNodeEventType) => Promise<JsonApiResponse> | void;
    checkNodeDispacthAction?: (checkedKeys: (Key[] | {checked: Key[]; halfChecked: Key[];}), info: any) => void;
    selectNodeDispatchAction?: (selectedKeys: Key[], info: any) => void;
    draggable?: boolean;
    nodeAttributeForm?: ReactNode;
    addNodeGroupActionIcon?: ReactNode;
    addNodeActionIcon?: ReactNode;
    removeNodeActionIcon?: ReactNode;
    editNodeActionIcon?: ReactNode;
    nodeOptionsIcon?: ReactNode;
    title?: string;
    contextMenuOnNode?: boolean;
    showMaskOnNodeAttributeForm?: boolean;
    checkableNodes?: boolean;
    extendedNodeActions?: (nodeData?: TreeNodeType) => any;
    customTreeTitleAction?: () => void | undefined;
    treeNodeTitlePreIcons?: (nodeData:TreeNodeType) => ReactNode;
    multipleSelection?: boolean;
    /** (Controlled) Specifies the keys of the selected treeNodes, cf. https://ant.design/components/tree/#API */
    selectedKeys?: string[];
  }
