import { ExpandOutlined } from '@ant-design/icons/lib/icons';
import { useMap } from '@terrestris/react-geo';
import { Menu } from 'antd';
import { Key } from 'antd/lib/table/interface';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import { transformExtent } from 'ol/proj';
import ImageWMS from 'ol/source/ImageWMS';
import { getUid } from 'ol/util';
import React, { useEffect, useState } from 'react';
import LayerRepo from '../../Repos/LayerRepo';
import { LayerUtils } from '../../Utils/LayerUtils';
import { TreeUtils } from '../../Utils/TreeUtils';
import { TreeFormField } from '../Shared/FormFields/TreeFormField/TreeFormField';
import { TreeNodeType } from '../Shared/FormFields/TreeFormField/TreeFormFieldTypes';
import { LayerTreeProps } from './LayerTreeTypes';

const treeUtils =  new TreeUtils();
const layerUtils =  new LayerUtils();

const layerTreeLayerGroup = new LayerGroup({
  opacity: 1,
  visible: true,
  properties: {
    name: 'mrMapLayerTreeLayerGroup'
  },
  layers: []
});

export const LayerTree = ({
  // map,
  layerGroup = layerTreeLayerGroup,
  asyncTree = false,
  addLayerDispatchAction = () => undefined,
  removeLayerDispatchAction = () => undefined,
  editLayerDispatchAction = () => undefined,
  dragLayerDispatchAction = () => undefined,
  selectLayerDispatchAction = () => undefined,
  layerAttributeForm,
}: LayerTreeProps): JSX.Element => {
  // TODO: all logic to handle layers or interaction between map and layers should be handled here,
  // not to the tree form field component.
  // The tree form field component handles generic logic for a tree, not for the layers or interaction with map.
  // Only change it if you detect aa bug thaat could be traced baack deep to the tree form field
  const map = useMap();
  const [treeData, setTreeData] = useState<TreeNodeType[]>([]);
  
  useEffect(() => {
    const onLayerGroupChange = (e:any) => {
        setTreeData(treeUtils.OlLayerGroupToTreeNodeList(layerGroup));
    };
    const setWMSParams = async(theLayer: ImageLayer<ImageWMS>) => {
      try {
        const source = theLayer.getSource();
        const res = await new LayerRepo().autocompleteInitialValue(theLayer.getProperties().renderingLayer);
        source.setUrl(res.attributes.WMSParams.url);
        source.getParams().LAYERS = res.attributes.WMSParams.layer;
        source.getParams().VERSION = res.attributes.WMSParams.version;
        source.set('serverType',res.attributes.WMSParams.serviceType);
      } catch (error) {
        //@ts-ignore
        throw new Error(error);
      }
    };
    map.addLayer(layerGroup);
    setTreeData(treeUtils.OlLayerGroupToTreeNodeList(layerGroup));
    const allMapLayers = layerUtils.getAllMapLayers(layerGroup);
    allMapLayers.forEach((mapLayer: any) => {
      if(mapLayer instanceof ImageLayer) {
        const src: ImageWMS = mapLayer.getSource();
        // loaded layers from the DB will not have any information regarding the WMS parameters
        // get them here
        // TODO: Maybe they can be included in the initial response
        if(!src.getUrl() && mapLayer.getProperties().renderingLayer){
          setWMSParams(mapLayer);
        }
      }
    });
    layerGroup.on('change', onLayerGroupChange);
    return () => {
      layerGroup.un('change', onLayerGroupChange);
      map.removeLayer(layerGroup);
    };

  }, [layerGroup, map]);

  const onCheckLayer = (checkedKeys: (Key[] | {checked: Key[]; halfChecked: Key[];}), info: any) => {
    const { checked } = info;
    const eventKey = info.node.key;
    const layer = layerUtils.getLayerByMrMapLayerId(map, eventKey);
    setLayerVisibility(layer, checked);
  };

  const setLayerVisibility = (
    layer: BaseLayer | LayerGroup | ImageLayer<ImageWMS> | undefined, 
    visibility: boolean
  ) => {
    // if (!(layer instanceof BaseLayer) || !(layer instanceof LayerGroup)) {
    //   console.error('setLayerVisibility called without layer or layer group.');
    //   return;
    // }
    if(layer) {
      if (layer instanceof LayerGroup) {
        layer.setVisible(visibility);
        layer.getLayers().forEach((subLayer) => {
          setLayerVisibility(subLayer, visibility);
        });
      } else {
        layer.setVisible(visibility);
        // if layer has a parent folder, make it visible too
        if (visibility) {
          const group = layerGroup ? layerGroup : map.getLayerGroup();
          setParentFoldersVisible(group, getUid(layer), group);
        }
      }
    }
  };

  const setParentFoldersVisible = (currentGroup: LayerGroup, olUid: string, masterGroup: LayerGroup) => {
    const items = currentGroup.getLayers().getArray();
    const groups = items.filter(l => l instanceof LayerGroup) as LayerGroup[];
    const match = items.find(i => getUid(i) === olUid);
    if (match) {
      currentGroup.setVisible(true);
      setParentFoldersVisible(masterGroup, getUid(currentGroup), masterGroup);
      return;
    }
    groups.forEach(g => {
      setParentFoldersVisible(g, olUid, masterGroup);
    });
  };

  const onFitToLayerExtent = async(layerId: string) => {
    try {
      const res = await new LayerRepo().autocompleteInitialValue(layerId);
      if(res.attributes.WMSParams.bbox) {
        map.getView().fit(transformExtent(res.attributes.WMSParams.bbox, 'EPSG:4326', 'EPSG:3857'));
      }
    } catch(error) {
      //@ts-ignore
      throw new Error(error);
    }
  };

  const layerActions = (nodeData: TreeNodeType|undefined): any => {
    return (
      <>
      {/* <Divider orientation='right' plain /> */}
      <Menu.Item
        onClick={async() => {
          // fit to layer extent
          const theLayer = layerUtils.getAllMapLayers(layerGroup).find(l => l.get('key') === nodeData?.key);
          if(theLayer && theLayer.get('renderingLayer')) {
            onFitToLayerExtent(theLayer.get('renderingLayer'));
          } else {
            console.warn('Layer not found');
          }
        }}
        icon={<ExpandOutlined/>}
        key='zoom-to-extent'
      >
        Zoom to layer Extent
      </Menu.Item>
      </>
    );
  };

  return (
    <TreeFormField
      title='Layers'
      treeData={treeData}
      asyncTree={asyncTree}
      addNodeDispatchAction={addLayerDispatchAction}
      removeNodeDispatchAction={removeLayerDispatchAction}
      editNodeDispatchAction={editLayerDispatchAction}
      dragNodeDispatchAction={dragLayerDispatchAction}
      checkNodeDispacthAction={onCheckLayer}
      selectNodeDispatchAction={selectLayerDispatchAction}
      draggable
      nodeAttributeForm={layerAttributeForm}
      attributeContainer='drawer'
      contextMenuOnNode
      checkableNodes
      extendedNodeActions={layerActions}
    />
  );
};
