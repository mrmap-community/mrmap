import { Form, Modal } from 'antd';
import React, { FC, ReactNode, useState } from 'react';

import { TreeNodeType } from '../TreeFormField';

interface TreeFormFieldModalProps {
  node: TreeNodeType;
  isModalVisible: boolean;
  title: string;
  onCancelClick: () => void;
  onOkClick: (node: TreeNodeType, values?: any) => void;
  attributeForm?: ReactNode;
}

export const TreeFormFieldModal: FC<TreeFormFieldModalProps> = ({
  node,
  isModalVisible,
  title,
  onCancelClick,
  onOkClick,
  attributeForm = (<></>)
}) => {
  const [nodeValues, setNodeValues] = useState<any>();

  return (
    <Modal
        title={title}
        visible={isModalVisible}
        onOk={() => onOkClick(node, nodeValues)}
        onCancel={onCancelClick}
      >
        {attributeForm}
      </Modal>
  );
};
