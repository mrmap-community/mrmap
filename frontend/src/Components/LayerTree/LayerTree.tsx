import { Key } from 'antd/lib/table/interface';
import Collection from 'ol/Collection';
import { EventsKey as OlEventsKey } from 'ol/events';
import GML2 from 'ol/format/GML2';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import OlMap from 'ol/Map';
import OlMapBrowserEvent from 'ol/MapBrowserEvent';
import { unByKey } from 'ol/Observable';
import * as olProj from 'ol/proj';
import ImageWMS from 'ol/source/ImageWMS';
import { getUid } from 'ol/util';
import React, { ReactNode, useEffect, useState } from 'react';
import { JsonApiResponse } from '../../Repos/JsonApiRepo';
import LayerRepo from '../../Repos/LayerRepo';
import { TreeFormField, TreeNodeType } from '../Shared/FormFields/TreeFormField/TreeFormField';

type OlWMSServerType = 'ESRI' | 'GEOSERVER' | 'MAPSERVER' | 'QGIS';

export interface CreateLayerOpts {
  url: string;
  version: '1.1.0' | '1.1.1' | '1.3.0';
  format: 'image/jpeg' | 'image/png';
  layers: string;
  visible: boolean;
  serverType: OlWMSServerType;
  mrMapLayerId?: string | number;
  legendUrl: string;
  title: string;
  name?: string;
  properties: Record<string, string>;
  extent?: any[]
}

interface LayerTreeProps {
  map: OlMap
  layerGroup?: LayerGroup;
  asyncTree?: boolean;
  addLayerDispatchAction?:(
    nodeAttributes: any,
    newNodeParent?: string | number | null | undefined) =>
    Promise<JsonApiResponse> | void;
  removeLayerDispatchAction?: (nodeToRemove: TreeNodeType) => Promise<JsonApiResponse> | void;
  editLayerDispatchAction?: (nodeId:number|string, nodeAttributesToUpdate: any) => Promise<JsonApiResponse> | void;
  dragLayerDispatchAction?: (nodeBeingDraggedInfo: any) => Promise<JsonApiResponse> | void;
  selectLayerDispatchAction?: (selectedKeys: Key[], info: any) => void;
  layerAttributeForm?: ReactNode;
}

 export const getWMSFeatureInfoUrl = (olMap: OlMap, layerSource: ImageWMS, coordinates: [number, number])
 : (string | undefined) => {
 // all getFeatureInfo operation will be handled in EPSG:3857
 const featureInfoUrl: string | undefined = layerSource
     .getFeatureInfoUrl(
         coordinates,
         //@ts-ignore
         olMap.getView().getResolution(),
         'EPSG:3857',
         {
             'INFO_FORMAT': 'application/vnd.ogc.gml'
         }
     );
 return featureInfoUrl;
};

// const onFetchingAttributesStart = () => {
//   setIsLoading(true);
//   map.getTargetElement().style.cursor = 'wait';
// };

const getFeatureAttributes = (olMap: OlMap, event: OlMapBrowserEvent<any>) => {
  // setDidClickOnMap(true);
  // setLayerFeatures({});
  console.log(event);
  const promises = [];
  const clickedPixel = olMap.getEventPixel(event.originalEvent);
  const clickedCoordinate = olMap.getCoordinateFromPixel(clickedPixel);

  // WARNING: The coordinates are directly transformed from the canvas pixel. This means that when the user
  // clicks on the center representation of the map in the canvas, the coordinates are correct according to the
  // current projection. HOWEVER... if the user zooms out, and zooms in again to another representation area of
  // the map within the canvas, the coordinates are not correct according to real world coordinates, rather they
  // are referenced according to the canvas axis. To fix this, we need to convert the derived coordinates from
  // the pixel using the OL method toLonLat().
  const realCoordinates = olProj.toLonLat(clickedCoordinate);
  // Altought it is said in the OL documentation that this coordinates are given by default in the map projection,
  // they are actually given in EPSG:4326 (even if specified). This might be a bug that will be investigated and
  // reported. Since we need the coordinates in EPSG:3857, we need to also get the proper transformation.

  // get the coordinates in EPSG:3857 (our default map projection)
  const transformedClickedCoordinate = olProj
      .transform(realCoordinates, 'EPSG:4326', olMap.getView().getProjection());

  const coords = transformedClickedCoordinate as [number, number];

  olMap.forEachLayerAtPixel(
      clickedPixel,
      (layer: ImageLayer<ImageWMS>) => {
          // gets the layer source
          const layerSource: ImageWMS = layer.getSource();
          layerSource.set('crossOrigin', 'gis.mffjiv.rlp.de');
          // TODO: add support for vector source

          if (layerSource instanceof ImageWMS) {
            const featureInfoUrl = getWMSFeatureInfoUrl(olMap, layerSource, coords);
            if (featureInfoUrl) {
              resolveWMSPromise(featureInfoUrl);
            }
          }

          return false;
      },
      { hitTolerance: 5 }
  );
};

