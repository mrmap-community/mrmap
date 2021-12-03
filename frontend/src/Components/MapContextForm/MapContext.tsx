import './MapContext.css';

import { Button, Steps } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import React, { FC, useState } from 'react';
import { useNavigate } from 'react-router';

import MapContextLayerRepo from '../../Repos/MapContextLayerRepo';
import MapContextRepo from '../../Repos/MapContextRepo';
import { MapContextForm } from './MapContextForm';
import { MapContextLayerForm } from './MapContextLayerForm';
import { TreeFormField } from './TreeFormField';

const mapContextRepo = new MapContextRepo();
const mapContextLayerRepo = new MapContextLayerRepo();

interface MapContextProps {
  edit?:boolean;
}

export const MapContext: FC<MapContextProps> = ({
  edit = false
}) => {
  const navigate = useNavigate();
  const [form] = useForm();

  const [current, setCurrent] = useState(0);
  const [createdMapContextId, setCreatedMapContextId] = useState<string>('');
  const [isSubmittingMapContext, setIsSubmittingMapContext] = useState<boolean>(false);
  const [isRemovingMapContext, setIsRemovingMapContext] = useState<boolean>(false);

  const nextStep = () => {
    setCurrent(current + 1);
  };

  const prevStep = () => {
    setCurrent(current - 1);
  };

  const steps = [
    {
      title: 'Map Context',
      content: (
        <>
          <MapContextForm
            setCreatedMapContextId={(bool) => setCreatedMapContextId(bool)}
            setIsSubmittingMapContext={(id) => setIsSubmittingMapContext(id)}
            onSubmit={() => nextStep()}
            form={form}
          />
          <div className='steps-action'>
            <Button
              type='primary'
              onClick={() => form.submit()}
              disabled={isSubmittingMapContext}
              loading={isSubmittingMapContext}
            >
              Next Step
            </Button>
          </div>
        </>
      )
    },
    {
      title: 'Map Context Layers',
      content: (
        <>
          <TreeFormField
            treeData={[]}
            asyncTree
            addNodeDispatchAction={async (nodeAttributes, newNodeParent) => {
              return await mapContextLayerRepo.create({
                ...nodeAttributes,
                parentLayerId: newNodeParent,
                mapContextId: createdMapContextId
              });
            }}
            removeNodeDispatchAction={async (nodeToRemove) => (
              await mapContextLayerRepo?.delete(String(nodeToRemove.key))
            )}
            editNodeDispatchAction={async (nodeId, nodeAttributesToUpdate) => (
              await mapContextLayerRepo?.update(String(nodeId), nodeAttributesToUpdate)
            )}
            dragNodeDispatchAction={async (nodeBeingDraggedInfo) => {
              const dropKey = nodeBeingDraggedInfo.node.key;
              const dragKey = nodeBeingDraggedInfo.dragNode.key;
              let position:string;
              if (nodeBeingDraggedInfo.node.parent === nodeBeingDraggedInfo.dragNode.parent) {
                position = 'right';
              } else {
                position = 'first-child';
              }
              return await mapContextLayerRepo?.move(dragKey, dropKey, position);
            }}
            draggable
            nodeAttributeForm={(<MapContextLayerForm/>)}
          />
          <div className='steps-action'>
            <Button
              type='primary'
              onClick={async () => {
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
