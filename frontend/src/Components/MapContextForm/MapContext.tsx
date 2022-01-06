import { MapComponent, MapContext as ReactGeoMapContext, useMap } from '@terrestris/react-geo';
import { Button, Steps } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import OlLayerGroup from 'ol/layer/Group';
import OlLayerTile from 'ol/layer/Tile';
import OlMap from 'ol/Map';
import OlSourceOsm from 'ol/source/OSM';
import OlView from 'ol/View';
import React, { ReactElement, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { JsonApiPrimaryData } from '../../Repos/JsonApiRepo';
import MapContextLayerRepo from '../../Repos/MapContextLayerRepo';
import MapContextRepo from '../../Repos/MapContextRepo';
import { LayerTree } from '../LayerTree/LayerTree';
import { SearchDrawer } from '../SearchDrawer/SearchDrawer';
import { MPTTListToTreeNodeList, TreeNodeType } from '../Shared/FormFields/TreeFormField/TreeFormField';
import './MapContext.css';
import { MapContextForm } from './MapContextForm';
import { MapContextLayerForm } from './MapContextLayerForm';



const mapContextRepo = new MapContextRepo();
const mapContextLayerRepo = new MapContextLayerRepo();

// TODO: Should be in a separate component or helper
const layerGroup = new OlLayerGroup({
  // @ts-ignore
  name: 'Layergroup',
  layers: [
    new OlLayerTile({
      source: new OlSourceOsm(),
      // @ts-ignore
      name: 'OSM'
    })
  ]
});

const center = [788453.4890155146, 6573085.729161344];

const olMap = new OlMap({
  view: new OlView({
    center: center,
    zoom: 16
  }),
  layers: [layerGroup]
});

// TODO: This is creating a component naamed map. Should be separated
function Map () {
  const map = useMap();

  return (
    <MapComponent
      map={map}
    />
  );
}

export const MapContext = (): ReactElement => {
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
          const response = await mapContextRepo.getMapContextWithLayers(String(id));
          form.setFieldsValue({
            // @ts-ignore
            title: response.mapContext.attributes.title || '',
            // @ts-ignore
            abstract: response.mapContext.attributes.abstract || ''
          });
          //  set  Initial  Tree Data
          const transformedTreeData = MPTTListToTreeNodeList(response.mapContextLayers);
          setInitTreeData(transformedTreeData);
        } catch (error) {
          // @ts-ignore
          throw new Error(error);
        }
      };
      fetchMapContext();
    }
  }, [id, form]);

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
          <div className='mapcontextform-map-area'>
            <MapContextForm
              onSubmit={async (values) => {
                if (!id) {
                  setIsSubmittingMapContext(true);
                  try {
                    const response = await mapContextRepo.create(values);
                    if (response.data?.data && (response.data.data as JsonApiPrimaryData).id) {
                      setCreatedMapContextId((response.data.data as JsonApiPrimaryData).id);
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
          </div>
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
          <div className='Map'>
            <ReactGeoMapContext.Provider value={olMap}>
              <Map />
            </ReactGeoMapContext.Provider>
            <div className='layer-section'>
              <LayerTree
                map={olMap}
                layers={initTreeData}
                addLayerDispatchAction={async (nodeAttributes, newNodeParent) => {
                  return await mapContextLayerRepo.create({
                    ...nodeAttributes,
                    parentLayerId: newNodeParent || '',
                    mapContextId: createdMapContextId
                  });
                }}
                removeLayerDispatchAction={async (nodeToRemove) => (
                  await mapContextLayerRepo?.delete(String(nodeToRemove.key))
                )}
                editLayerDispatchAction={async (nodeId, nodeAttributesToUpdate) => (
                  await mapContextLayerRepo?.update(String(nodeId), nodeAttributesToUpdate)
                )}
                dragLayerDispatchAction={async (nodeBeingDraggedInfo) => {
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
                layerAttributeForm={(<MapContextLayerForm form={form}/>)}
              />
            </div>
          </div>

          <SearchDrawer />

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
