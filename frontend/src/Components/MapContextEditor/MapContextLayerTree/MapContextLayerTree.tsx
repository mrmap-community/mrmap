import MapUtil from '@terrestris/ol-util/dist/MapUtil/MapUtil';
import { LayerTree } from '@terrestris/react-geo';
import { LayerTreeProps } from '@terrestris/react-geo/dist/LayerTree/LayerTree';
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
      (addingLayer.current as BaseLayer).set('id', addMapContextLayerResponse.data.data.id);
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
    const relationships = {
      mapContext: {
        data: {
          type: 'MapContext',
          id: id
        }
      }
    };
    addMapContextLayer([], {
      data: {
        type: 'MapContextLayer',
        attributes: {
          title: layer.get('name')
        },
        relationships: {
          ...relationships
        }
      }
    });
  };

  const onLayerRemove = (evt: CollectionEvent) => {
    console.log('onLayerRemove', evt);
    const layer: BaseLayer = evt.element;
    deleteMapContextLayer([{ name: 'id', value: layer.get('id'), in: 'path' }]);
  };

  const onLayerMove = (remove: CollectionEvent, add: CollectionEvent) => {
    console.log('onLayerMove (remove)', remove);
    console.log('onLayerMove (add)', add);
  };

  const renderNodeTitle = (layer: BaseLayer): ReactNode => {
    return (
      <div className='mapcontext-layertree-node'>
        <div className='mapcontext-layertree-node-title'>{ layer.get('name') }</div>
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
      disabled={addMapContextLayerLoading || deleteMapContextLayerLoading}
      draggable
      allowDrop={allowDrop}
      map={map}
      layerGroup={olLayerGroup}
      nodeTitleRenderer={renderNodeTitle}
      {...passThroughProps}
    />
  );
};
