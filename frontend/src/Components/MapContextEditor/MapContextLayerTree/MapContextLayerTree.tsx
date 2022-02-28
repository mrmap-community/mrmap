import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import MapUtil from '@terrestris/ol-util/dist/MapUtil/MapUtil';
import { LayerTree } from '@terrestris/react-geo';
import { LayerTreeProps } from '@terrestris/react-geo/dist/LayerTree/LayerTree';
import { Space, Tooltip } from 'antd';
import { CollectionEvent } from 'ol/Collection';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import OlMap from 'ol/Map';
import { default as React, ReactElement, ReactNode, useEffect, useRef } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import './MapContextLayerTree.css';

export const MapContextLayerTree = ({
  id,
  map,
  olLayerGroup,
  removeLayerInProgress,
  ...passThroughProps
}:{
  id: string,
  map: OlMap,
  olLayerGroup: LayerGroup,
  removeLayerInProgress: React.MutableRefObject<boolean>
} & LayerTreeProps): ReactElement => {

  const moveRemoveStep = useRef<CollectionEvent>();

  // tracks the layer that is currently being added (so we can set the new backend id)
  const addingLayer = useRef<BaseLayer>();

  const [
    addMapContextLayer,
    {
      loading: addMapContextLayerLoading,
      response: addMapContextLayerResponse,
      error: addMapContextLayerError
    }
  ] = useOperationMethod('addMapContextLayer');

  const [
    deleteMapContextLayer,
    {
      loading: deleteMapContextLayerLoading,
      response: deleteMapContextLayerResponse,
      error: deleteMapContextLayerError
    }
  ] = useOperationMethod('deleteMapContextLayer');

  const [
    moveMapContextLayer,
    {
      loading: moveMapContextLayerLoading,
      response: moveMapContextLayerResponse,
      error: moveMapContextLayerError
    }
  ] = useOperationMethod('move_to/api/v1/registry/mapcontextlayers/{id}/move_to/');

  // init: register listeners for layer group
  useEffect(() => {
    if (olLayerGroup) {
      registerLayerListeners(olLayerGroup);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [olLayerGroup]);


  useEffect(() => {
    console.log('addMapContextLayerLoading', addMapContextLayerLoading);
  }, [addMapContextLayerLoading]);
  useEffect(() => {
    if (addMapContextLayerResponse) {
      console.log('addMapContextLayerResponse', addMapContextLayerResponse);
      (addingLayer.current as BaseLayer).set('mapContextLayer', addMapContextLayerResponse.data.data);
      addingLayer.current = undefined;
    }
  }, [addMapContextLayerResponse]);
  useEffect(() => {
    console.log('addMapContextLayerError', addMapContextLayerError);
    addingLayer.current = undefined;
  }, [addMapContextLayerError]);

  useEffect(() => {
    console.log('deleteMapContextLayerLoading', addMapContextLayerLoading);
  }, [deleteMapContextLayerLoading]);
  useEffect(() => {
    console.log('deleteMapContextLayerResponse', deleteMapContextLayerResponse);
  }, [deleteMapContextLayerResponse]);
  useEffect(() => {
    console.log('deleteMapContextLayerError', addMapContextLayerError);
  }, [deleteMapContextLayerError]);

  useEffect(() => {
    console.log('moveMapContextLayerResponse', moveMapContextLayerResponse);
  }, [moveMapContextLayerResponse]);
  useEffect(() => {
    console.log('moveMapContextLayerError', moveMapContextLayerError);
  }, [moveMapContextLayerError]);

  // register listeners for layer group recursively
  const registerLayerListeners = (groupLayer: LayerGroup) => {
    const collection = groupLayer.getLayers();
    collection.on('add', (evt: CollectionEvent) => {
      if (!moveRemoveStep.current) {
        // a normal add operation
        onLayerAdd(evt);
      } else {
        // the second event of a move operation (remove + add)
        onLayerMove(moveRemoveStep.current, evt);
        moveRemoveStep.current = undefined;
      }
    });
    collection.on('remove', (evt: CollectionEvent) => {
      if (removeLayerInProgress.current) {
        // a normal remove operation
        onLayerRemove(evt);
        removeLayerInProgress.current = false;
      } else {
        // the first event of a move operation (remove + add)
        moveRemoveStep.current = evt;
      }
    });
    collection.forEach((layer) => {
      if (layer instanceof LayerGroup) {
        registerLayerListeners(layer);
      }
    });
  };

  const onLayerAdd = (evt: CollectionEvent) => {
    const layer: BaseLayer = evt.element;
    addingLayer.current = layer;
    const targetGroup = MapUtil
      .getAllLayers(map)
      .filter((l: BaseLayer) => l instanceof LayerGroup)
      .filter((l: LayerGroup) => l.getLayers() === evt.target)[0];
    const mapContextLayer = layer.get('mapContextLayer');
    if (!mapContextLayer.relationships) {
      mapContextLayer.relationships = {};
    }
    mapContextLayer.relationships.mapContext = {
      data: {
        type: 'MapContext',
        id: id
      }
    };
    mapContextLayer.relationships.parent = {
      data: {
        type: 'MapContextLayer',
        id: targetGroup.get('mapContextLayer').id
      }
    };
    addMapContextLayer([], {
      data: mapContextLayer
    });
  };

  const onLayerRemove = (evt: CollectionEvent) => {
    const layer: BaseLayer = evt.element;
    deleteMapContextLayer([{ name: 'id', value: layer.get('mapContextLayer').id, in: 'path' }]);
  };

  const onLayerMove = (remove: CollectionEvent, add: CollectionEvent) => {
    console.log('onLayerMove (remove)', remove);
    console.log('onLayerMove (add)', add);
    const movedLayer: BaseLayer = add.element;
    const targetGroup = MapUtil
      .getAllLayers(map)
      .filter((layer: BaseLayer) => layer instanceof LayerGroup)
      .filter((layer: LayerGroup) => layer.getLayers().getArray().includes(movedLayer))[0];
    console.log('movedLayer', movedLayer);
    console.log('target', targetGroup);
    console.log('index', add.index);
    // moveMapContextLayer([{ name: 'id', value: movedLayer.get('id'), in: 'path' }], {
    //   data: {
    //     type: 'MapContextLayer',
    //     attributes: {
    //       target: targetGroup.get('id'),
    //       position: add.index
    //     }
    //   }
    // });
  };

  const renderNodeTitle = (layer: BaseLayer): ReactNode => {
    console.log('Rendering', layer);
    const mapContextLayer = layer.get('mapContextLayer');
    const hasMetadata = mapContextLayer.relationships?.datasetMetadata?.data;
    const hasRenderingLayer = mapContextLayer.relationships?.renderingLayer?.data;
    const hasSelectionLayer = mapContextLayer.relationships?.selectionLayer?.data;
    return (
      <div className='mapcontext-layertree-node'>
        <div className='mapcontext-layertree-node-title'>
          <Space>
            <Tooltip title={hasMetadata ? 'Dataset Metadata is set' : 'Dataset Metadata is not set'}>
              <span className='fa-layers fa-fw'>
                <FontAwesomeIcon icon='file' />
                {
                  !hasMetadata &&
                  (
                    <>
                      <FontAwesomeIcon icon='slash' transform='left-1 down-1' color='white'/>
                      <FontAwesomeIcon icon='slash' />
                    </>
                  )
                }
              </span>
            </Tooltip>
            <Tooltip title={hasRenderingLayer ? 'Rendering layer is set' : 'Rendering layer is not set'} >
              {
                hasRenderingLayer ?
                  <FontAwesomeIcon icon='eye' /> :
                  <FontAwesomeIcon icon='eye-slash' />
              }
            </Tooltip>
            <Tooltip title={hasSelectionLayer ? 'Selection layer is set' : 'Selection layer is not set'} >
              <span className='fa-layers fa-fw'>
                <FontAwesomeIcon icon='crosshairs' />
                {
                  !hasSelectionLayer &&
                  (
                    <>
                      <FontAwesomeIcon icon='slash' transform='left-1 down-1' color='white'/>
                      <FontAwesomeIcon icon='slash' />
                    </>
                  )
                }
              </span>
            </Tooltip>
            { mapContextLayer.attributes.title }
          </Space>
        </div>
      </div>
    );
  };

  const allowDrop = ({ dropNode, dropPosition }: {dropNode: any, dropPosition: any}) => {
    const layer = MapUtil.getLayerByOlUid(map, dropNode.key);
    // dropPosition: -1 (previous sibling)
    // dropPosition: 1 (next sibling)
    // dropPosition: 0 (first child)
    // disable dropping a new child of non-group layer
    return dropPosition !== 0 || layer instanceof LayerGroup;
  };

  return (
    <LayerTree
      disabled={
        addMapContextLayerLoading ||
        deleteMapContextLayerLoading ||
        moveMapContextLayerLoading
      }
      draggable
      allowDrop={allowDrop}
      map={map}
      layerGroup={olLayerGroup}
      nodeTitleRenderer={renderNodeTitle}
      {...passThroughProps}
    />
  );
};
