import { MapComponent, MapContext as ReactGeoMapContext, useMap } from '@terrestris/react-geo';
import { Button, notification, Steps } from 'antd';
import { useForm } from 'antd/lib/form/Form';
import Collection from 'ol/Collection';
import { default as OlLayerGroup } from 'ol/layer/Group';
import OlLayerTile from 'ol/layer/Tile';
import OlMap from 'ol/Map';
import { transformExtent } from 'ol/proj';
import OlSourceOsm from 'ol/source/OSM';
import OlView from 'ol/View';
import React, { ReactElement, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { JsonApiPrimaryData } from '../../Repos/JsonApiRepo';
import LayerRepo from '../../Repos/LayerRepo';
import MapContextLayerRepo from '../../Repos/MapContextLayerRepo';
import MapContextRepo from '../../Repos/MapContextRepo';
import { addLayerToGroup, createMrMapOlWMSLayer, LayerTree } from '../LayerTree/LayerTree';
import { SearchDrawer } from '../SearchDrawer/SearchDrawer';
import { MPTTListToOLLayerGroup } from '../Shared/FormFields/TreeFormField/TreeFormField';
import './MapContext.css';
import { MapContextForm } from './MapContextForm';
import { MapContextLayerForm } from './MapContextLayerForm';


const mapContextRepo = new MapContextRepo();
const mapContextLayerRepo = new MapContextLayerRepo();
const layerRepo = new LayerRepo();

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

// TODO: This is creating a component named map. Should be separated
function Map () {
  const map = useMap();

  return (
    <MapComponent
      map={map}
    />
  );
}

const mapContextLayersGroup = new OlLayerGroup({
  opacity: 1,
  visible: true,
  properties: {
    name: 'mrMapMapContextLayers'
  },
  layers: []
});

export const MapContext = (): ReactElement => {
  const navigate = useNavigate();
  const [form] = useForm();

  // get the ID parameter from the url
  const { id } = useParams();

  const [current, setCurrent] = useState(0);
  const [createdMapContextId, setCreatedMapContextId] = useState<string>('');
  const [isSubmittingMapContext, setIsSubmittingMapContext] = useState<boolean>(false);
  const [isRemovingMapContext, setIsRemovingMapContext] = useState<boolean>(false);
  const [initLayerTreeData, setInitLayerTreeData] = useState<Collection<any>>(new Collection());

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
          //  Convert the mapContext layers coming from the server to a compatible tree node list
          const _initLayerTreeData = MPTTListToOLLayerGroup(response.mapContextLayers);
          setInitLayerTreeData(_initLayerTreeData);
        } catch (error) {
          // @ts-ignore
          throw new Error(error);
        }
      };
      fetchMapContext();
    }
  }, [id, form]);

  useEffect(() => {
    mapContextLayersGroup.setLayers(initLayerTreeData);
  }, [initLayerTreeData]);

  
  const nextStep = () => {
    setCurrent(current + 1);
  };

  const prevStep = () => {
    setCurrent(current - 1);
  };

  const onPreviewDatasetOnMapAction = async(dataset:any) => {
    const layerToRemove = olMap.getLayers().getArray().find(l => l.getProperties().name === 'previewMapContextLayer');
    if(layerToRemove) {
      olMap.removeLayer(layerToRemove);
    }
    dataset.layers.forEach(async (layer: string) => {
      try {
        // get the layer details with the id and create an OL Layer
        const renderingLayerDetails = await layerRepo.autocompleteInitialValue(layer);
        const renderingLayerPreview = createMrMapOlWMSLayer({
          extent: renderingLayerDetails.attributes.WMSParams.bbox,
          url: renderingLayerDetails.attributes.WMSParams.url,
          version: renderingLayerDetails.attributes.WMSParams.version,
          format: 'image/png',
          layers: renderingLayerDetails.attributes.WMSParams.layer,
          mrMapLayerId: '',
          visible: true,
          serverType: renderingLayerDetails.attributes.WMSParams.serviceType,
          legendUrl: 'string',
          name: 'previewMapContextLayer',
          title: renderingLayerDetails.attributes.title,
          properties: {}
        });

        const layerExtent = renderingLayerPreview.getExtent();
        if(layerExtent) {
          const transformedExtent = transformExtent(layerExtent, 'EPSG:4326', 'EPSG:3857');
          // TODO
          olMap.getView().fit(transformedExtent);
        }
        olMap.addLayer(renderingLayerPreview);
    } catch (error) {
      //@ts-ignore
      throw new Error(error);
    }
  });
};

  const onAddDatasetToMapAction = async(dataset:any) => {
    dataset.layers.forEach(async (layer: string) => {
      // make call
      try {
        // get the layer details with the id and create an OL Layer
        const renderingLayerDetails = await layerRepo.autocompleteInitialValue(layer);
        // this layer needs to be persisted in the DB. Create this layer in the DB
        const createdLayer = await mapContextLayerRepo.create({
          name:renderingLayerDetails.attributes.title,
          title:renderingLayerDetails.attributes.abstract,
          layerScaleMax:renderingLayerDetails.attributes.scaleMax,
          layerScaleMin:renderingLayerDetails.attributes.scaleMin,
          isLeaf: true,
          renderingLayer: renderingLayerDetails.attributes.id,
          parentLayerId: '', // here must be the current selected node
          mapContextId: createdMapContextId
        });
        
        const renderingLayer = createMrMapOlWMSLayer({
          url: renderingLayerDetails.attributes.WMSParams.url,
          version: renderingLayerDetails.attributes.WMSParams.version,
          format: 'image/png',
          layers: renderingLayerDetails.attributes.WMSParams.layer,
          //@ts-ignore
          mrMapLayerId: createdLayer.data?.data?.id,
          visible: false,
          serverType: renderingLayerDetails.attributes.WMSParams.serviceType,
          legendUrl: 'string',
          //@ts-ignore
          name: createdLayer?.data?.data?.attributes?.name,
          title: renderingLayerDetails.attributes.title,
          //@ts-ignore
          properties: createdLayer?.data?.data?.attributes
        });

        addLayerToGroup(olMap, 'mrMapMapContextLayers', renderingLayer);
        notification.info({
          message: `Add dataset '${dataset.title}'`
        });
      } catch (error) {
        //@ts-ignore
        throw new Error(error);
      }
  });
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
                layerGroup={mapContextLayersGroup}
                asyncTree
                addLayerDispatchAction={async (nodeAttributes, newNodeParent) => {
                  try {
                    const createdLayer = await mapContextLayerRepo.create({
                      ...nodeAttributes,
                      parentLayerId: newNodeParent || '',
                      mapContextId: createdMapContextId
                    });
                    
                    //@ts-ignore
                    // const renderingLayerId = createdLayer.data?.data?.relationships.rendering_layer?.data?.id;
                    // if(renderingLayerId) {
                    //   try {
                    //     const rl = await layerRepo.autocompleteInitialValue(renderingLayerId);
                    //     const renderingLayer = createMrMapOlWMSLayer({
                    //       //eslint-disable-next-line
                    //       url: rl.attributes.WMSParams.url,
                    //       version: rl.attributes.WMSParams.version,
                    //       format: 'image/png',
                    //       layers: rl.attributes.WMSParams.layer,
                    //       visible: true,
                    //       serverType: rl.attributes.WMSParams.serviceType,
                    //       //@ts-ignore
                    //       mrMapLayerId: createdLayer.data.data.id,
                    //       legendUrl: 'string',
                    //       //@ts-ignore
                    //       title: createdLayer.data.data.attributes.title,
                    //       //@ts-ignore
                    //       name: createdLayer.data.data.attributes.name,
                    //       properties: {
                    //         //@ts-ignore
                    //         parent: null
                    //       }
                    //     });
                    //     addLayerToGroup(olMap, 'mrMapLayerTreeLayerGroup', renderingLayer);
                    //   } catch (error) {
                    //     //@ts-ignore
                    //     throw new Error(error);
                    //   }
                    // }
                    
                    return createdLayer;
                  } catch (error) {
                    //@ts-ignore
                    throw new Error(error);
                  }
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

          <SearchDrawer 
            addDatasetToMapAction={onAddDatasetToMapAction}
            previewDatasetOnMapAction={onPreviewDatasetOnMapAction}
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
