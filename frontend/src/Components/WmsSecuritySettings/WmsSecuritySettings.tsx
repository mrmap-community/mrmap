import { SyncOutlined } from '@ant-design/icons';
import { MapContext as ReactGeoMapContext } from '@terrestris/react-geo';
import Collection from 'ol/Collection';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import ImageWMS from 'ol/source/ImageWMS';
import React, { ReactElement, useEffect, useState } from 'react';
import { useParams } from 'react-router';
import WmsRepo from '../../Repos/WmsRepo';
import { LayerUtils } from '../../Utils/LayerUtils';
import { MPTTJsonApiTreeNodeType, TreeNodeType } from '../Shared/TreeManager/TreeManagerTypes';
import { CreateLayerOpts } from '../TheMap/LayerManager/LayerManagerTypes';
import { olMap, TheMap } from '../TheMap/TheMap';
import { RulesDrawer } from './RulesDrawer/RulesDrawer';
import './WmsSecuritySettings.css';

const wmsRepo = new WmsRepo();
const layerUtils = new LayerUtils();

function wmsLayersToTreeNodeList(list:any[]):TreeNodeType[] {
  const roots:TreeNodeType[] = [];

  // initialize children on the list element
  list = list.map((element: any) => ({ ...element, children: [] }));

  list.map((element) => {
    const node: TreeNodeType = {
      key: element.id,
      title: element.attributes.title,
      parent: element.relationships.parent.data?.id,
      children: element.children || [],
      isLeaf: element.children && element.children.length === 0,
      properties: {
        origId: element.attributes.identifier,
        title: element.attributes.title, // yes, title is repeated
        scaleMin: element.attributes.scale_min,
        scaleMax: element.attributes.scale_max,
      }
    };

    if (node.parent) {
      const parentNode: MPTTJsonApiTreeNodeType | undefined = list.find((el:any) => el.id === node.parent);
      if (parentNode) {
        list[list.indexOf(parentNode)].children?.push(node);
      }
    } else {
      roots.push(node);
    }
    return element;
  });

  return roots;
}

function TreeNodeListToOlLayerGroup(list: TreeNodeType[], 
  getMapUrl:string, wmsVersion:string): Collection<LayerGroup | ImageLayer<ImageWMS>> {
  const layerList = list.map((node: TreeNodeType) => {

    if (node.children.length > 0) {
      const layerGroupOpts = {
        opacity: 1,
        visible: false,
        properties: {
          title: node.properties.title,
          description: node.properties.description,
          parent: node.parent,
          key: node.key,
          layerId: node.key
        },
        layers: TreeNodeListToOlLayerGroup(node.children, getMapUrl, wmsVersion)
      };
      return new LayerGroup(layerGroupOpts);
    } 

    if(node.children.length === 0) {
      const layerOpts: CreateLayerOpts = {
        url: getMapUrl,
        version: wmsVersion as any,
        format: 'image/png',
        layers: node.properties.origId,
        serverType: 'MAPSERVER',
        visible: false,
        legendUrl: '',
        title: node.properties.title,
        description: node.properties.description,
        layerId: node.key,
        properties: {
          ...node.properties,
          parent: node.parent,
          key: node.key,
        }
      };
      return layerUtils.createMrMapOlWMSLayer(layerOpts);
    }
    return new LayerGroup();
  });
  return new Collection(layerList);
}

function wmsLayersToOlLayerGroup(list:MPTTJsonApiTreeNodeType[], 
  getMapUrl:string, wmsVersion:string): Collection<LayerGroup | BaseLayer> {
  if(list) {
    const treeNodeList = wmsLayersToTreeNodeList(list);
    const layerGroupList = TreeNodeListToOlLayerGroup(treeNodeList, getMapUrl, wmsVersion);
    return layerGroupList;
  }
  return new Collection();
}

export const WmsSecuritySettings = (): ReactElement => {

  const { wmsId } = useParams();
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [selectedLayerIds, setSelectedLayerIds] = useState<string[]>([]);
  const [initLayerTreeData, setInitLayerTreeData] = useState<Collection<any>>(new Collection());
  const [nonLeafLayerIds, setNonLeafLayerIds] = useState<string[]>([]);

  useEffect(() => {
    if (wmsId) {
      setIsLoading(true);
      const fetchWmsAndLayers = async () => {
        try {
          const jsonApiWmsWithOpUrls = await wmsRepo.get(String(wmsId)) as any;
          const getMapUrl = jsonApiWmsWithOpUrls.data.included.filter((opUrl:any) => {
            return opUrl.attributes.method === 'Get' && opUrl.attributes.operation === 'GetMap';
          }).map ((opUrl:any) => {
            return opUrl.attributes.url;
          }).reduce ( 
            (acc:string, curr:string) => curr, null
          );
          const wmsAttrs = jsonApiWmsWithOpUrls.data.data.attributes;
          const wmsVersion = wmsAttrs.version;
          const response = await wmsRepo.getAllLayers(String(wmsId));

          // convert the WMS layers coming from the server to a compatible tree node list
          const _initLayerTreeData = wmsLayersToOlLayerGroup((response as any).data?.data, getMapUrl, wmsVersion);
          const layerIds: string[] = [];
          const collectNonLeafLayers = (layer: BaseLayer) => {
            if (layer instanceof LayerGroup) {
              layerIds.push(layer.getProperties()['layerId']);
              layer.getLayers().forEach ((child) => {
                collectNonLeafLayers(child);
              }); 
            } 
          };
          _initLayerTreeData.forEach ( (layer) => {
            collectNonLeafLayers(layer);
          });
          setInitLayerTreeData(_initLayerTreeData);
          setNonLeafLayerIds(layerIds);
        } catch (error) {
          // @ts-ignore
          throw new Error(error);
        } finally {
          setIsLoading(false);
        }
      };      
      fetchWmsAndLayers();
    }
  }, [wmsId]);

  if(isLoading) {
    return (<SyncOutlined spin />);
  }

  return (
    <>
      <div className='map-context'>
        <ReactGeoMapContext.Provider value={olMap}>
          <TheMap
            showLayerManager
            allowMultipleLayerSelection
            selectLayerDispatchAction={(selectedKeys, info) => { 
              setSelectedLayerIds(selectedKeys as string[]);
            }}
            layerGroupName='mrMapWmsSecurityLayers'
            initLayerTreeData={initLayerTreeData}
            initExpandedLayerIds={nonLeafLayerIds}
            layerAttributeForm={(<h1>Placeholder</h1>)}
            selectedLayerIds={selectedLayerIds}
          />
          { 
            wmsId && 
            <RulesDrawer 
              wmsId={wmsId}
              selectedLayerIds={selectedLayerIds}
              setSelectedLayerIds={ (ids:string[]) => { setSelectedLayerIds(ids); } }
            /> 
          }
        </ReactGeoMapContext.Provider>
      </div>
    </>
  );
};
