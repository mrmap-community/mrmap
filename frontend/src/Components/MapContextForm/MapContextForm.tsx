import './MapContextForm.css';

import { Steps } from 'antd';
import { Key } from 'antd/lib/table/interface';
import { DataNode } from 'antd/lib/tree';
import React, { FC, useEffect, useState } from 'react';

import MapContextLayerRepo from '../../Repos/MapContextLayerRepo';
import MapContextRepo from '../../Repos/MapContextRepo';
import { hasOwnProperty } from '../../utils';
import { MapContextForm } from './Step1';
import { MapContextLayerForm } from './Step2';
import { TreeComp } from './Tree';

export interface TreeNodeType extends DataNode {
  key: string | number;
  parent?: string | number | null;
  children: TreeNodeType[];
  properties?: any;
  expanded?: boolean;
}

const mapContextRepo = new MapContextRepo();
const mapContextLayerRepo = new MapContextLayerRepo();

export const FormSteps: FC = () => {
  const [current, setCurrent] = useState(0);
  const [isModalVisible, setIsModalVisible] = useState<boolean>(false);
  const [treeData, setTreeData] = useState<TreeNodeType[]>([]);
  const [selectedNode, setSelectedNode] = useState<TreeNodeType>();
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [createdMapContextId, setCreatedMapContextId] = useState<string>('');
  const [isRemovingMapContext, setIsRemovingMapContext] = useState<boolean>(false);
  const [isAddingNode, setIsAddingNode] = useState<boolean>(false);
  const [isRemovingNode, setIsRemovingNode] = useState<boolean>(false);
  const [isDraggingNode, setIsDraggingNode] = useState<boolean>(false);
  const [expandedKeys, setExpandedKeys] = useState<Key[]>([]);

  const toggleModal = () => {
    setIsModalVisible(!isModalVisible);
  };

  const nextStep = () => {
    setCurrent(current + 1);
  };

  const prevStep = () => {
    setCurrent(current - 1);
  };

  // add aa new root node as soon as a map context id exists
  useEffect(() => {
    if (createdMapContextId) {
      createRootNode();
    }
  }, [createdMapContextId]);

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
    return list.flatMap((value: TreeNodeType) => {
      if (value.key === node.parent) {
        return value;
      }
      if (value.children) {
        return getNodeParent(value.children, node);
      }
      return value;
    });
  };

  /**
   * @description: Method to define the action to happen when the user wants to add a new node
   * @param node
   */
  const onAddNode = async (node: TreeNodeType | undefined, values: any) => {
    if (node) {
      const newNode: TreeNodeType = {
        title: values.title || `${node.key}-${node.children.length}`,
        key: `${node.key}-${node.children.length}`, // this will be the id of the created node
        children: [],
        parent: node.key === '0' ? null : node.key,
        properties: values || null,
        expanded: true
      };
      setIsAddingNode(true);
      try {
        const response = await mapContextLayerRepo.create({
          ...values,
          parentLayerId: newNode.parent,
          mapContextId: createdMapContextId
        });
        // update new node key
        if (response.data?.data &&
          hasOwnProperty(response.data.data, 'id')) {
          newNode.key = response.data.data.id;
        }
      } catch (error) {
        setIsAddingNode(false);
        // @ts-ignore
        throw new Error(error);
      } finally {
        // update node structure
        if (!newNode.parent) {
          setTreeData([newNode]);
        } else {
          setTreeData(updateTreeData(treeData, node.key, [...node.children, newNode]));
        }
        setExpandedKeys([...expandedKeys, newNode.key]);
        setIsAddingNode(false);
        if (isModalVisible) {
          toggleModal();
        }
      }
    }
  };

  /**
   * @description: Method to define the action to happen when the user wants to remove an existing node
   * @param node
   */
  const onRemoveNode = async (node: TreeNodeType | undefined) => {
    if (node) {
      setIsRemovingNode(true);
      try {
        return mapContextLayerRepo.delete(String(node.key));
      } catch (error) {
        setIsRemovingNode(false);
        // @ts-ignore
        throw new Error(error);
      } finally {
        const parentNode = getNodeParent(treeData, node);
        if (parentNode) {
          const indexToRemove = parentNode[0].children.indexOf(node);
          parentNode[0].children.splice(indexToRemove, 1);
          const expandedNodeIndexToRemove = expandedKeys.indexOf(node.key);
          setExpandedKeys(expandedKeys.splice(expandedNodeIndexToRemove, 1));
          setTreeData(updateTreeData(treeData, parentNode[0].key, parentNode[0].children));
        }
        setIsRemovingNode(false);
      }
    }
  };

  /**
   * @description: Method to define the action to happen when the user wants to edit an existing node
   * @param node
   */
  const onEditNode = (node: TreeNodeType | undefined, values: any) => {
    if (values && node) {
      node.title = values.title;
      node.properties = values;
    }
  };

  const onDropNode = async (info:any) => {
    const dropKey = info.node.key;
    const dragKey = info.dragNode.key;
    const originKey = info.dragNode.parent;
    const dropPos = info.node.pos.split('-');
    const dropPosition = info.node.children.length - Number(dropPos[dropPos.length - 1]);

    console.log(info.node, info.dragNode);
    setIsDraggingNode(true);
    try {
      let position:string;
      if (info.node.parent === info.dragNode.parent) {
        position = 'right';
      } else {
        position = 'first-child';
      }
      console.log(position, dropKey === dragKey, dropKey, dragKey);
      return mapContextLayerRepo.move(dragKey, dropKey, position);
    } catch (error) {
      setIsDraggingNode(false);
      // @ts-ignore
      throw new Error(error);
    } finally {
      setIsDraggingNode(false);
      // @ts-ignore
      const loop = (data, key, callback) => {
        for (let i = 0; i < data.length; i++) {
          if (data[i].key === key) {
            return callback(data[i], i, data);
          }
          if (data[i].children) {
            loop(data[i].children, key, callback);
          }
        }
      };

      const data = [...treeData];

      // Find dragObject and remove it from paarent
      // @ts-ignore
      let dragObj;
      // @ts-ignore
      loop(data, dragKey, (item, index, arr) => {
        arr.splice(index, 1);
        dragObj = item;
      });

      //  if inserting between nodes
      if (!info.dropToGap) {
      // Drop on the content
      // @ts-ignore
        loop(data, dropKey, item => {
          item.children = item.children || [];
          // where to insert
          // @ts-ignore
          item.children.unshift(dragObj);
        });
      } else if (
      //  if inserting on  first position
        (info.node.props.children || []).length > 0 && // Has children
      info.node.props.expanded && // Is expanded
      dropPosition === 1 // On the bottom gap
      ) {
      // @ts-ignore
        loop(data, dropKey, item => {
          item.children = item.children || [];
          // where to insert
          // @ts-ignore
          item.children.unshift(dragObj);
        // in previous version, we use item.children.push(dragObj) to insert the
        // item to the tail of the children
        });
      } else {
        let ar;
        let i;
        // @ts-ignore
        loop(data, dropKey, (item, index, arr) => {
          ar = arr;
          i = index;
        });
        if (dropPosition === -1) {
        // @ts-ignore
          ar.splice(i, 0, dragObj);
        } else {
        // @ts-ignore
          ar.splice(i + 1, 0, dragObj);
        }
      }
      // @ts-ignore
      setTreeData(data);
    }
  };

  const onExpand = (expandedKeys:any, info:any) => {
    const node = info.node;
    node.expanded = info.expanded;
    if (node.expanded) {
      expandedKeys.push(node.key);
    } else {
      expandedKeys.splice(expandedKeys.indexOf(node.key), 1);
    }
    setExpandedKeys(expandedKeys);
  };

  const createRootNode = () => {
    const nodeToCreate = {
      key: '0',
      children: [],
      parent: null
    };
    const nodeToCreateAttributes = {
      title: 'Root Node',
      name: 'Root Node'
    };
    onAddNode(nodeToCreate, nodeToCreateAttributes);
  };

  const steps = [
    {
      title: 'Map Context',
      content: (
      <MapContextForm
        setCreatedMapContextId={setCreatedMapContextId}
        onStepChange={nextStep}
      />
      )
    },
    {
      title: 'Map Context Layers',
      content: (
        <>
          <MapContextLayerForm
            visible={isModalVisible}
            onSubmit={(values) => {
              if (!isEditing) {
                onAddNode(selectedNode, values);
              } else {
                onEditNode(selectedNode, values);
              }
            }}
            onCancel={() => {
              toggleModal();
              setIsEditing(false);
            }}
            isEditing={isEditing}
            node={selectedNode}
            okButtonProps={{
              disabled: isAddingNode,
              loading: isAddingNode
            }}
          />
          <TreeComp
            draggable
            onExpand={onExpand}
            expandedKeys={expandedKeys}
            onDropNode={onDropNode}
            treeData={treeData}
            onAddNodeClick={(nodeData) => {
              toggleModal();
              setSelectedNode(nodeData);
            }}
            onEditNodeClick={(nodeData) => {
              toggleModal();
              setIsEditing(true);
              setSelectedNode(nodeData);
            }}
            onRemoveNodeClick={(nodeData) => onRemoveNode(nodeData)}
            onPreviousClick={async () => {
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
            }}
            isRemovingMapContext={isRemovingMapContext}
            isRemovingNode={isRemovingNode}
          />
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
