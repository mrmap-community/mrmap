import { Key } from 'antd/lib/table/interface';
import { ReactNode } from 'react';
import { JsonApiResponse } from '../../Repos/JsonApiRepo';
import { TreeFormFieldDropNodeEventType, TreeNodeType } from '../Shared/FormFields/TreeFormField/TreeFormFieldTypes';

type OlWMSServerType = 'ESRI' | 'GEOSERVER' | 'MAPSERVER' | 'QGIS';

export interface CreateLayerOpts {
  url: string;
  version: '1.1.0' | '1.1.1' | '1.3.0';
  format: 'image/jpeg' | 'image/png';
  layers: string;
  visible: boolean;
  serverType: OlWMSServerType;
  layerId?: string | number;
  legendUrl: string;
  title: string;
  description?: string;
  properties: Record<string, string>;
  extent?: any[]
}

export interface LayerManagerProps {
  initLayerTreeData:any
  layerManagerLayerGroupName?: string;
  asyncTree?: boolean;
  addLayerDispatchAction?:(
    nodeAttributes: any,
    newNodeParent?: string | number | null | undefined) => Promise<CreateLayerOpts> | CreateLayerOpts | void;
  removeLayerDispatchAction?: (nodeToRemove: TreeNodeType) => Promise<JsonApiResponse> | void;
  editLayerDispatchAction?: (nodeId:number|string, nodeAttributesToUpdate: any) => Promise<JsonApiResponse> | void;
  dropLayerDispatchAction?: (dropEvent:TreeFormFieldDropNodeEventType) => Promise<JsonApiResponse> | void;
  selectLayerDispatchAction?: (selectedKeys: Key[], info: any) => void;
  customLayerManagerTitleAction?: () => undefined | void;
  layerCreateErrorDispatchAction?: (error: any) => undefined | void;
  layerRemoveErrorDispatchAction?: (error: any) => undefined | void;
  layerEditErrorDispatchAction?: (error: any) => undefined | void;
  layerAttributeInfoIcons?: (nodeData: TreeNodeType) => ReactNode;
  layerAttributeForm?: ReactNode;
  multipleSelection?: boolean;
}
