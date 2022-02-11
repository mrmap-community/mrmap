import { SyncOutlined } from '@ant-design/icons';
import Collection from 'ol/Collection';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import ImageWMS from 'ol/source/ImageWMS';
import React, { ReactElement, useEffect, useState } from 'react';
import { useParams } from 'react-router';
import { operation, unpage } from '../../Repos/JsonApi';
import { LayerUtils } from '../../Utils/LayerUtils';
import { olMap } from '../../Utils/MapUtils';
import { MPTTJsonApiTreeNodeType, TreeNodeType } from '../Shared/TreeManager/TreeManagerTypes';
import { CreateLayerOpts } from '../TheMap/LayerManager/LayerManagerTypes';
import { TheMap } from '../TheMap/TheMap';
import { AreaDigitizeToolbar } from './AreaDigitizeToolbar/AreaDigitizeToolbar';
import { RulesDrawer } from './RulesDrawer/RulesDrawer';
import './WmsSecuritySettings.css';

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
        scaleMin: element.attributes.scaleMin,
        scaleMax: element.attributes.scaleMax,
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
  // only when rule editing is active, layers are selectable and area digitizing is possible
  const [isRuleEditingActive, setIsRuleEditingActive] = useState<boolean>(false);

  useEffect(() => {
    if (wmsId) {
      setIsLoading(true);
      const fetchWmsAndLayers = async () => {
        try {
          let jsonApiResponse = await operation(
            'retrieve/api/v1/registry/wms/{id}/',
            [{
              in: 'path',
              name: 'id',
              value: String(wmsId),
            },
            {
              in: 'query',
              name: 'include',
              value: 'operationUrls'
            }]
          );          
          const getMapUrl = jsonApiResponse.data.included.filter((opUrl:any) => {
            return opUrl.attributes.method === 'Get' && opUrl.attributes.operation === 'GetMap';
          }).map ((opUrl:any) => {
            return opUrl.attributes.url;
          }).reduce ( 
            (acc:string, curr:string) => curr, null
          );
          const wmsAttrs = jsonApiResponse.data.data.attributes;
          const wmsVersion = wmsAttrs.version;

          jsonApiResponse = await operation(
            'List/api/v1/registry/wms/{parent_lookup_service}/layers/',
            [
              {
                in: 'path',
                name: 'parent_lookup_service',
                value: String(wmsId),
              },
              {
                in: 'query',
                name: 'fields[Layer]',
                value: 'title,identifier,parent'
              },
              {
                in: 'query',
                name: 'page[size]',
                value: '1000'
              },              
            ]
          );
          jsonApiResponse = await unpage(jsonApiResponse);

          // convert the WMS layers coming from the server to a compatible tree node list
          const _initLayerTreeData = wmsLayersToOlLayerGroup(jsonApiResponse.data?.data, getMapUrl, wmsVersion);
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
        } finally {
          setIsLoading(false);
        }
      };      
      fetchWmsAndLayers();
    }
  }, [wmsId]);

  useEffect(() => {
    if (!isRuleEditingActive) {
      setSelectedLayerIds([]);
    }
  }, [isRuleEditingActive]);

  if(isLoading) {
    return (<SyncOutlined spin />);
  }

  const selectLayersAndSublayers = ((ids:string[]) => {
    olMap.getLayers().forEach (layer => {
      if (layer.getProperties().title === 'mrMapWmsSecurityLayers') {
        const layerIds: string[] = [];
        const collectLayersAndSubLayers = (layer: BaseLayer, include: boolean) => {
          include = include || ids.includes(layer.getProperties()['layerId']);
          if (layer instanceof LayerGroup) {
            layer.getLayers().forEach ((child) => {
              collectLayersAndSubLayers(child, include);
            }); 
          } 
          include && layerIds.push(layer.getProperties()['layerId']);
        };
        collectLayersAndSubLayers(layer, false);
        setSelectedLayerIds(layerIds);
      }
    });
  });

  return (
    <>
      <div className='map-context'>
        <TheMap
          showLayerManager
          allowMultipleLayerSelection
          selectLayerDispatchAction={(selectedKeys, info) => { 
            isRuleEditingActive && selectLayersAndSublayers(selectedKeys as string[]);
          }}
          layerGroupName='mrMapWmsSecurityLayers'
          initLayerTreeData={initLayerTreeData}
          initExpandedLayerIds={nonLeafLayerIds}
          layerAttributeForm={(<h1>Placeholder</h1>)}
          selectedLayerIds={selectedLayerIds}
          draggable={false}
        />
        { 
          wmsId && 
            <RulesDrawer 
              wmsId={wmsId}
              selectedLayerIds={selectedLayerIds}
              setSelectedLayerIds={selectLayersAndSublayers}
              setIsRuleEditingActive={setIsRuleEditingActive}
            /> 
        }
        {
          olMap && isRuleEditingActive && <AreaDigitizeToolbar map={olMap} /> 
        }
      </div>
    </>
  );
};