const resolveWMSPromise = async(url: string) => {
    try {
      const response = await fetch(url,
        { 
          method: 'GET', 
          mode: 'cors',
          //@ts-ignore
          headers: { 
            'Content-Type': 'application/vnd.ogc.gml',
          }
        } 
      );
      const textRes = await response.text();
      const format = new GML2();
      const fc = format.readFeatures(textRes);
      fc.forEach((feature: any) => {
        if (Object.getOwnPropertyNames(feature).length > 0) {
          // TODO where to render the properties?
          console.log(feature.getProperties());
        }
      });
    } catch (error) {
      //@ts-ignore
      throw new Error(error);
    }

};

export const getAllMapLayers = (collection: OlMap | LayerGroup): (LayerGroup | BaseLayer | ImageLayer<ImageWMS>)[] => {
  if (!(collection instanceof OlMap) && !(collection instanceof LayerGroup)) {
    console.error('Input parameter collection must be from type `ol.Map` or `ol.layer.Group`.');
    return [];
  }

  const layers = collection.getLayers().getArray();
  const allLayers:any = [];

  layers.forEach((layer) => {
    if (layer instanceof LayerGroup) {
      getAllMapLayers(layer).forEach((layeri:any) => allLayers.push(layeri));
    }
    allLayers.push(layer);
  });
  
  return allLayers;
};

export const createMrMapOlWMSLayer = (opts: CreateLayerOpts): ImageLayer<ImageWMS> => {
  const olLayerSource = new ImageWMS({
    url: opts.url,
    params: {
      'LAYERS': opts.layers,
      'VERSION': opts.version,
      'FORMAT': opts.format,
      'TRANSPARENT': true
    },
    serverType: opts.serverType,
    // crossOrigin: 'anonymous',
    // //crossOrigin: 'Anonymous',
  });

  const olWMSLayer = new ImageLayer({
    source: olLayerSource,
    visible: opts.visible,
  });

  olWMSLayer.setProperties({
    mrMapLayerId: opts.mrMapLayerId,
    legendUrl: opts.legendUrl,
    title: opts.title,
    name: opts.name,
    extent: opts.extent,
    ...opts.properties
  });

  return olWMSLayer;
};

export const getLayerByMrMapLayerId= (
  collection: OlMap | LayerGroup, 
  id: string | number
): LayerGroup | BaseLayer | ImageLayer<ImageWMS> | undefined => {
  const layersToSearch = getAllMapLayers(collection);
  return layersToSearch.find((layer:any) => String(layer.getProperties().mrMapLayerId) === String(id));
};

export const getLayerGroupByName = (
  collection: OlMap | LayerGroup, 
  layerGroupName: string
): LayerGroup | undefined => {
  const requiredLayerGroup = getAllMapLayers(collection)
    .find((layer:any) => layer.getProperties().name === layerGroupName);
  if(requiredLayerGroup instanceof LayerGroup){
    return requiredLayerGroup;
  }
};

export const getLayerGroupByMrMapLayerId = (
  collection: OlMap | LayerGroup, 
  id: string|number
): LayerGroup | undefined => {
  const allMapLayers = getAllMapLayers(collection);
  const requiredLayerGroup = allMapLayers
    .find((layer:any) => layer.getProperties().mrMapLayerId === id);
  if(requiredLayerGroup) {
    if(requiredLayerGroup instanceof LayerGroup) {
      return requiredLayerGroup;
    } else {
      if(requiredLayerGroup.getProperties().parent) {
        const parentLayer = allMapLayers
          .find((layer:any) => layer.getProperties().mrMapLayerId === requiredLayerGroup.getProperties().parent);
        if(parentLayer && parentLayer instanceof LayerGroup) {
          return parentLayer;
        }
      } else {
        if (collection instanceof LayerGroup) {
          return collection;
        }
        if (collection instanceof OlMap) {
          collection.getLayerGroup();
        }
      }
    }
  } else {
    if (collection instanceof LayerGroup) {
      return collection;
    }
    if (collection instanceof OlMap) {
      collection.getLayerGroup();
    }
  }
};

