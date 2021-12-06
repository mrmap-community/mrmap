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
import { TreeFormField } from './TreeFormField';

const mapContextRepo = new MapContextRepo();
const mapContextLayerRepo = new MapContextLayerRepo();

interface MapContextProps {
  edit?:boolean;
}

// const mockMCLayers = [
//   {
//     type: 'MapContextLayer',
//     id: '632',
//     attributes: {
//       name: 'Test1',
//       title: 'test1',
//       layer_scale_min: null,
//       layer_scale_max: null,
//       preview_image: null,
//       lft: 1,
//       rght: 8,
//       tree_id: 1,
//       level: 0
//     },
//     relationships: {
//       parent: {
//         data: null
//       },
//       map_context: {
//         data: {
//           type: 'MapContext',
//           id: '82'
//         }
//       },
//       dataset_metadata: {
//         data: null
//       },
//       rendering_layer: {
//         data: null
//       },
//       layer_style: {
//         data: null
//       },
//       selection_layer: {
//         data: null
//       }
//     },
//     links: {
//       self: 'https://localhost/api/v1/registry/mapcontextlayers/632/'
//     }
//   },
//   {
//     type: 'MapContextLayer',
//     id: '633',
//     attributes: {
//       name: '1',
//       title: '1',
//       layer_scale_min: null,
//       layer_scale_max: null,
//       preview_image: null,
//       lft: 2,
//       rght: 5,
//       tree_id: 1,
//       level: 1
//     },
//     relationships: {
//       parent: {
//         data: {
//           type: 'MapContextLayer',
//           id: '632'
//         }
//       },
//       map_context: {
//         data: {
//           type: 'MapContext',
//           id: '82'
//         }
//       },
//       dataset_metadata: {
//         data: null
//       },
//       rendering_layer: {
//         data: null
//       },
//       layer_style: {
//         data: null
//       },
//       selection_layer: {
//         data: null
//       }
//     },
//     links: {
//       self: 'https://localhost/api/v1/registry/mapcontextlayers/633/'
//     }
//   },
//   {
//     type: 'MapContextLayer',
//     id: '635',
//     attributes: {
//       name: '11',
//       title: '11',
//       layer_scale_min: null,
//       layer_scale_max: null,
//       preview_image: null,
//       lft: 3,
//       rght: 4,
//       tree_id: 1,
//       level: 2
//     },
//     relationships: {
//       parent: {
//         data: {
//           type: 'MapContextLayer',
//           id: '633'
//         }
//       },
//       map_context: {
//         data: {
//           type: 'MapContext',
//           id: '82'
//         }
//       },
//       dataset_metadata: {
//         data: null
//       },
//       rendering_layer: {
//         data: null
//       },
//       layer_style: {
//         data: null
//       },
//       selection_layer: {
//         data: null
//       }
//     },
//     links: {
//       self: 'https://localhost/api/v1/registry/mapcontextlayers/635/'
//     }
//   },
//   {
//     type: 'MapContextLayer',
//     id: '634',
//     attributes: {
//       name: '21',
//       title: '2',
//       layer_scale_min: null,
//       layer_scale_max: null,
//       preview_image: null,
//       lft: 6,
//       rght: 7,
//       tree_id: 1,
//       level: 1
//     },
//     relationships: {
//       parent: {
//         data: {
//           type: 'MapContextLayer',
//           id: '632'
//         }
//       },
//       map_context: {
//         data: {
//           type: 'MapContext',
//           id: '82'
//         }
//       },
//       dataset_metadata: {
//         data: null
//       },
//       rendering_layer: {
//         data: null
//       },
//       layer_style: {
//         data: null
//       },
//       selection_layer: {
//         data: null
//       }
//     },
//     links: {
//       self: 'https://localhost/api/v1/registry/mapcontextlayers/634/'
//     }
//   }
// ];

// const parseMapContextLayers = (rawMapContextLayers: any[]) => {
//   const nodeChildren = rawMapContextLayers.reduce((accumulator, rawNode) => {
//     const property = rawNode.relationships.parent.data?.id || 'root';
//     // @ts-ignore
//     accumulator[property] = accumulator[property] || [];
//     const node = {
//       title: rawNode.attributes.title,
//       key: rawNode.id,
//       children: [],
//       parent: rawNode.relationships.parent.data?.id || null,
//       properties: rawNode.attributes,
//       expanded: true
//     };
//     // @ts-ignore
//     accumulator[property].push(node);
//     // @ts-ignore
//     accumulator[property].sort((a, b) => a.properties.lft - b.properties.lft);

//     return accumulator;
//   }, {});
//   return nodeChildren;
// };

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

  // useEffect(() => {
  //   parseMapContextLayers(mockMCLayers);
  // }, []);

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
      fetchMapContext();
      // TODO: set treeData
    }
  }, [id]);

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
