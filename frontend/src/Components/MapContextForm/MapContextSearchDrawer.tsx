import { PlusCircleOutlined } from '@ant-design/icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { Button } from 'antd';
import React, { ReactElement, useState } from 'react';
import DatasetMetadataRepo from '../../Repos/DatasetMetadataRepo';
import { DrawerContentType, SearchDrawer } from '../Shared/SearchDrawer/SearchDrawer';
import RepoTable from '../Shared/Table/RepoTable';
import { getDatasetMetadataColumns } from './helper';

const datasetMetadataRepo = new DatasetMetadataRepo();

export const MapContextSearchDrawer = ({
  addDatasetToMapAction = () => undefined,
  mapContextForm=(<></>),
  isVisible=false,
  defaultOpenTab=''
}:{
  addDatasetToMapAction?: (dataset: any) => void;
  mapContextForm?: ReactElement;
  isVisible?: boolean;
  defaultOpenTab?: string;
}):JSX.Element => {
  
  const [isDrawerVisible, setIsDrawerVisible] = useState<boolean>(isVisible);
  
  const onAddDatasetToMap = (dataset: any) => {
    addDatasetToMapAction(dataset); 
  };

  const getDatasetMetadataColumnActions = (text: any, record:any) => {
    return (
      <>
        <Button
          disabled={record.layers.length === 0 || !record.layers}
          size='small'
          type='primary'
          onClick={ () => { onAddDatasetToMap(record); }}
        >
          Zur Karte hinzufügen
        </Button>
      </>
    );
  };

  const datasetMetadataColumns = getDatasetMetadataColumns(getDatasetMetadataColumnActions);

  const mapContextDrawerContent: DrawerContentType = {
    title: 'Map Context',
    icon: <FontAwesomeIcon icon={['fas', 'box']} />,
    isVisible: isDrawerVisible,
    onTabCickAction: () => setIsDrawerVisible(!isDrawerVisible),
    content: mapContextForm,
    key: 'mapContextForm'
  };

  const datasetMetadataDrawerContent: DrawerContentType = {
    title: 'Metadata Datasets',
    icon: <PlusCircleOutlined />,
    isVisible: isDrawerVisible,
    onTabCickAction: () => setIsDrawerVisible(!isDrawerVisible),
    content: (
      <RepoTable
        repo={datasetMetadataRepo}
        columns={datasetMetadataColumns}
        pagination={{
          defaultPageSize: 13,
          showSizeChanger: true,
          pageSizeOptions: ['10', '13', '20', '50', '100']
        }}
      />
    ),
    key: 'datasetMetadataTable'
  };

  return (
    <SearchDrawer 
      drawerContent={[mapContextDrawerContent, datasetMetadataDrawerContent]}
      defaultOpenTab={defaultOpenTab}
    />
  );
};
