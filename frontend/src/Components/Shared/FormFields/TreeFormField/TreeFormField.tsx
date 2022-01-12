import { EditFilled, FolderAddFilled, MinusCircleFilled, PlusCircleFilled } from '@ant-design/icons';
import { Button, Drawer, Dropdown, Input, Menu, Modal, Space, Tooltip, Tree } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import { Key } from 'antd/lib/table/interface';
import { DataNode, EventDataNode } from 'antd/lib/tree';
import Collection from 'ol/Collection';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import ImageWMS from 'ol/source/ImageWMS';
import React, { cloneElement, createRef, FC, ReactNode, useEffect, useState } from 'react';
import { JsonApiPrimaryData, JsonApiResponse } from '../../../../Repos/JsonApiRepo';
import { CreateLayerOpts, createMrMapOlWMSLayer } from '../../../LayerTree/LayerTree';
import './TreeFormField.css';



interface MPTTJsonApiAttributeType {
  description: string;
  title: string;
  layer_scale_min?: string; // eslint-disable-line
  layer_scale_max?: string; // eslint-disable-line
  preview_image?: string; // eslint-disable-line
  lft: number;
  rght: number;
  tree_id: number; // eslint-disable-line
  level: number;
  is_leaf: boolean; // eslint-disable-line
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
  checkNodeDispacthAction?: (checkedKeys: (Key[] | {checked: Key[]; halfChecked: Key[];}), info: any) => void;
  selectNodeDispatchAction?: (selectedKeys: Key[], info: any) => void;
  draggable?: boolean;
  nodeAttributeForm?: ReactNode;
  addNodeGroupActionIcon?: ReactNode;
  addNodeActionIcon?: ReactNode;
  removeNodeActionIcon?: ReactNode;
  editNodeActionIcon?: ReactNode;
  title?: string;
  attributeContainer?: 'modal' | 'drawer';
  contextMenuOnNode?: boolean;
  showMaskOnNodeAttributeForm?: boolean;
  checkableNodes?: boolean;
}

