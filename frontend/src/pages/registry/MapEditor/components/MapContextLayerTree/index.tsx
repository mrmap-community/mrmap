import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import MapUtil from '@terrestris/ol-util/dist/MapUtil/MapUtil';
import { LayerTree } from '@terrestris/react-geo';
import type { LayerTreeProps } from '@terrestris/react-geo/dist/LayerTree/LayerTree';
import { Space, Tooltip } from 'antd';
import { getUid } from 'ol';
import type { CollectionEvent } from 'ol/Collection';
import type { EventsKey } from 'ol/events';
import type BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import type OlMap from 'ol/Map';
import { unByKey } from 'ol/Observable';
import type { Key, ReactElement, ReactNode } from 'react';
import { default as React, useEffect, useRef, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import './index.css';

const renderNodeTitle = (layer: BaseLayer): ReactNode => {
  const mapContextLayer = layer.get('mapContextLayer');
  const hasMetadata = mapContextLayer.relationships?.datasetMetadata?.data;
  const hasRenderingLayer = mapContextLayer.relationships?.renderingLayer?.data;
  const hasSelectionLayer = mapContextLayer.relationships?.selectionLayer?.data;
  return (
    <div className="mapcontext-layertree-node">
      <div className="mapcontext-layertree-node-title">
        <Space>
          <Tooltip title={hasMetadata ? 'Dataset Metadata is set' : 'Dataset Metadata is not set'}>
            <span className="fa-layers fa-fw">
              <FontAwesomeIcon icon="file" />
              {!hasMetadata && (
                <>
                  <FontAwesomeIcon icon="slash" transform="left-1 down-1" color="white" />
                  <FontAwesomeIcon icon="slash" />
                </>
              )}
            </span>
          </Tooltip>
          <Tooltip
            title={hasRenderingLayer ? 'Rendering layer is set' : 'Rendering layer is not set'}
          >
            {hasRenderingLayer ? (
              <FontAwesomeIcon icon="eye" />
            ) : (
              <FontAwesomeIcon icon="eye-slash" />
            )}
          </Tooltip>
          <Tooltip
            title={hasSelectionLayer ? 'Selection layer is set' : 'Selection layer is not set'}
          >
            <span className="fa-layers fa-fw">
              <FontAwesomeIcon icon="crosshairs" />
              {!hasSelectionLayer && (
                <>
                  <FontAwesomeIcon icon="slash" transform="left-1 down-1" color="white" />
                  <FontAwesomeIcon icon="slash" />
                </>
              )}
            </span>
          </Tooltip>
          {mapContextLayer.attributes.title}
        </Space>
      </div>
    </div>
  );
};

/**
 * Layer tree that uses a (possibly nested) layer hierarchy from a given layer group.
 *
 * It watches the layer hierarchy for changes, updates the tree view and automatically synchronizes
 * changes to the MapContextLayer entities stored in the JSON:API backend.
 */
const MapContextLayerTree = ({
  mapContextId,
  map,
  olLayerGroup,
  removeLayerInProgress,
  ...passThroughProps
}: {
  /** Id of the persistent MapContext entity. */
  mapContextId: string;
  /** The OpenLayers map the tree interacts with. */
  map: OlMap;
  /** A LayerGroup the Tree should handle. */
  olLayerGroup: LayerGroup;
  /** True, if a remove operation has been invoked (needed to distinguish between remove and move operations). */
  removeLayerInProgress: React.MutableRefObject<boolean>;
} & LayerTreeProps): ReactElement => {
  // layers that we watch for changes
  const [watchedLayers, setWatchedLayers] = useState<BaseLayer[]>([]);

  // tracks the OpenLayer layer that is currently being added/updated via a backend call, so we can attach
  // the new/updated MapContextLayer to it later
  const layerBeingPersisted = useRef<BaseLayer>();

  // setNodeTitleRenderer is used to trigger node re-rendering when a layer changes (e.g. title)
  // this is a bit of a workaround, maybe a better solution can be added to react-geo LayerTree
  const [nodeTitleRenderer, setNodeTitleRenderer] = useState<any>(() => renderNodeTitle);

  const [expandedOlUids, setExpandedOlUids] = useState<string[] | Key[]>([]);

  const [
    addMapContextLayer,
    {
      loading: addMapContextLayerLoading,
      response: addMapContextLayerResponse,
      error: addMapContextLayerError,
    },
  ] = useOperationMethod('addMapContextLayer');

  const [
    deleteMapContextLayer,
    {
      loading: deleteMapContextLayerLoading,
      response: deleteMapContextLayerResponse,
      error: deleteMapContextLayerError,
    },
  ] = useOperationMethod('deleteMapContextLayer');

  const [
    updateMapContextLayer,
    {
      loading: updateMapContextLayerLoading,
      response: updateMapContextLayerResponse,
      error: updateMapContextLayerError,
    },
  ] = useOperationMethod('updateMapContextLayer');

  // init/update: initialize layers to watch
  useEffect(() => {
    setWatchedLayers([olLayerGroup, ...MapUtil.getAllLayers(olLayerGroup)]);
    setExpandedOlUids([
      getUid(olLayerGroup),
      ...MapUtil.getAllLayers(olLayerGroup).map((layer) => getUid(layer)),
    ]);
  }, [olLayerGroup]);

  // init/update: ensure all watched layers have listeners
  useEffect(() => {
    // OpenLayers collection events can not distinguish between remove and a remove followed by an add (move)
    // so we track the remove step of a move operation ourselves
    let moveRemoveStep: CollectionEvent | undefined;
    const olListenerKeys: EventsKey[] = [];
    const registerListeners = (baseLayer: BaseLayer) => {
      const onLayerAdd = (evt: CollectionEvent) => {
        const layer: BaseLayer = evt.element;
        layerBeingPersisted.current = layer;
        // TODO just use event for target?
        const targetGroup = MapUtil.getAllLayers(map)
          .filter((l: BaseLayer) => l instanceof LayerGroup)
          .filter((l: any) => l.getLayers() === evt.target)[0];
        const mapContextLayer = layer.get('mapContextLayer');
        if (!mapContextLayer.relationships) {
          mapContextLayer.relationships = {};
        }
        mapContextLayer.relationships.mapContext = {
          data: {
            type: 'MapContext',
            id: mapContextId,
          },
        };
        mapContextLayer.relationships.parent = {
          data: {
            type: 'MapContextLayer',
            id: targetGroup.get('mapContextLayer').id,
          },
        };
        addMapContextLayer([], {
          data: mapContextLayer,
        });
      };

      const onLayerRemove = (evt: CollectionEvent) => {
        const layer: BaseLayer = evt.element;
        deleteMapContextLayer([{ name: 'id', value: layer.get('mapContextLayer').id, in: 'path' }]);
      };

      const onLayerMove = (remove: CollectionEvent, add: CollectionEvent) => {
        const movedLayer: BaseLayer = add.element;
        layerBeingPersisted.current = movedLayer;
        const targetGroup = MapUtil.getAllLayers(map)
          .filter((layer: BaseLayer) => layer instanceof LayerGroup)
          .filter((layer: any) => layer.getLayers().getArray().includes(movedLayer))[0];
        let position = add.index;
        if (remove.target === add.target) {
          // a move in the same group, we may need to adjust the index
          if (add.index > remove.index) {
            position++;
          }
        }
        updateMapContextLayer(
          [{ name: 'id', value: movedLayer.get('mapContextLayer').id, in: 'path' }],
          {
            data: {
              type: 'MapContextLayer',
              id: movedLayer.get('mapContextLayer').id,
              attributes: {
                position: position,
              },
              relationships: {
                parent: {
                  data: {
                    type: 'MapContextLayer',
                    id: targetGroup.get('mapContextLayer').id,
                  },
                },
              },
            },
          },
        );
      };

      if (baseLayer instanceof LayerGroup) {
        const collection = (baseLayer as LayerGroup).getLayers();
        olListenerKeys.push(
          collection.on('add', (evt: CollectionEvent) => {
            if (!moveRemoveStep) {
              // a normal add operation
              onLayerAdd(evt);
            } else {
              // the second event of a move operation (remove + add)
              onLayerMove(moveRemoveStep, evt);
              moveRemoveStep = undefined;
            }
          }),
        );
        olListenerKeys.push(
          collection.on('remove', (evt: CollectionEvent) => {
            if (removeLayerInProgress.current) {
              // a normal remove operation
              onLayerRemove(evt);
              removeLayerInProgress.current = false;
            } else {
              // the first event of a move operation (remove + add)
              moveRemoveStep = evt;
            }
          }),
        );
      }

      olListenerKeys.push(
        baseLayer.on('propertychange', (evt: any) => {
          console.log('property change detected', evt);
          setNodeTitleRenderer(() => (layer: BaseLayer) => renderNodeTitle(layer));
        }),
      );
    };
    watchedLayers.forEach((layer) => {
      registerListeners(layer);
    });
    return () => {
      // add hook to remove listeners
      unByKey(olListenerKeys);
    };
  }, [
    watchedLayers,
    mapContextId,
    map,
    removeLayerInProgress,
    addMapContextLayer,
    deleteMapContextLayer,
    updateMapContextLayer,
  ]);

  // addMapContext backend call succeeded
  useEffect(() => {
    if (addMapContextLayerResponse) {
      (layerBeingPersisted.current as BaseLayer).set(
        'mapContextLayer',
        addMapContextLayerResponse.data.data,
      );
      layerBeingPersisted.current = undefined;
      const nestedGroups = MapUtil.getAllLayers(olLayerGroup).filter(
        (l: BaseLayer) => l instanceof LayerGroup,
      );
      setWatchedLayers([olLayerGroup, ...nestedGroups]);
    }
  }, [addMapContextLayerResponse, setWatchedLayers, olLayerGroup]);

  // deleteMapContext backend call succeeded
  useEffect(() => {
    if (deleteMapContextLayerResponse) {
      const nestedGroups = MapUtil.getAllLayers(olLayerGroup).filter(
        (l: BaseLayer) => l instanceof LayerGroup,
      );
      setWatchedLayers([olLayerGroup, ...nestedGroups]);
    }
  }, [deleteMapContextLayerResponse, setWatchedLayers, olLayerGroup]);

  // updateMapContext backend call succeeded
  useEffect(() => {
    if (updateMapContextLayerResponse) {
      (layerBeingPersisted.current as BaseLayer).set(
        'mapContextLayer',
        updateMapContextLayerResponse.data.data,
      );
      layerBeingPersisted.current = undefined;
    }
  }, [updateMapContextLayerResponse]);

  useEffect(() => {
    layerBeingPersisted.current = undefined;
    // TODO warning for user
  }, [addMapContextLayerError, deleteMapContextLayerError, updateMapContextLayerError]);

  const allowDrop = ({ dropNode, dropPosition }: { dropNode: any; dropPosition: any }) => {
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
        addMapContextLayerLoading || deleteMapContextLayerLoading || updateMapContextLayerLoading
      }
      draggable
      allowDrop={allowDrop}
      map={map}
      layerGroup={olLayerGroup}
      nodeTitleRenderer={nodeTitleRenderer}
      expandedKeys={expandedOlUids}
      onExpand={(expandedKeys) => setExpandedOlUids(expandedKeys)}
      {...passThroughProps}
    />
  );
};

export default MapContextLayerTree;
