import { EditFilled, MinusCircleFilled, PlusCircleFilled } from '@ant-design/icons';
import { Button, Modal, Tooltip, Tree } from 'antd';
import { Key } from 'antd/lib/table/interface';
import { EventDataNode } from 'antd/lib/tree';
import React, { FC } from 'react';
import { useNavigate } from 'react-router';

import { TreeNodeType } from './MapContextForm';

interface TreeProps {
  treeData: any[];
  onAddNodeClick?: (nodeData?: any) => void;
  onRemoveNodeClick?: (nodeData?: any) => void;
  onEditNodeClick?: (nodeData?: any) => void;
  onDropNode?: (info?: any) => void;
  onPreviousClick: () => void;
  onExpand?:(expandedKeys: Key[], info: { node: EventDataNode; expanded: boolean; nativeEvent: MouseEvent; }) => void;
  isRemovingMapContext?: boolean;
  isRemovingNode?: boolean;
  draggable?: boolean;
  expandedKeys?: Key[];
}

export const TreeComp: FC<TreeProps> = ({
  treeData = [],
  onAddNodeClick = () => undefined,
  onRemoveNodeClick = () => undefined,
  onEditNodeClick = () => undefined,
  onDropNode = () => undefined,
  onPreviousClick = () => undefined,
  onExpand = () => undefined,
  isRemovingMapContext = false,
  isRemovingNode = false,
  draggable = false,
  expandedKeys = undefined
}) => {
  const navigate = useNavigate();

  return (
    <>
      <h1>Ebenen und Datenangebote</h1>
      <Tree
        className='tree-form-field'
        draggable={draggable}
        // blockNode
        showIcon
        defaultExpandAll
        onExpand={onExpand}
        // onDragEnter={this.onDragEnter}
        onDrop={onDropNode}
        treeData={treeData}
        showLine
        multiple={false}
        expandedKeys={expandedKeys}
        // @ts-ignore
        titleRender={(nodeData: TreeNodeType):JSX.Element => (
          <div className='tree-form-field-node'>
            <div className='tree-form-field-node-title'>
              <h3> {nodeData.title}</h3>
            </div>
            <div className='tree-form-field-node-actions'>
              <Tooltip title='Create Node'>
                <Button
                  onClick={() => onAddNodeClick(nodeData)}
                  type='text'
                  icon={<PlusCircleFilled />}
                />
              </Tooltip>
              {nodeData.parent && (
                <Tooltip title='Remove Node'>
                  <Button
                    onClick={() => {
                      Modal.warning({
                        title: 'Remove Node',
                        content: 'The selectd node will be removed, Are you sure?',
                        onOk: () => onRemoveNodeClick(nodeData),
                        okButtonProps: {
                          disabled: isRemovingNode,
                          loading: isRemovingNode
                        }
                      });
                    }}
                    type='text'
                    icon={<MinusCircleFilled />}
                  />
                </Tooltip>
              )}
              <Tooltip title='Edit Node'>
                <Button
                  onClick={() => onEditNodeClick(nodeData)}
                  type='text'
                  icon={<EditFilled />}
                />
              </Tooltip>
            </div>
          </div>
        )}
      />
      <div className='steps-action'>
        <Button
          type='primary'
          onClick={() => {
            onPreviousClick();
          }}
          disabled={isRemovingMapContext}
          loading={isRemovingMapContext}
        >
          Previous
        </Button>
        <Button
          type='primary'
          htmlType='submit'
          onClick={() => {
            navigate('/registry/mapcontexts/');
          }}
        >
          Finish
        </Button>
      </div>
    </>
  );
};
