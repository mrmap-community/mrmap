import './MapContextForm.css';

import { Steps } from 'antd';
import { DataNode } from 'antd/lib/tree';
import React, { FC, useEffect, useState } from 'react';

import MapContextLayerRepo from '../../Repos/MapContextLayerRepo';
import MapContextRepo from '../../Repos/MapContextRepo';
import { MapContextForm } from './Step1';
import { MapContextLayerForm } from './Step2';
import { TreeComp } from './Tree';
import { hasOwnProperty } from '../../utils';

export interface TreeNodeType extends DataNode {
  key: string | number;
  parent?: string | number | null;
  children: TreeNodeType[];
  properties?: any;
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

  const getNodeParent = (list: TreeNodeType[], node: TreeNodeType): TreeNodeType[] => {
    return list.reduce((acc: (TreeNodeType[]), value: TreeNodeType) => {
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
  const onAddNode = async (node: TreeNodeType | undefined, values: any) => {
    if (node) {
      const newNode: TreeNodeType = {
        title: values.title || `${node.key}-${node.children.length}`,
        key: `${node.key}-${node.children.length}`, // this will be the id of the created node
        children: [],
        parent: node.key === '0' ? null : node.key,
        properties: values || null
      };
      setIsAddingNode(true);
      debugger;
      try {
        const response = await mapContextLayerRepo.create({
          ...values,
          parentLayerId: newNode.parent,
          mapContextId: createdMapContextId
        });
        // update new node key
        if (response.data?.data
          && hasOwnProperty(response.data.data, 'id')){
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
        if (parentNode.length > 0) {
          const indexToRemove = parentNode[0].children.indexOf(node);
          parentNode[0].children.splice(indexToRemove, 1);
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
