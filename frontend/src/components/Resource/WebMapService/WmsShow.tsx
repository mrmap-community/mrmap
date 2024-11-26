import { EditButton, Show, SimpleShowLayoutProps, TabbedShowLayout, TextField, TopToolbar } from 'react-admin';


import ProxySettingsTab from './ProxySettings';
import SpatialSecureTab from './SpatialSecureTab';
import WmsLayers from './WmsLayerTab';

const WmsShowActions = () => (
    <TopToolbar>
        <EditButton/>
    </TopToolbar>
);



export const WmsShow = (props: SimpleShowLayoutProps) => {

    return (
        <Show 
            queryOptions={{meta: {jsonApiParams:{include: 'layers'}}}}
            actions={<WmsShowActions/>}
        >
            <TabbedShowLayout>
                <TabbedShowLayout.Tab label="service">
                    <TextField source="id" />
                    <TextField source="title" />
                    <TextField source="abstract" />
                </TabbedShowLayout.Tab>
                <TabbedShowLayout.Tab label="layers" path='layers/:layerId'>
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
