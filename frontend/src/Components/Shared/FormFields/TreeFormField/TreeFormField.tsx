import './TreeFormField.css';

import { EditFilled, MinusCircleFilled, PlusCircleFilled } from '@ant-design/icons';
import { Button, Drawer, Dropdown, Input, Menu, Modal, Space, Tooltip, Tree } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import { Key } from 'antd/lib/table/interface';
import { DataNode } from 'antd/lib/tree';
import React, { cloneElement, createRef, FC, ReactNode, useEffect, useState } from 'react';

import { JsonApiPrimaryData, JsonApiResponse } from '../../../../Repos/JsonApiRepo';

interface MPTTJsonApiAttributeType {
  name: string;
  title: string;
  layer_scale_min?: string; // eslint-disable-line
  layer_scale_max?: string; // eslint-disable-line
  preview_image?: string; // eslint-disable-line
  lft: number;
  rght: number;
  tree_id: number; // eslint-disable-line
  level: number;
}

interface MPTTJsonApiRelashionshipDataType {
  data?: {
    type: string;
    id: string;
  }
}

export interface MPTTJsonApiRelashionshipType {
  parent: MPTTJsonApiRelashionshipDataType;
  map_context: MPTTJsonApiRelashionshipDataType; // eslint-disable-line
  dataset_metadata: MPTTJsonApiRelashionshipDataType; // eslint-disable-line
  rendering_layer: MPTTJsonApiRelashionshipDataType; // eslint-disable-line
  layer_style: MPTTJsonApiRelashionshipDataType; // eslint-disable-line
  selection_layer: MPTTJsonApiRelashionshipDataType; // eslint-disable-line
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
  key: string | number;
  parent?: string | number | null;
  children: TreeNodeType[];
  properties?: any;
  expanded?: boolean;
}

export interface TreeProps {
  treeData: TreeNodeType[];
  asyncTree?: boolean;
  addNodeDispatchAction?:(
    nodeAttributes: any,
    newNodeParent?: string | number | null | undefined) =>
    Promise<JsonApiResponse> | void;
  removeNodeDispatchAction?: (nodeToRemove: TreeNodeType) => Promise<JsonApiResponse> | void;
  editNodeDispatchAction?: (nodeId:number|string, nodeAttributesToUpdate: any) => Promise<JsonApiResponse> | void;
  dragNodeDispatchAction?: (nodeBeingDraggedInfo: any) => Promise<JsonApiResponse> | void;
  draggable?: boolean;
  nodeAttributeForm?: ReactNode;
  addNodeActionIcon?: ReactNode;
  removeNodeActionIcon?: ReactNode;
  editNodeActionIcon?: ReactNode;
  title?: string;
  attributeContainer?: 'modal' | 'drawer';
  contextMenuOnNode?: boolean;
  showMaskOnNodeAttributeForm?: boolean;
  checkableNodes?: boolean;
}

//  TODO: create helper with several tree methods
/**
* @description: Method to parse an MPTT tree array to a TreeNodeType array
* @param list
* @returns
*/
export const MPTTListToTreeNodeList = (list:MPTTJsonApiTreeNodeType[]):TreeNodeType[] => {
  const roots:TreeNodeType[] = [];

  // initialize children on the list element
  list = list.map((element: MPTTJsonApiTreeNodeType) => ({ ...element, children: [] }));

  list.map((element:MPTTJsonApiTreeNodeType) => {
    // transform the list element into a TreeNodeType element
    const node: TreeNodeType = {
      key: element.id,
      title: element.attributes.title,
      parent: element.relationships.parent.data?.id,
      children: element.children || [],
      properties: {
        name: element.attributes.name,
        datasetMetadata: element.relationships.dataset_metadata.data?.id,
        renderingLayer: element.relationships.rendering_layer.data?.id,
        scaleMin: element.attributes.layer_scale_min,
        scaleMax: element.attributes.layer_scale_max,
        style: element.relationships.layer_style.data?.id,
        featureSelectionLayer: element.relationships.selection_layer.data?.id
      },
      expanded: true
    };
    if (node.parent) {
      const parentNode: MPTTJsonApiTreeNodeType | undefined = list.find((el:any) => el.id === node.parent);
      if (parentNode) {
        list[list.indexOf(parentNode)].children?.push(node);
      }
    } else {
      roots.push(node);
    }
    return element;
  });
  return roots;
};

