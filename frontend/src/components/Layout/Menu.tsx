import { useState } from 'react';
import {
    DashboardMenuItem,
    MenuItemLink,
    MenuProps,
    useResourceDefinition,
    useSidebarState
} from 'react-admin';

import FeedIcon from '@mui/icons-material/Feed';
import PeopleAltIcon from '@mui/icons-material/PeopleAlt';
import PublicIcon from '@mui/icons-material/Public';
import { Box } from '@mui/material';

import DisplaySettingsIcon from '@mui/icons-material/DisplaySettings';
import { createElementIfDefined } from '../../utils';
import SubMenu from './SubMenu';

type MenuName = 'menuWms' | 'menuWfs' | 'menuCsw'| 'menuMetadata'| 'menuAccounts' | 'menuAdmin';


const Menu = ({ dense = false }: MenuProps) => {
    const [state, setState] = useState({
        menuWms: true,
        menuWfs: true,
        menuCsw: true,
        menuMetadata: true,
        menuAccounts: true,
        menuAdmin: true,
    });
    const [open] = useSidebarState();

    const handleToggle = (menu: MenuName) => {
        setState(state => ({ ...state, [menu]: !state[menu] }));
    };

    const { name: wmsName, icon: wmsIcon } = useResourceDefinition({ resource: "WebMapService" })
    const { name: layerName, icon: layerIcon } = useResourceDefinition({ resource: "Layer" })
    const { name: allowedWmsOpName, icon: allowedWmsOpIcon } = useResourceDefinition({ resource: "AllowedWebMapServiceOperation" })
    const { name: wmsProxySettingName, icon: wmsProxySettingIcon } = useResourceDefinition({ resource: "WebMapServiceProxySetting" })


    const { name: wfsName, icon: wfsIcon } = useResourceDefinition({ resource: "WebFeatureService" })
    const { name: featureTypeName, icon: featureTypeIcon } = useResourceDefinition({ resource: "FeatureType" })
    const { name: cswName, icon: cswIcon } = useResourceDefinition({ resource: "CatalogueService" })
    const { name: harvestingJobName, icon: harvestingJobIcon } = useResourceDefinition({ resource: "HarvestingJob" })

    const { name: datasetName, icon: datasetIcon } = useResourceDefinition({ resource: "DatasetMetadataRecord" })
    const { name: serviceMetadataName, icon: serviceMetadataIcon } = useResourceDefinition({ resource: "ServiceMetadataRecord" })
    const { name: keywordName, icon: keywordIcon } = useResourceDefinition({ resource: "Keyword" })


    const { name: userName, icon: userIcon } = useResourceDefinition({ resource: "User" })
    const { name: organizationName, icon: organizationIcon } = useResourceDefinition({ resource: "Organization" })    

    const { name: systemInfoName, icon: systemInfoIcon } = useResourceDefinition({ resource: "SystemInfo" })
    const { name: periodicTaskName, icon: periodicTaskIcon } = useResourceDefinition({ resource: "PeriodicTask" })


    return (
        <Box
            sx={{
                width: open ? 200 : 50,
                marginTop: 1,
                marginBottom: 1,
                transition: theme =>
                    theme.transitions.create('width', {
                        easing: theme.transitions.easing.sharp,
                        duration: theme.transitions.duration.leavingScreen,
                    }),
            }}
        >
            <DashboardMenuItem />
            <SubMenu
                handleToggle={() => handleToggle('menuWms')}
                isOpen={state.menuWms}
                name={wmsName}
                icon={createElementIfDefined(wmsIcon)}
                dense={dense}
            >
                <MenuItemLink
                    to={`/${wmsName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={wmsName}
                    leftIcon={createElementIfDefined(wmsIcon)}
                    dense={dense}
                />
                <MenuItemLink
                    to={`/${layerName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={layerName}
                    leftIcon={createElementIfDefined(layerIcon)}
                    dense={dense}
                />
                <MenuItemLink
                    to={`/${allowedWmsOpName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={`Security Rules`}
                    leftIcon={createElementIfDefined(allowedWmsOpIcon)}
                    dense={dense}
                />
                <MenuItemLink
                    to={`/${wmsProxySettingName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={`Proxy settings`}
                    leftIcon={createElementIfDefined(wmsProxySettingIcon)}
                    dense={dense}
                />
            </SubMenu>
            <SubMenu
                handleToggle={() => handleToggle('menuWfs')}
                isOpen={state.menuWfs}
                name={wfsName}
                icon={createElementIfDefined(wfsIcon)}
                dense={dense}
            >
                <MenuItemLink
                    to={`/${wfsName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={wfsName}
                    leftIcon={createElementIfDefined(wfsIcon)}
                    dense={dense}
                />
                <MenuItemLink
                    to={`/${featureTypeName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={featureTypeName}
                    leftIcon={createElementIfDefined(featureTypeIcon)}
                    dense={dense}
                />
            </SubMenu>
            <SubMenu
                handleToggle={() => handleToggle('menuCsw')}
                    isOpen={state.menuCsw}
                    name={"CatalogueService"}
                    icon={createElementIfDefined(cswIcon)}
                    dense={dense}
                >
                <MenuItemLink
                    to={`/${cswName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={cswName}
                    leftIcon={createElementIfDefined(cswIcon)}
                    dense={dense}
                />
                <MenuItemLink
                    to={`/${harvestingJobName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={harvestingJobName}
                    leftIcon={createElementIfDefined(harvestingJobIcon)}
                    dense={dense}
                />
                
            </SubMenu>       
           
            <SubMenu
                handleToggle={() => handleToggle('menuMetadata')}
                isOpen={state.menuMetadata}
                name={"Metadata"}
                icon={<FeedIcon/>}
                dense={dense}
            >
                <MenuItemLink
                    to={`/${datasetName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={datasetName}
                    leftIcon={createElementIfDefined(datasetIcon)}
                    dense={dense}
                />
                <MenuItemLink
                    to={`/${keywordName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={keywordName}
                    leftIcon={createElementIfDefined(keywordIcon)}
                    dense={dense}
                />
                <MenuItemLink
                    to={`/${serviceMetadataName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={serviceMetadataName}
                    leftIcon={createElementIfDefined(serviceMetadataIcon) ?? <div></div>}
                    dense={dense}
                />
                
            </SubMenu>           
            <SubMenu
                handleToggle={() => handleToggle('menuAccounts')}
                isOpen={state.menuAccounts}
                name={"Accounts"}
                icon={<PeopleAltIcon/>}
                dense={dense}
            >
                <MenuItemLink
                    to={`/${userName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={userName}
                    leftIcon={createElementIfDefined(userIcon)}
                    dense={dense}
                />
                <MenuItemLink
                    to={`/${organizationName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={organizationName}
                    leftIcon={createElementIfDefined(organizationIcon)}
                    dense={dense}
                />
                
            </SubMenu>
            <SubMenu
                handleToggle={() => handleToggle('menuAdmin')}
                isOpen={state.menuAdmin}
                name={"Admin"}
                icon={<DisplaySettingsIcon/>}
                dense={dense}
            >
                <MenuItemLink
                    to={`/${systemInfoName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={systemInfoName}
                    leftIcon={createElementIfDefined(systemInfoIcon)}
                    dense={dense}
                />
                <MenuItemLink
                    to={`/${periodicTaskName}`}
                    state={{ _scrollToTop: true }}
                    primaryText={periodicTaskName}
                    leftIcon={createElementIfDefined(periodicTaskIcon)}
                    dense={dense}
                />
              
                
            </SubMenu>  
            <MenuItemLink
                to={"/viewer"}
                state={{ _scrollToTop: true }}
                primaryText={"MapViewer"}
                leftIcon={<PublicIcon/>}
                dense={dense}
            />
        </Box>
    );
};

export default Menu;
