import { SyncOutlined } from '@ant-design/icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { MapContext as ReactGeoMapContext } from '@terrestris/react-geo';
import Collection from 'ol/Collection';
import React, { ReactElement, useEffect, useState } from 'react';
import { useParams } from 'react-router';
import WmsRepo from '../../Repos/WmsRepo';
import { TreeUtils } from '../../Utils/TreeUtils';
import { TreeNodeType } from '../Shared/FormFields/TreeFormField/TreeFormFieldTypes';
import { olMap, TheMap } from '../TheMap/TheMap';
import { RulesDrawer } from './RulesDrawer';
import './WmsSecuritySettings.css';

const wmsRepo = new WmsRepo();
const treeUtils = new TreeUtils();

export const WmsSecuritySettings = (): ReactElement => {

  // get the ID parameter from the url
  const { id } = useParams();

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [initLayerTreeData, setInitLayerTreeData] = useState<Collection<any>>(new Collection());

  useEffect(() => {
    // TODO: need to add some sort of loading until the values are fetched
    // olMap.addLayer(mapContextLayersPreviewGroup);
    if (id) {
      setIsLoading(true);
      const fetchMapContext = async () => {
        try {
          // const response = await mapContextRepo.getMapContextWithLayers(String(id));
          const response = await wmsRepo.getAllLayers(String(id));
          // Convert the mapContext layers coming from the server to a compatible tree node list
          const _initLayerTreeData = treeUtils.wmsLayersToOlLayerGroup((response as any).data?.data);
          setInitLayerTreeData(_initLayerTreeData);
        } catch (error) {
          // @ts-ignore
          throw new Error(error);
        } finally {
          setIsLoading(false);
        }
      };
      fetchMapContext();
    }
  }, [id]);

  // TODO: replace for a decent loading screen
  if(isLoading) {
    return (<SyncOutlined spin />);
  }

  return (
    <>
      <div className='map-context'>
        <ReactGeoMapContext.Provider value={olMap}>
          <TheMap
            selectLayerDispatchAction={(selectedKeys, info) => console.log('selected', info.node)}
            layerGroupName='mrMapWmsSecurityLayers'
            initLayerTreeData={initLayerTreeData}
            layerAttributeForm={(<h1>Placeholder</h1>)}
            layerAttributeInfoIcons={(nodeData:TreeNodeType) => {
              if(!nodeData.isLeaf) {
                return (<></>);
              }
              return (
                <>
                  {nodeData.properties.datasetMetadata && (
                    <FontAwesomeIcon icon={['fas','eye']} />
                  )}
                  <FontAwesomeIcon
                    icon={['fas',`${nodeData.properties.renderingLayer ? 'eye' : 'eye-slash'}`]}
                  />
                </>
              );
            }}
          />
          <RulesDrawer />
        </ReactGeoMapContext.Provider>
      </div>
    </>
  );
};
