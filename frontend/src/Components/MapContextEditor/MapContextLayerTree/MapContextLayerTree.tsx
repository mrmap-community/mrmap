import { MinusCircleFilled, SettingFilled } from '@ant-design/icons';
import MapUtil from '@terrestris/ol-util/dist/MapUtil/MapUtil';
import { LayerTree } from '@terrestris/react-geo';
import { Button, Dropdown, Menu, Tooltip } from 'antd';
import { getUid } from 'ol';
import { CollectionEvent } from 'ol/Collection';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import OlMap from 'ol/Map';
import { default as React, ReactElement, ReactNode, useEffect, useRef, useState } from 'react';
import './MapContextLayerTree.css';

export const MapContextLayerTree = ({
  id,
  map,
  olLayerGroup
}:{
  id: string,
  map: OlMap,
  olLayerGroup: LayerGroup
}): ReactElement => {

  const [selectedLayer, setSelectedLayer] = useState<BaseLayer>();

  // OpenLayers collection events do not distinguish between remove and a remove followed by an add (move)
  // so we work around this by using two state variables
  const removingLayer = useRef(false);
  const moveRemoveStep = useRef<any>();

  // init: register listeners for layer group
  useEffect(() => {
    if (olLayerGroup) {
      registerLayerListeners(olLayerGroup);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [olLayerGroup]);

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
      if (removingLayer.current) {
        // a normal remove operation
        onLayerRemove(evt);
        removingLayer.current = false;
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
    console.log('onLayerAdd', evt);
    const layer: BaseLayer = evt.element;
    layer.set('parent', evt.target);

    // POST
    // lft/right?
  };

  const onLayerRemove = (evt: CollectionEvent) => {
    console.log('onLayerRemove', evt);
  };

  const onLayerMove = (remove: CollectionEvent, add: CollectionEvent) => {
    console.log('onLayerMove (remove)', remove);
    console.log('onLayerMove (add)', add);
  };

  const onSelect = (selectedKeys: any, info: any) => {
    if (info.selected) {
      setSelectedLayer(MapUtil.getLayerByOlUid(map,info.node.key));
    } else {
      setSelectedLayer(undefined);
    }
  };

  const renderNodeContextMenu = (layer: BaseLayer): ReactElement => {
    const removeLayer = () => {
      // TODO handle nested layers
      removingLayer.current = true;
      olLayerGroup?.getLayers().remove(layer);
    };

    return (
      <Menu
        className='tree-manager-context-menu'>
        <Menu.Item
          onClick={removeLayer}
          icon={<MinusCircleFilled />}
          key='remove-node'
        >
        Delete
        </Menu.Item>
      </Menu>
    );
  };

  const renderNodeTitle = (layer: BaseLayer): ReactNode => {
    return (
      <div className='mapcontext-layertree-node'>
        <div className='mapcontext-layertree-node-title'>{ layer.get('name') }</div>
        <div className='mapcontext-layertree-node-actions'>
          <Dropdown
            overlay={renderNodeContextMenu(layer)}
            trigger={['click']}
          >
            <Tooltip title='Node options'>
              <Button
                type='text'
                icon={<SettingFilled />}
              />
            </Tooltip>
          </Dropdown>
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
      draggable
      allowDrop={allowDrop}
      map={map}
      layerGroup={olLayerGroup}
      onSelect={onSelect}
      selectedKeys={selectedLayer ? [getUid(selectedLayer)] : []}
      nodeTitleRenderer={renderNodeTitle}
    />
  );
};