export const addLayerToGroupByName = (
  collection: OlMap | LayerGroup, 
  layerGroupName: string, 
  layerToAdd: LayerGroup | BaseLayer
): void => {
  const layerGroup: LayerGroup | undefined = getLayerGroupByName(collection, layerGroupName);
  if(layerGroup) {
    const layerArray = layerGroup.getLayers().getArray();
    layerArray.push(layerToAdd);
    layerGroup.setLayers(new Collection(layerArray));
  } else {
    console.warn(`No layer group with the name ${layerGroupName}, was found on the map`);
  }
};

export const addLayerToGroupByMrMapLayerId = (
  collection: OlMap | LayerGroup, 
  id: string | number, 
  layerToAdd: LayerGroup | BaseLayer
): void => {
  const layerGroup: LayerGroup | undefined = getLayerGroupByMrMapLayerId(collection, id);
  if(layerGroup) {
    const layerArray = layerGroup.getLayers().getArray();
    layerArray.push(layerToAdd);
    layerGroup.setLayers(new Collection(layerArray));
  } else {
    console.warn(`No layer group with the id ${id}, was found on the map`);
  }
};

export const OlLayerGroupToTreeNodeList = (layerGroup: LayerGroup): TreeNodeType[] => {
  return layerGroup.getLayers().getArray().map((layer: LayerGroup | BaseLayer) => {
    const node: any = {
      key: layer.getProperties().mrMapLayerId,
      title: layer.getProperties().title,
      parent: layer.getProperties().parent,
      properties: layer.getProperties(),
      isLeaf: true,
      expanded: layer instanceof LayerGroup,
      children: []
    }; 
    if (layer instanceof LayerGroup ) {
      node.children = OlLayerGroupToTreeNodeList(layer);
      node.isLeaf = false;
    }
    return node;
  });
};

export const OlLayerToTreeNode = (layer: BaseLayer): TreeNodeType => {
  const node: any = {
    key: layer.getProperties().mrMapLayerId,
    title: layer.getProperties().title,
    parent: layer.getProperties().parent,
    properties: layer.getProperties(),
    isLeaf: true,
    expanded: layer instanceof LayerGroup,
    children: []
  }; 
  return node;
};

const layerTreeLayerGroup = new LayerGroup({
  opacity: 1,
  visible: true,
  properties: {
    name: 'mrMapLayerTreeLayerGroup'
  },
  layers: []
});

export const LayerTree = ({
  map,
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

  const olListenerKeys: (OlEventsKey[]) = [];

  

  const [treeData, setTreeData] = useState<TreeNodeType[]>([]);
  
  useEffect(() => {
    const onLayerGroupChange = (e:any) => {
        setTreeData(OlLayerGroupToTreeNodeList(layerGroup));
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
    setTreeData(OlLayerGroupToTreeNodeList(layerGroup));
    const allMapLayers = getAllMapLayers(layerGroup);
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

  const registerMapClickListener = (olMap: OlMap) => {
    const mapClickEventKey = olMap.on('singleclick', (event) => getFeatureAttributes(map, event));
    olListenerKeys.push(mapClickEventKey);
};

  useEffect(() => {
    
    registerMapClickListener(map);
    return () => {
      // unregister the listener
      unByKey(olListenerKeys);
    };
  }, [olListenerKeys]);

   

  const onCheckLayer = (checkedKeys: (Key[] | {checked: Key[]; halfChecked: Key[];}), info: any) => {
    const { checked } = info;
    const eventKey = info.node.key;
    const layer = getLayerByMrMapLayerId(map, eventKey);
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

  // const onAddNewLayer = (nodeAttributes: any, newNodeParent?: string | number | null | undefined, layer: any) =>  {
  //   addLayerDispatchAction(nodeAttributes, newNodeParent);
  //   addLayerToGroup(map, layerGroup.getProperties().name, layer);
  // };

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
    />
  );
};
