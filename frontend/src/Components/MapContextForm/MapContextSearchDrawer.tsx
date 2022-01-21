import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import React, { ReactElement, useState } from "react";
import { CustomContentType, SearchDrawer } from "../SearchDrawer/SearchDrawer";

export const MapContextSearchDrawer = ({
  addDatasetToMapAction = () => undefined,
  mapContextForm=(<></>),
  isOpenByDefault=false
}:{
  addDatasetToMapAction?: (dataset: any) => void;
  mapContextForm?: ReactElement;
  isOpenByDefault?: boolean;
}):JSX.Element => {
  
  const [isDrawerVisible, setIsDrawerVisible] = useState<boolean>(isOpenByDefault);

  const drawerContent: CustomContentType = {
    title: 'Map Context',
    icon: <FontAwesomeIcon icon={['fas', 'box']} />,
    isVisible: isDrawerVisible,
    onTabCickAction: () => setIsDrawerVisible(!isDrawerVisible),
    content: mapContextForm


  };
  return (
    <SearchDrawer 
      addDatasetToMapAction={addDatasetToMapAction}
      customContent={[drawerContent]}
      isOpenByDefault={isOpenByDefault}
    />
  );
};
