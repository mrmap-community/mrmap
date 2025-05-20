import { EditButton, Show, SimpleShowLayoutProps, TabbedShowLayout, TextField, TopToolbar, useResourceDefinition } from 'react-admin';


import { createElementIfDefined } from '../../../utils';
import ProxySettingsTab from './ProxySettings';
import SpatialSecureTab from './SpatialSecureTab';
import WmsLayers from './WmsLayerTab';

const WmsShowActions = () => (
    <TopToolbar>
        <EditButton/>
    </TopToolbar>
);



export const WmsShow = (props: SimpleShowLayoutProps) => {

    const { name: layerName, icon: layerIcon } = useResourceDefinition({resource: 'Layer'})
    const { name: wmsName, icon: wmsIcon } = useResourceDefinition({resource: 'WebMapService'})

    return (
        <Show 
            queryOptions={{meta: {jsonApiParams:{include: 'layers'}}}}
            actions={<WmsShowActions/>}
        >
            <TabbedShowLayout>
                <TabbedShowLayout.Tab label={wmsName} icon={createElementIfDefined(wmsIcon)}>
                    <TextField source="id" />
                    <TextField source="title" />
                    <TextField source="abstract" />
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
            </TabbedShowLayout>
        </Show>
    )
};