export const TreeFormField: FC<TreeProps> = ({
  treeData = [],
  asyncTree = false,
  addNodeDispatchAction = () => undefined,
  removeNodeDispatchAction = () => undefined,
  editNodeDispatchAction = () => undefined,
  dragNodeDispatchAction = () => undefined,
  draggable = false,
  nodeAttributeForm = (<></>),
  addNodeActionIcon = (<PlusCircleFilled />),
  removeNodeActionIcon = (<MinusCircleFilled />),
  editNodeActionIcon = (<EditFilled />),
  title = '',
  attributeContainer = 'modal',
  contextMenuOnNode = false,
  showMaskOnNodeAttributeForm = false,
  checkableNodes = false
}) => {
  const [form] = useForm();

  const nodeNameTextInput:any = createRef();

  const [_treeData, setTreeData] = useState<TreeNodeType[]>(treeData);
  const [isNodeAttributeFormVisible, setIsNodeAttributeFormVisible] = useState<boolean>(false);
  const [isEditingNodeAttributes, setIsEditingNodeAttributes] = useState<boolean>(false);
  const [isAddingNode, setIsAddingNode] = useState<boolean>(false);
  const [isEditingNode, setIsEditingNode] = useState<boolean>(false);
  const [isRemovingNode, setIsRemovingNode] = useState<boolean>(false);
  // eslint-disable-next-line
  const [isDraggingNode, setIsDraggingNode] = useState<boolean>(false); // TODO
  const [expandedKeys, setExpandedKeys] = useState<Key[]>([]);
  const [selectedNode, setSelectedNode] = useState<TreeNodeType | undefined>(undefined);
  const [newNodeName, setNewNodeName] = useState<string>('');
  const [isEditingNodeName, setIsEditingNewNodeName] = useState<boolean>(false);

  /**
   * @description: Toggles the modal showing the form with the node properties
   */
  const toggleNodeAttributeForm = () => {
    setIsNodeAttributeFormVisible(!isNodeAttributeFormVisible);
  };

  /**
   * @description: Method to generate a title for the modal containing  the attribute form
   * @returns string
   */
  const getNodeAttributeFormTitle = (): string => {
    if (isEditingNodeAttributes) {
      return 'Edit Node';
    }
    return 'Add Node';
  };

  /**
   * @description Method to determine what should happen when clicking the OK button on the
   * modal containing the attribute form
   */
  const onNodeAttributeFormOkClick = () => {
    form.submit();
  };

  /**
   * @description Method to determine what should happen when clicking the Cancel button on the
   * modal containing the attribute form
   */
  const onNodeAttributeFormCancelClick = () => {
    toggleNodeAttributeForm();
    setIsEditingNodeAttributes(false);
  };

  /**
   * @description Method that runs through the tree and updates the children of a specific node
   * @param list
   * @param key
   * @param children
   * @returns TreeNodeType[]
   */
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

  /**
   * @description Method that finds the parent node of a given node
   * @param list
   * @param node
   * @returns TreeNodeType[] | never[]
   */
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
   * @description Method to updaate the tree data when user adds a node
   * @param node
   * @param newNode
   */
  const setTreeDataOnAdd = (node: TreeNodeType, newNode: TreeNodeType) => {
    if (!newNode.parent) {
      setTreeData([newNode]);
    } else {
      setTreeData(updateTreeData(_treeData, node.key, [...node.children, newNode]));
    }
    setExpandedKeys([...expandedKeys, newNode.key]);
    setIsAddingNode(false);
    if (isNodeAttributeFormVisible) {
      toggleNodeAttributeForm();
    }
  };

  /**
   * @description Method to updaate the tree data when user edits a node
   * @param node
   */
  const setTreeDataOnRemove = (node: TreeNodeType) => {
    const parentNode = getNodeParent(_treeData, node);
    if (parentNode) {
      const indexToRemove = parentNode[0].children.indexOf(node);
      parentNode[0].children.splice(indexToRemove, 1);
      const expandedNodeIndexToRemove = expandedKeys.indexOf(node.key);
      expandedKeys.splice(expandedNodeIndexToRemove, 1);
      setExpandedKeys(expandedKeys);
      setTreeData(updateTreeData(_treeData, parentNode[0].key, parentNode[0].children));
    }
  };

  const setTreeDataOnEdit = (node: TreeNodeType) => {
    setTreeData(updateTreeData(_treeData, node.key, node.children));
    if (isNodeAttributeFormVisible) {
      toggleNodeAttributeForm();
    }
  };

  /**
   * @description Method to updaate the tree data when user moves a node
   * @param info
   */
  const setTreeDataOnMove = (info: any) => {
    const dropPos = info.node.pos.split('-');
    const dropPosition = info.node.children.length - Number(dropPos[dropPos.length - 1]);
    const dragKey = info.dragNode.key;
    const dropKey = info.node.key;

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

    const data = [..._treeData];

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
  };

  /**
   * @description: Asyncronous method to define the action to happen when the user wants to add a new node.
   * If using an asyncronous tree, a JsonApiReponse is expected
   * @param node
   */
  const onAddNode = async (node: TreeNodeType | undefined, values: any) => {
    if (node) {
      const newNode: TreeNodeType = {
        title: values.title || `${node.key}-${node.children.length}`,
        key: `${node.key}-${node.children.length}`, // this will be the id of the created node on async
        children: [],
        parent: node.key === '0' ? null : node.key,
        properties: values || null,
        expanded: true
      };
      if (asyncTree) {
        setIsAddingNode(true);
        try {
          const response = await addNodeDispatchAction(values, newNode.parent);
          // update new node key
          if (response && response.data?.data && (response.data.data as JsonApiPrimaryData).id) {
            newNode.key = (response.data.data as JsonApiPrimaryData).id;
          }
        } catch (error) {
          setIsAddingNode(false);
          // @ts-ignore
          throw new Error(error);
        } finally {
        // update node structure
          setTreeDataOnAdd(node, newNode);
        }
      } else {
        addNodeDispatchAction(values);
        setTreeDataOnAdd(node, newNode);
      }
    }
  };

  /**
   * @description: Method to define the action to happen when the user wants to remove an existing node.
   * If using an asyncronous tree, a JsonApiReponse is expected
   * @param node
   */
  const onRemoveNode = async (node: TreeNodeType | undefined) => {
    if (node) {
      if (asyncTree) {
        setIsRemovingNode(true);
        try {
          return await removeNodeDispatchAction(node);
        } catch (error) {
          setIsRemovingNode(false);
          // @ts-ignore
          throw new Error(error);
        } finally {
          setTreeDataOnRemove(node);
          setIsRemovingNode(false);
        }
      } else {
        removeNodeDispatchAction(node);
        setTreeDataOnRemove(node);
      }
    }
  };

  /**
   * @description: Method to define the action to happen when the user wants to edit an existing node.
   * If using an asyncronous tree, a JsonApiReponse is expected
   * @param node
   */
  const onEditNode = async (node: TreeNodeType | undefined, values: any) => {
    if (node) {
      if (values && node) {
        node.title = values.title;
        node.properties = values.properties;
        delete node.properties.title;
      }
      if (asyncTree) {
        setIsEditingNode(true);
        try {
          return await editNodeDispatchAction(
            node.key,
            {
              ...node.properties,
              title: node.title
            }
          );
        } catch (error) {
          setIsEditingNode(false);
          // @ts-ignore
          throw new Error(error);
        } finally {
          setTreeDataOnEdit(node);
          setIsEditingNode(false);
        }
      } else {
        setTreeDataOnEdit(node);
      }
    }
  };

  /**
   * @description Method to define the action to happen when the user moves aand drops a node.
   * If using an asyncronous tree, a JsonApiReponse is expected
   * @param info
   * @returns
   */
  const onDropNode = async (info:any) => {
    if (asyncTree) {
      setIsDraggingNode(true);
      try {
        return await dragNodeDispatchAction(info);
      } catch (error) {
        setIsDraggingNode(false);
        // @ts-ignore
        throw new Error(error);
      } finally {
        setIsDraggingNode(false);
        setTreeDataOnMove(info);
      }
    } else {
      dragNodeDispatchAction(info);
      setTreeDataOnMove(info);
    }
  };

  /**
   * @description Method to define the action to happen when the user clicks to expaand or retract a node
   * @param expandedKeys
   * @param info
   */
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

  // /**
  //  * @description: Method to render a load icon when tree node is loading data
  //  * @param node
  //  */
  // const onLoadData = async (node: EventDataNode): Promise<void> => {

  //   if (isAddingNode || isDraggingNode || isRemovingNode) {
  //     node.icon = (<PlusCircleFilled spin/>);
  //   }
  // };

  /**
   * @description Method to create a root node
   */
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

  const clonedNodeAttributeForm = (node: TreeNodeType| undefined) => {
    // @ts-ignore
    return cloneElement(nodeAttributeForm, {
      form,
      onSubmit: (values) => {
        if (!isEditingNodeAttributes) {
          onAddNode(node, values);
        } else {
          onEditNode(node, values);
        }
      }
    });
  };

  const onNodeNameEditing = (nodeData: TreeNodeType | undefined, newName: string) => {
    if (nodeData) {
      onEditNode(
        nodeData,
        {
          ...nodeData.properties,
          properties: {
            ...nodeData.properties,
            name: newName
          }
        }
      );
    }
  };

  /**
   * @description TSX element to show context menu
   * @param nodeData
   * @returns
   */
  const nodeContextMenu = (nodeData: TreeNodeType) => (
    <Menu>
      <Menu.Item
        onClick={() => {
          setSelectedNode(nodeData);
          setIsNodeAttributeFormVisible(true);
        }}
        icon={addNodeActionIcon}
        key='add-node'
      >
        Add new layer
      </Menu.Item>
      {nodeData.parent && (
        <Menu.Item
          onClick={() => {
            Modal.warning({
              title: 'Remove Node',
              content: 'The selected node will be removed, Are you sure?',
              onOk: () => onRemoveNode(nodeData),
              okButtonProps: {
                disabled: isRemovingNode,
                loading: isRemovingNode
              }
            });
          }}
          icon={removeNodeActionIcon}
          key='remove-node'
        >
          Delete
        </Menu.Item>
      )}
      <Menu.Item
        onClick={() => {
          setSelectedNode(nodeData);
          setIsNodeAttributeFormVisible(true);
          setIsEditingNodeAttributes(true);
        }}
        icon={editNodeActionIcon}
        key='edit-node'
      >
        Properties
      </Menu.Item>
    </Menu>
  );

  /**
   * @description TSX element to show node title
   * @param nodeData
   * @returns
   */
  const nodeTitle = (nodeData: TreeNodeType) => (
    <Dropdown
      overlay={nodeContextMenu(nodeData)}
      trigger={contextMenuOnNode ? ['contextMenu'] : []}
    >
      <div
        className='tree-form-field-node-title'
        onDoubleClick={() => {
          setSelectedNode(nodeData);
          setIsEditingNewNodeName(true);
          setNewNodeName(nodeData.properties.name);
        }}
      >
        {isEditingNodeName && nodeData.key === selectedNode?.key
          ? (
            <Input
              id='nodeNameInput'
              ref={nodeNameTextInput}
              name='nodeName'
              value={newNodeName}
              onChange={(e) => {
                setNewNodeName(e.target.value);
              }}
              onKeyUp={(e) => {
                if (newNodeName !== '' && e.key === 'Enter') {
                  onNodeNameEditing(selectedNode, newNodeName);
                  setNewNodeName('');
                  setIsEditingNewNodeName(false);
                }
                if (e.key === 'Escape') {
                  setNewNodeName('');
                  setIsEditingNewNodeName(false);
                }
              }}
            />
            )
          : nodeData.properties.name}
      </div>
    </Dropdown>
  );

  /**
   * @description TSX element to show node action
   * @param nodeData
   * @returns
   */
  const nodeActions = (nodeData: TreeNodeType) => (
    <div className='tree-form-field-node-actions'>
      <Tooltip title='Create Node'>
        <Button
          onClick={() => {
            setSelectedNode(nodeData);
            setIsNodeAttributeFormVisible(true);
          }}
          type='text'
          icon={addNodeActionIcon}
        />
      </Tooltip>
      {nodeData.parent && (
        <Tooltip title='Remove Node'>
          <Button
            onClick={() => {
              Modal.warning({
                title: 'Remove Node',
                content: 'The selected node will be removed, Are you sure?',
                onOk: () => onRemoveNode(nodeData),
                okButtonProps: {
                  disabled: isRemovingNode,
                  loading: isRemovingNode
                }
              });
            }}
            type='text'
            icon={removeNodeActionIcon}
          />
        </Tooltip>
      )}
      <Tooltip title='Edit Node'>
        <Button
          onClick={() => {
            setSelectedNode(nodeData);
            setIsNodeAttributeFormVisible(true);
            setIsEditingNodeAttributes(true);
          }}
          type='text'
          icon={editNodeActionIcon}
        />
      </Tooltip>
    </div>
  );

  /**
   * @description: Hook to run on component mount. Creates sets the initial tree data
   */
  useEffect(() => {
    setTreeData(treeData);
  }, [treeData]);

  /**
   * @description: Hook to run on component mount. Creates a root node in case the tree is empty
   */
  useEffect(() => {
    if (_treeData.length === 0) {
      createRootNode();
    }
    // eslint-disable-next-line
  }, []);

  /**
   * @description: Hook to detect a click anywhere on the document. This will reset the isEditingNameOnNode value.
   * Event  will be removed when editingNodeName.id is not present
   */
  useEffect(() => {
    const setNodeNameOnClick = (e:any) => {
      if (e.target.id !== 'nodeNameInput') {
        setIsEditingNewNodeName(false);
        setNewNodeName('');
      }
    };
    if (isEditingNodeName) {
      // TODO: shouldthe name  be changed here  aas  well?
      document.addEventListener('click', setNodeNameOnClick, false);
    }
    // cleanup. Removes event and changes the node name
    return () => {
      document.removeEventListener('click', setNodeNameOnClick, false);
    };
  }, [isEditingNodeName]);

  /**
   * @description: This hook is a backup since the modal is not being destroyed on close,
   * this is a backup solution. Reseting or setting the values when the modal becomes visible
   */
  useEffect(() => {
    if (isNodeAttributeFormVisible) {
      form.resetFields();
      if (isEditingNodeAttributes && selectedNode) {
        form.setFieldsValue({
          ...selectedNode.properties,
          title: selectedNode.title
        });
      }
    }
  // eslint-disable-next-line
  }, [isNodeAttributeFormVisible, selectedNode]);

  /**
   * @description: Hook to control focus once node name input edit field is shown on the node
   */
  useEffect(() => {
    if (nodeNameTextInput.current && isEditingNodeName) {
      nodeNameTextInput.current.focus();
    }
  }, [nodeNameTextInput, isEditingNodeName]);

  return (
    <>
      <h1>{title}</h1>
      <Tree
        checkable={checkableNodes}
        className='tree-form-field'
        draggable={draggable}
        showIcon
        defaultExpandAll
        onExpand={onExpand}
        onDrop={onDropNode}
        treeData={_treeData}
        // loadData={onLoadData}
        showLine
        multiple={false}
        expandedKeys={expandedKeys}
        // @ts-ignore
        titleRender={(nodeData: TreeNodeType):JSX.Element => (
          <div className='tree-form-field-node'>
            {nodeTitle(nodeData)}
            {!contextMenuOnNode && nodeActions(nodeData)}
          </div>

        )}
      />
      {attributeContainer === 'modal' && (
        <Modal
          mask={showMaskOnNodeAttributeForm}
          title={getNodeAttributeFormTitle()}
          visible={isNodeAttributeFormVisible}
          onOk={onNodeAttributeFormOkClick}
          onCancel={onNodeAttributeFormCancelClick}
          destroyOnClose
          okButtonProps={{
            disabled: isAddingNode || isEditingNode,
            loading: isAddingNode || isEditingNode
          }}
        >
          {clonedNodeAttributeForm(selectedNode)}
        </Modal>
      )}
      {attributeContainer === 'drawer' && (
        <Drawer
          mask={showMaskOnNodeAttributeForm}
          title={getNodeAttributeFormTitle()}
          placement='right'
          width={500}
          onClose={onNodeAttributeFormCancelClick}
          visible={isNodeAttributeFormVisible}
          extra={
            <Space>
              <Button onClick={onNodeAttributeFormCancelClick}>Cancel</Button>
              <Button type='primary' onClick={onNodeAttributeFormOkClick}>
                OK
              </Button>
            </Space>
          }
        >
        {clonedNodeAttributeForm(selectedNode)}
      </Drawer>
      )}
    </>
  );
};
