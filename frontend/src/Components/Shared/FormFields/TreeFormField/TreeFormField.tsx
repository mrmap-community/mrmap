import './TreeFormField.css';

import { CarryOutOutlined, FolderFilled } from '@ant-design/icons';
import { Form, Tree } from 'antd';
import { DataNode } from 'antd/lib/tree';
import { cloneDeep } from 'lodash';
import React, { cloneElement, FC, ReactFragment, ReactNode, useEffect, useState } from 'react';

import { MapContextLayerForm } from '../../../MapContextLayerForm/MapContextLayerForm';
import { TreeFormFieldActions } from './Components/TreeFormFieldActions';

export interface TreeNodeType extends DataNode {
  parent?: string | number;
  children: TreeNodeType[];
  properties?: any;
}

interface TreeFormFieldProps {
  title?: string;
  defaultExpandAll?: boolean;
  defaultExpandedKeys?: number[] | string[];
  draggable?: boolean;
  showLine?: boolean;
  initTreeData?: TreeNodeType[];
  onAddNodeClick?: () => void;
  onRemoveNodeClick?: () => void;
  onEditNodeClick?: () => void;

}

export const TreeFormField: FC<TreeFormFieldProps> = ({
  title = '',
  showLine = true,
  draggable = false,
  initTreeData = [
    {
      title: '/',
      key: '0',
      children: [],
      properties: null
    }
  ],
  onAddNodeClick = () => undefined,
  onRemoveNodeClick = () => undefined,
  onEditNodeClick = () => undefined
}) => {
  const [treeData, setTreeData] = useState<TreeNodeType[]>(initTreeData);

  const updateTreeData = (list: TreeNodeType[], key: React.Key, children: TreeNodeType[]): TreeNodeType[] => {
    return list.map(node => {
      if (node.key === key) {
        return {
          ...node,
          children
        };
      }
      if (node.children) {
        return {
          ...node,
          children: updateTreeData(node.children, key, children)
        };
      }

      return node;
    });
  };

  const getNodeParent = (list: TreeNodeType[], node: TreeNodeType): TreeNodeType[] | never[] => {
    return list.reduce((acc: (TreeNodeType[] | never[]), value: TreeNodeType) => {
      if (value.key === node.parent) {
        acc.push(value);
        return acc;
      }
      if (value.children) {
        return getNodeParent(value.children, node);
      }
      return acc;
    }, []);
  };

  /**
   * @description: Method to define the action to happen when the user wants to add a new node
   * @param node
   */
  const onAddNode = (node: TreeNodeType, values: any) => {
    const newNode: TreeNodeType = {
      title: values.title || `${node.key}-${node.children.length}`,
      key: `${node.key}-${node.children.length}`,
      children: [],
      parent: node.key,
      properties: values
    };
    setTreeData(updateTreeData(treeData, node.key, [...node.children, newNode]));
  };

  /**
   * @description: Method to define the action to happen when the user wants to remove an existing node
   * @param node
   */
  const onRemoveNode = (node: TreeNodeType) => {
    const parentNode = getNodeParent(treeData, node);
    if (parentNode.length > 0) {
      const indexToRemove = parentNode[0].children.indexOf(node);
      parentNode[0].children.splice(indexToRemove, 1);
      setTreeData(updateTreeData(treeData, parentNode[0].key, parentNode[0].children));
    }
  };

  /**
   * @description: Method to define the action to happen when the user wants to edit an existing node
   * @param node
   */
  const onEditNode = (node: TreeNodeType, values: any) => {
    if (values) {
      node.title = values.title;
      node.properties = values;
    }
  };

  return (
    <>
    <h1>{title}</h1>
    <Tree
      className="tree-form-field"
      draggable={draggable}
      blockNode
      showIcon
      defaultExpandAll
      // onDragEnter={this.onDragEnter}
      // onDrop={this.onDrop}
      treeData={treeData}
      showLine={showLine}
      multiple={false}
      titleRender={
        (nodeData: TreeNodeType) => (
          <TreeFormFieldActions
            node={nodeData}
            onAddNode={(node, values) => {
              onAddNodeClick();
              // onAddNode(node, {}/*values*/);
            }}
            onRemoveNode={(node) => {
              onRemoveNodeClick();
              // onRemoveNode(node);
            }}
            onEditNode={(node, values) => {
              onEditNodeClick();
              // onEditNode(node, {}/*values*/)
            }}
          />
        )}
        />
    </>
  );
};
