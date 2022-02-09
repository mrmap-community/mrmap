import React, { ReactElement, useState } from 'react';

import { PlusCircleOutlined } from '@ant-design/icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';

import { DrawerContentType, RightDrawer } from '../../Shared/RightDrawer/RightDrawer';

import { SearchTable } from './SearchTable/SearchTable';


export const TabsDrawer = ({
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
      <SearchTable addDatasetToMapAction={addDatasetToMapAction} />
    ),
    key: 'datasetMetadataTable'
  };

  return (
    <RightDrawer 
      drawerContent={[mapContextDrawerContent, datasetMetadataDrawerContent]}
      defaultOpenTab={defaultOpenTab}
    />
  );
};
