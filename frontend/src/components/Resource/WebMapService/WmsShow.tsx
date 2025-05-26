import { DeleteButton, EditButton, SaveButton, Show, SimpleShowLayoutProps, TabbedShowLayout, Toolbar, TopToolbar, UrlField, useResourceDefinition } from 'react-admin';

import LinearScaleIcon from '@mui/icons-material/LinearScale';
import { createElement, useMemo } from 'react';
import EditGuesser from '../../../jsonapi/components/EditGuesser';
import { useFieldsForOperation } from '../../../jsonapi/hooks/useFieldsForOperation';
import { createElementIfDefined } from '../../../utils';
import ProxySettingsTab from './ProxySettings';
import SpatialSecureTab from './SpatialSecureTab';
import WebMapServiceOperationUrlsTab from './WebMapServiceOperationUrlsTab';
import WmsLayers from './WmsLayerTab';

const WmsShowActions = () => (
    <TopToolbar>
        <EditButton/>
    </TopToolbar>
);



export const WmsShow = (props: SimpleShowLayoutProps) => {
    const { name: layerName, icon: layerIcon } = useResourceDefinition({resource: 'Layer'})
    const { name: wmsName, icon: wmsIcon } = useResourceDefinition({resource: 'WebMapService'})
    const { name: operationUrlName, icon: operationUrlIcon } = useResourceDefinition({resource: 'WebMapServiceOperationUrl'})

    const fieldDefinitions = useFieldsForOperation('partial_update_WebMapService', false, true);

    const fields = useMemo(()=>(
        fieldDefinitions.filter(fieldDef => ['title', 'abstract'].includes(fieldDef.props.source)).map(fieldDef => createElement(fieldDef.component, fieldDef.props))
    ),[fieldDefinitions])

    return (
        <Show 
            queryOptions={{meta: {jsonApiParams:{include: 'layers,operationUrls'}}}}
            actions={<WmsShowActions/>}
        >
        <TabbedShowLayout
            
        >
            <TabbedShowLayout.Tab label={wmsName} icon={createElementIfDefined(wmsIcon)}>
                <EditGuesser 
                    resource='WebMapService'
                    //id={settingId}
                    redirect={false}
                    toolbar={
                        <Toolbar sx={{ display: 'flex', justifyContent: 'space-between' }}>
                            <SaveButton alwaysEnable/>
                            <DeleteButton/>
                        </Toolbar>
                    }
                    
                />
            </TabbedShowLayout.Tab>
            <TabbedShowLayout.Tab label={"Interfaces"} icon={<LinearScaleIcon/>}>
                <UrlField source="xmlBackupFile" content='show capabilitites'/>
            </TabbedShowLayout.Tab>
            <TabbedShowLayout.Tab label={operationUrlName} icon={createElementIfDefined(operationUrlIcon)} path='operation-urls'>
                <WebMapServiceOperationUrlsTab/>
            </TabbedShowLayout.Tab>   
            <TabbedShowLayout.Tab label={layerName} icon={createElementIfDefined(layerIcon)} path='layers' >
                
                <WmsLayers/>
            </TabbedShowLayout.Tab>
            <TabbedShowLayout.Tab label="proxy settings" path='ProxySetting'>
                <ProxySettingsTab/>
            </TabbedShowLayout.Tab>
            
            <TabbedShowLayout.Tab label="spatial secure" path='spatial-secure'>
                <SpatialSecureTab/>
            </TabbedShowLayout.Tab>

            {/** Monitoring settings */}
        </TabbedShowLayout>
        </Show>
    )
};
