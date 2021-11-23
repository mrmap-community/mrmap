import { EditFilled, MinusCircleFilled, PlusCircleFilled } from '@ant-design/icons';
import { Button, Modal, Tooltip } from 'antd';
import React, { FC, ReactNode, useState } from 'react';

import { TreeNodeType } from '../TreeFormField';
import { TreeFormFieldModal } from './TreeFormFieldModal';

interface TreeFormFieldActionsProps {
  node: TreeNodeType;
  onAddNode: (node: TreeNodeType, values: any) => void;
  onRemoveNode: (node: TreeNodeType) => void;
  onEditNode: (node: TreeNodeType, values: any) => void;
  nodeAttributesForm?: ReactNode;
}

export const TreeFormFieldActions: FC<TreeFormFieldActionsProps> = ({
  node,
  onAddNode,
  onRemoveNode,
  onEditNode,
  nodeAttributesForm = (<></>)
}) => {
  const [isModalVisible, setIsModalVisible] = useState<boolean>(false);
  const [modalTitle, setModalTitle] = useState<string>('');
  const [isEditing, setIsEditing] = useState<boolean>(false);

  return (
    <div className='tree-form-field-node'>
      <div className='tree-form-field-node-title'>
        <h3> {node.title}</h3>
      </div>
      <div className='tree-form-field-node-actions'>
        <Tooltip title="Create Node">
          <Button
            onClick={() => {
              setModalTitle('Add Node');
              setIsModalVisible(true);
            }}
            type="text"
            icon={<PlusCircleFilled />}
          />
        </Tooltip>
        {node.parent && (
          <Tooltip title="Remove Node">
            <Button
              onClick={() => {
                Modal.warning({
                  title: 'Remove Node',
                  content: 'The selectd node will be removed, Are you sure?',
                  onOk: () => { onRemoveNode(node); }
                });
              }}
              type="text"
              icon={<MinusCircleFilled />}
            />
          </Tooltip>
        )}
        <Tooltip title="Edit Node">
          <Button
            onClick={() => {
              setModalTitle('Edit Node');
              setIsEditing(true);
              setIsModalVisible(true);
            }}
            type="text"
            icon={<EditFilled />}
          />
        </Tooltip>
      </div>
      <TreeFormFieldModal
        node = {node}
        isModalVisible={isModalVisible}
        title = {modalTitle}
        onOkClick={(theNode, values) => {
          if (isEditing) {
            onEditNode(theNode, values);
            setIsEditing(false);
          } else {
            onAddNode(theNode, values);
          }
          setIsModalVisible(false);
        }}
        onCancelClick = {() => {
          setIsEditing(false);
          setIsModalVisible(false);
        }}
        // nodeAttributesForm={nodeAttributesForm}
      />
    </div>
  );
};
