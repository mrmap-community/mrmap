
import React, { cloneElement, createRef, useEffect, useState } from 'react';

import { EditFilled, FolderAddFilled, MinusCircleFilled, PlusCircleFilled, SettingFilled } from '@ant-design/icons';
import { Button, Drawer, Dropdown, Input, Menu, Modal, Space, Tooltip, Tree, Typography } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import { Key } from 'antd/lib/table/interface';
import { EventDataNode } from 'antd/lib/tree';

import { TreeUtils } from '../../../Utils/TreeUtils';

import './TreeManager.css';
import { DropNodeEventType, TreeManagerProps, TreeNodeType } from './TreeManagerTypes';


const treeUtils = new TreeUtils();

export const TreeManager = ({
  treeData = [],
  asyncTree = false,
  addNodeDispatchAction = () => undefined,removeNodeDispatchAction = () => undefined,
  editNodeDispatchAction = () => undefined,
  dropNodeDispatchAction = () => undefined,
  checkNodeDispacthAction = () => undefined,
  selectNodeDispatchAction = () => undefined,
  draggable = false,
  nodeAttributeForm = (<></>),
  addNodeGroupActionIcon = (<FolderAddFilled/>),
  addNodeActionIcon = (<PlusCircleFilled />),
  removeNodeActionIcon = (<MinusCircleFilled />),
  editNodeActionIcon = (<EditFilled />),
  nodeOptionsIcon = (<SettingFilled/>),
  title = '',
  attributeContainer = 'modal',
  contextMenuOnNode = false,
  showMaskOnNodeAttributeForm = false,
  checkableNodes = false,
  extendedNodeActions= () => undefined,
  treeNodeTitlePreIcons = () => (<></>),
  multipleSelection = false,
  selectedKeys = undefined
}: TreeManagerProps): JSX.Element => {
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
  * @description TSX element to show node action
  * @param nodeData
  * @returns
  */
  const getNodeActions = (nodeData: TreeNodeType): JSX.Element => (
    <div className='tree-form-field-node-actions'>
      <Dropdown
        overlay={getNodeContextMenu(nodeData)}
        trigger={['click']}
      >
        <Tooltip title='Node options'>
          <Button
            onClick={() => {
              setSelectedNode(nodeData);
            }}
            type='text'
            icon={nodeOptionsIcon}
          />
        </Tooltip>
      </Dropdown>
    </div>
  );

  /**
  * @description TSX element to show context menu
  * @param nodeData
  * @returns
  */
  const getNodeContextMenu = (nodeData?: TreeNodeType) => (
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
              setIsCreatingGroupNode(false);
              setIsNodeAttributeFormVisible(true);
            }}
            icon={addNodeActionIcon}
            key={`add-node-${nodeData?.key}`}
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
          if(nodeData?.isLeaf) {
            setIsCreatingGroupNode(false);
          }
        }}
        icon={editNodeActionIcon}
        key='edit-node'
      >
        Properties
      </Menu.Item>
      {/* <Divider orientation='right' plain /> */}
      {extendedNodeActions(nodeData)}
    </Menu>
  );

  /**
  * @description TSX element to show node title
  * @param nodeData
  * @returns
  */
  const getNodeTitle = (nodeData: TreeNodeType): JSX.Element => {
    return (
      <div className='tree-node-title'>
        <Dropdown
          overlay={getNodeContextMenu(nodeData)}
          trigger={contextMenuOnNode ? ['contextMenu'] : []}
        >
          <div
            className='tree-form-field-node-title'
            onDoubleClick={() => {
              setSelectedNode(nodeData);
              setIsEditingNewNodeName(true);
              setNewNodeName(nodeData.properties.title);
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
              : (
                <Typography.Text style={{ maxWidth: '200px' }} ellipsis={true}>
                  {nodeData.properties.title}
                </Typography.Text>
              ) 
            }
          </div>
        </Dropdown>
      </div>
    );
  };
  
  /**
   * @description Method to create a root node
   */
  const onCreateNewNodeGroup = (isRoot: boolean) => {
    const nodeToCreate = {
      // this is the node object title.
      // Is basically used to identify the node by a name and it is rendered as the node's tooltip.
      // It has nothing to do with our title property.
      title: 'A group node', 
      key: String(newNodeGroupIncrementValue),
      children: [],
      parent: null,
    };
    const nodeToCreateAttributes = {
      title: `Group node (${newNodeGroupIncrementValue})`,
      description: 'A group node',
    };
    onAddNode(nodeToCreate, nodeToCreateAttributes, isRoot);
  };

  /**
   * @description: Asyncronous method to define the action to happen when the user wants to add a new node.
   * If using an asyncronous tree, a JsonApiReponse is expected
   * @param node
   */
  const onAddNode = async (node: TreeNodeType | undefined, values: any, isRoot = false) => {
    if (node) {

      const newNode: TreeNodeType = {
        title: node.title || `${node.key}-${node.children.length}`,
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
          const createdNode = await addNodeDispatchAction(values, newNode.parent);
          // console.log(createdNode);
          // update new node key
          // if (createdNode && createdNode.data?.data && (createdNode.data.data as JsonApiPrimaryData).id) {
          // @ts-ignore
          if (createdNode && createdNode.key) {
            //newNode.key = (createdNode.data.data as JsonApiPrimaryData).id;
            // @ts-ignore
            newNode.key = createdNode.key;
            
            // console.log(newNode);
            setTreeDataOnAdd(node, newNode);
          }
        } catch (error) {
          setIsAddingNode(false);
          // @ts-ignore
          throw new Error(error);
        } 
      } else {
        addNodeDispatchAction(values);
        setTreeDataOnAdd(node, newNode);
      }
    }
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
      setTreeData(treeUtils.updateTreeData(_treeData, node.key, [...node.children, newNode]));
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
   * @description Method to update the tree data when user edits a node
   * @param node
   */
  const setTreeDataOnRemove = (node: TreeNodeType) => {
    const parentNode = treeUtils.getNodeParent(_treeData, node);
    if (parentNode.length > 0) {
      const indexToRemove = parentNode[0].children.indexOf(node);
      parentNode[0].children.splice(indexToRemove, 1);
      const expandedNodeIndexToRemove = expandedKeys.indexOf(node.key);
      expandedKeys.splice(expandedNodeIndexToRemove, 1);
      setExpandedKeys(expandedKeys);
      setTreeData(treeUtils.updateTreeData(_treeData, parentNode[0].key, parentNode[0].children));
    } else {
      const rootToRemove = _treeData.find(n => node.key === n.key);
      if(rootToRemove) {
        _treeData.splice(_treeData.indexOf(rootToRemove),1);
        setTreeData(treeUtils.updateTreeData(_treeData));
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
      if (asyncTree) {
        setIsEditingNode(true);
        try {
          return await editNodeDispatchAction(
            node.key,
            {
              ...node.properties,
              ...values,
              title: node.properties.title
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

  const setTreeDataOnEdit = (node: TreeNodeType) => {
    setTreeData(treeUtils.updateTreeData(_treeData, node.key, node.children));
    if (isNodeAttributeFormVisible) {
      toggleNodeAttributeForm();
    }
  };
  /**
   * @description Method to define the action to happen when the user moves and drops a node.
   * If using an asyncronous tree, a JsonApiReponse is expected
   * @param info
   * @returns
   */
  const onDropNode = async (dropEvent:DropNodeEventType) => {
    //TODO: avoid droping nodes inside leaves
    if (asyncTree) {
      setIsDraggingNode(true);
      try {
        return await dropNodeDispatchAction(dropEvent);
      } catch (error) {
        setIsDraggingNode(false);
        // @ts-ignore
        throw new Error(error);
      } finally {
        setTreeDataOnMove(dropEvent);
        setIsDraggingNode(false);
      }
    } else {
      dropNodeDispatchAction(dropEvent);
      setTreeDataOnMove(dropEvent);
    }
  };

  // TODO: Refactor thos method in order to be more TS friendly and easier to read
  /**
   * @description Method to update the tree data when user moves a node
   * @param info
   */
  const setTreeDataOnMove = (dropEvent:DropNodeEventType) => {
    //@ts-ignore
    const dropPos = dropEvent.node.pos.split('-');
    //@ts-ignore
    const dropPosition = dropEvent.node.children.length - Number(dropPos[dropPos.length - 1]);
    const dragKey = dropEvent.dragNode.key;
    const dropKey = dropEvent.node.key;
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
    let dragObj:any;
    // @ts-ignore
    loop(data, dragKey, (item, index, arr) => {
      arr.splice(index, 1);
      dragObj = item;
    });

    //  if inserting between nodes
    if (!dropEvent.dropToGap) {
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
      (
        //@ts-ignore
        dropEvent.node.props.children || []).length > 0 && // Has children
        //@ts-ignore
        dropEvent.node.props.expanded && // Is expanded
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
        dragObj.parent = item.key;
      });
      if (dropPosition === -1) {
        // @ts-ignore
        ar.splice(i, 0, dragObj);
      } else {
        // @ts-ignore
        ar.splice(i + 1, 0, dragObj);
      }
    }

    setTreeData(treeUtils.updateTreeData(data));
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
    setCheckedKeys(_checkedKeys);
    checkNodeDispacthAction(_checkedKeys, info);
  };

  const onSelect = (_selectedKeys: Key[], info: any) => {
    setSelectedNode(info.node);
    selectNodeDispatchAction(_selectedKeys, info);
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
      onSubmit: (values: any) => {
        if (!isEditingNodeAttributes) {
          onAddNode(node, values);
        } else {
          onEditNode(node, values);
        }
      },
      nodeInfo: node,
      showBasicInfo: isCreatingGroupNode
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
          title: newName
        }
      );
    }
  };

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
          title: selectedNode.properties.title
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

  // workaround for omitting the selectedKeys attribute completely from the Tree element
  // not sure why, but providing undefined as value of the attribute does not switch of the controlled keys behaviour
  // of the component, while omitting it completely does...
  const selectedKeysAttr = {} as any;
  if (selectedKeys !== undefined) {
    selectedKeysAttr.selectedKeys = selectedKeys;
  }

  return (
    <div className='tree-form-field' >
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
        {...selectedKeysAttr}
        checkedKeys={checkedKeys}
        checkable={checkableNodes}
        className='tree-form-field-tree'
        draggable={draggable}
        showIcon
        defaultExpandAll
        onExpand={onExpand}
        onDrop={onDropNode}
        // TODO limit drop on leaves
        // onDragOver={({ event, node }) => {console.log(event);}}
        onCheck={onCheck}
        onSelect={onSelect}
        treeData={_treeData}
        showLine
        multiple={multipleSelection}
        expandedKeys={expandedKeys}
        // @ts-ignore
        titleRender={(nodeData: TreeNodeType):JSX.Element => (
          <div className='tree-form-field-node'>
            <div className='tree-node-title-group1'>
              <div className='tree-node-title-symbols'>
                {treeNodeTitlePreIcons(nodeData)}
              </div>
              {getNodeTitle(nodeData)}
            </div>
            <div className='tree-node-title-group2'>
              {getNodeActions(nodeData)}
            </div>
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
    </div>
  );
};
