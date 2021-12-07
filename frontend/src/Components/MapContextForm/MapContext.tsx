import './MapContext.css';

import { Button, Steps } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import React, { FC, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import MapContextLayerRepo from '../../Repos/MapContextLayerRepo';
import MapContextRepo from '../../Repos/MapContextRepo';
import { hasOwnProperty } from '../../utils';
import { MapContextForm } from './MapContextForm';
import { MapContextLayerForm } from './MapContextLayerForm';
import { TreeFormField, TreeNodeType } from './TreeFormField';

const mapContextRepo = new MapContextRepo();
const mapContextLayerRepo = new MapContextLayerRepo();

interface MapContextProps {
  edit?:boolean;
}

export const MapContext: FC<MapContextProps> = ({
}) => {
  const navigate = useNavigate();
  const [form] = useForm();

  // get the ID parameter from the url
  const { id } = useParams();

  const [current, setCurrent] = useState(0);
  const [createdMapContextId, setCreatedMapContextId] = useState<string>('');
  const [isSubmittingMapContext, setIsSubmittingMapContext] = useState<boolean>(false);
  const [isRemovingMapContext, setIsRemovingMapContext] = useState<boolean>(false);
  const [initTreeData, setInitTreeData] = useState<TreeNodeType[]>([]);

  useEffect(() => {
    // TODO: need to add some sort of loading until the values are fetched
    if (id) {
      const fetchMapContext = async () => {
        try {
          const response = await mapContextRepo.get(id);
          form.setFieldsValue({
            // @ts-ignore
            title: response.data.data.attributes.title || '',
            // @ts-ignore
            abstract: response.data.data.attributes.abstract || ''
          });
        } catch (error) {
          // @ts-ignore
          throw new Error(error);
        }
      };

      const fetchMapContextLayers = async () => {
        try {
          const response = await mapContextRepo.getMapContextLayerFromMapContextId(String(id));
          const cena = listToTree(response);
          setInitTreeData(cena);
        } catch (error) {
          // @ts-ignore
          throw new Error(error);
        }
      };
      fetchMapContext();
      fetchMapContextLayers();
    }
  }, [id]);

  const listToTree = (list:any[]):any => {
    const roots:any[] = [];

    // initialize children on the list element
    list = list.map((element: any) => ({ ...element, children: [] }));

    list = list.map((element:any, index:number) => {
      // transform the list element into a TreeNodeType element
      const node = {
        key: element.id,
        title: element.attributes.title,
        parent: element.relationships.parent.data?.id,
        children: element.children,
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
        const parent = list.find((element1:any) => element1.id === node.parent);
        list[list.indexOf(parent)].children.push(node);
      } else {
        roots.push(node);
      }
    });
    return roots;
  };

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
            onSubmit={async (values) => {
              if (!id) {
                setIsSubmittingMapContext(true);
                try {
                  const response = await mapContextRepo.create(values);
                  if (response.data?.data &&
                    hasOwnProperty(response.data.data, 'id')) {
                    setCreatedMapContextId(response.data.data.id);
                  }
                  return response;
                } catch (error) {
                  setIsSubmittingMapContext(false);
                  // @ts-ignore
                  throw new Error(error);
                } finally {
                  setIsSubmittingMapContext(false);
                  nextStep();
                }
              } else {
                // TODO add action to edit
                setCreatedMapContextId(id);
                nextStep();
              }
            }}
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
            treeData={initTreeData}
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
                if (!id) {
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
                } else {
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