// TODO: create helper files with several tree methods inside. This file is too big.
// Maybe separate it into helper functions for specific actions on the tree and another with rendering
// of subcomponents

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
      isLeaf: element.attributes.is_leaf,
      properties: {
        description: element.attributes.description,
        datasetMetadata: element.relationships.dataset_metadata.data?.id,
        renderingLayer: element.relationships.rendering_layer.data?.id,
        scaleMin: element.attributes.layer_scale_min,
        scaleMax: element.attributes.layer_scale_max,
        style: element.relationships.layer_style.data?.id,
        featureSelectionLayer: element.relationships.selection_layer.data?.id,
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

export const TreeNodeListToOlLayerGroup = (list: TreeNodeType[]): Collection<LayerGroup | ImageLayer<ImageWMS>> => {
  const layerList = list.map(node => {
    if (node.children.length >= 0 && !node.isLeaf) {
      const layerGroupOpts = {
        opacity: 1,
        visible: false,
        properties: {
          title: node.properties.title,
          description: node.properties.description,
          parent: node.parent,
          key: node.key,
          mrMapLayerId: node.key
        },
        layers: TreeNodeListToOlLayerGroup(node.children)
      };
      return new LayerGroup(layerGroupOpts);
    } 

    if(node.children.length === 0 && node.isLeaf) {
      const layerOpts: CreateLayerOpts = {
        url: '',
        version: '1.1.0',
        format: 'image/png',
        layers: '',
        serverType: 'MAPSERVER',
        visible: false,
        mrMapLayerId: '',
        legendUrl: '',
        title: node.properties.title,
        description: node.properties.description,
        properties: {
          ...node.properties,
          parent: node.parent,
          key: node.key,
          mrMapLayerId: node.key
        }
      };
      return createMrMapOlWMSLayer(layerOpts);
    }
    return new LayerGroup();
  });
  return new Collection(layerList);
};

export const MPTTListToOLLayerGroup = (list:MPTTJsonApiTreeNodeType[]): Collection<LayerGroup | BaseLayer> => {
  if(list) {
    const treeNodeList = MPTTListToTreeNodeList(list);
    const layerGroupList = TreeNodeListToOlLayerGroup(treeNodeList);
    return layerGroupList;
  }
  return new Collection();
};

export const TreeFormField: FC<TreeProps> = ({
  treeData = [],
  asyncTree = false,
  addNodeDispatchAction = () => undefined,
  removeNodeDispatchAction = () => undefined,
  editNodeDispatchAction = () => undefined,
  dragNodeDispatchAction = () => undefined,
  checkNodeDispacthAction = () => undefined,
  selectNodeDispatchAction = () => undefined,
  draggable = false,
  nodeAttributeForm = (<></>),
  addNodeGroupActionIcon = (<FolderAddFilled/>),
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
  const [checkedKeys, setCheckedKeys] = useState<(Key[] | {checked: Key[]; halfChecked: Key[];})>([]);
  const [selectedNode, setSelectedNode] = useState<TreeNodeType | undefined>(undefined);
  const [newNodeName, setNewNodeName] = useState<string>('');
  const [isEditingNodeName, setIsEditingNewNodeName] = useState<boolean>(false);
  const [isCreatingGroupNode, setIsCreatingGroupNode] = useState<boolean>(true);
  const [newNodeGroupIncrementValue, setNewNodeGroupIncrementValue] = useState<number>(1);

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
  const updateTreeData = (list: TreeNodeType[], key?: React.Key, children?: TreeNodeType[]): TreeNodeType[] => {
    return list.map(node => {
      if(key && children){
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
      } else {
        return node;
      }
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
   * @description Method to update the tree data when user adds a node
   * @param node
   * @param newNode
   */
  const setTreeDataOnAdd = (node: TreeNodeType, newNode: TreeNodeType) => {
    if (!newNode.parent) {
      setTreeData([..._treeData, newNode]);
    } else {
      setTreeData(updateTreeData(_treeData, node.key, [...node.children, newNode]));
    }
    setExpandedKeys([...expandedKeys, newNode.key]);
    setIsAddingNode(false);
    if (isNodeAttributeFormVisible) {
      toggleNodeAttributeForm();
    }
    // reset to the default value
    setIsCreatingGroupNode(true);
  };

  /**
   * @description Method to update the tree data when user edits a node
   * @param node
   */
  const setTreeDataOnRemove = (node: TreeNodeType) => {
    const parentNode = getNodeParent(_treeData, node);
    if (parentNode.length > 0) {
      const indexToRemove = parentNode[0].children.indexOf(node);
      parentNode[0].children.splice(indexToRemove, 1);
      const expandedNodeIndexToRemove = expandedKeys.indexOf(node.key);
      expandedKeys.splice(expandedNodeIndexToRemove, 1);
      setExpandedKeys(expandedKeys);
      setTreeData(updateTreeData(_treeData, parentNode[0].key, parentNode[0].children));
    } else {
      const rootToRemove = _treeData.find(n => node.key === n.key);
      if(rootToRemove) {
        _treeData.splice(_treeData.indexOf(rootToRemove),1);
        setTreeData(updateTreeData(_treeData));
      }
      
    }
  };

  const setTreeDataOnEdit = (node: TreeNodeType) => {
    setTreeData(updateTreeData(_treeData, node.key, node.children));
    if (isNodeAttributeFormVisible) {
      toggleNodeAttributeForm();
    }
  };

  /**
   * @description Method to update the tree data when user moves a node
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

    // Find dragObject and remove it from parent
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
  const onAddNode = async (node: TreeNodeType | undefined, values: any, isRoot = false) => {
    if (node) {
      const newNode: TreeNodeType = {
        title: values.title || `${node.key}-${node.children.length}`,
        key: `${node.key}-${node.children.length}`, // this will be the id of the created node on async
        children: [],
        parent: isRoot ? null : node.key,
        properties: values || null,
        expanded: true,
        isLeaf: isCreatingGroupNode ? false : true,
      };
      if (asyncTree) {
        setIsAddingNode(true);
        try {
          const response = await addNodeDispatchAction({
            ...values, 
            isLeaf: newNode.isLeaf
          }, 
          newNode.parent);
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
        node.properties = values;
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
   * @description Method to define the action to happen when the user moves and drops a node.
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
   * @description Method to define the action to happen when the user clicks to expand or retract a node
   * @param expandedKeys
   * @param info
   */
  const onExpand = (
    _expandedKeys:Key[], 
    info: { node: EventDataNode; expanded: boolean; nativeEvent: MouseEvent; }
  ) => {
    const node = info.node;
    if (info.expanded) {
      _expandedKeys.push(node.key);
    } else {
      _expandedKeys.splice(_expandedKeys.indexOf(node.key), 1);
    }
    setExpandedKeys(_expandedKeys);
  };
  
  /**
   * @description Method to define the action to happen when the user clicks on the checkbox
   * @param checkedKeys
   * @param info
   */
  const onCheck = (_checkedKeys: (Key[] | {checked: Key[]; halfChecked: Key[];}), info: any) => {
    const node = info.node;
    if (info.checked) {
      //@ts-ignore
      checkedKeys.push(info.node.props.key);
    } else {
      //@ts-ignore
      checkedKeys.splice(_checkedKeys.indexOf(node.key), 1);
    }
    setCheckedKeys(_checkedKeys);
    checkNodeDispacthAction(_checkedKeys, info);
  };

  const onSelect = (_selectedKeys: Key[], info: any) => {
    selectNodeDispatchAction(_selectedKeys, info);
  };
  /**
   * @description Method to create a root node
   */
  const onCreateNewNodeGroup = (isRoot: boolean) => {
    const nodeToCreate = {
      title: `Group node (${newNodeGroupIncrementValue})`,
      key: String(newNodeGroupIncrementValue),
      children: [],
      parent: null,
    };
    const nodeToCreateAttributes = {
      name: `Group node (${newNodeGroupIncrementValue})`,
    };
    onAddNode(nodeToCreate, nodeToCreateAttributes, isRoot);
  };

  /**
   * @ description: Method to clone the node attribute form
   * @param node
   * @returns
   */
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
      },
      showBasicForm: isCreatingGroupNode
    });
  };

  /**
   * @description Method to be called when user changes the node name directly on the node title
   * @param nodeData
   * @param newName
   */
  const onNodeNameEditing = (nodeData: TreeNodeType | undefined, newName: string) => {
    if (nodeData) {
      onEditNode(
        nodeData,
        {
          ...nodeData.properties,
          name: newName
        }
      );
    }
  };

  /**
   * @description TSX element to show context menu
   * @param nodeData
   * @returns
   */
  const nodeContextMenu = (nodeData?: TreeNodeType) => (
    <Menu>
      {!nodeData?.isLeaf && (
        <>
          <Menu.Item
            onClick={() => {
              nodeData && setSelectedNode(nodeData);
              setIsNodeAttributeFormVisible(true);
              setIsCreatingGroupNode(true);
            }}
            icon={addNodeGroupActionIcon}
            key='add-group'
          >
            Add new layer group
          </Menu.Item>
          <Menu.Item
            onClick={() => {
              nodeData && setSelectedNode(nodeData);
              setIsNodeAttributeFormVisible(true);
              setIsCreatingGroupNode(false);
            }}
            icon={addNodeActionIcon}
            key='add-node'
          >
            Add new layer
          </Menu.Item>
        </>
      )}
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
          : nodeData.properties?.name}
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
      // TODO: shouldthe name  be changed here as well?
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
      <div 
        className='tree-form-field-title'
      >
        {title}
        <Tooltip title='Create new node folder'>
          <Button 
            icon={<PlusCircleFilled />} 
            size='small' 
            block
            type='link'
            onClick={() => {
              setNewNodeGroupIncrementValue(newNodeGroupIncrementValue + 1);
              onCreateNewNodeGroup(true);
            }}
          />
        </Tooltip>
      </div>
      <Tree
        checkedKeys={checkedKeys}
        checkable={checkableNodes}
        className='tree-form-field'
        draggable={draggable}
        showIcon
        defaultExpandAll
        onExpand={onExpand}
        onDrop={onDropNode}
        onCheck={onCheck}
        treeData={_treeData}
        showLine
        multiple={false}
        expandedKeys={expandedKeys}
        onSelect={onSelect}
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
