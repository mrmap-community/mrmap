import { DeleteButton, EditButton, RaRecord, SaveButton, Show, SimpleShowLayoutProps, TabbedShowLayout, Toolbar, TopToolbar, UrlField, useResourceDefinition, WithRecord } from 'react-admin';

import LinearScaleIcon from '@mui/icons-material/LinearScale';
import { createElement, useCallback, useMemo } from 'react';
import EditGuesser from '../../../jsonapi/components/EditGuesser';
import { useFieldsForOperation } from '../../../jsonapi/hooks/useFieldsForOperation';
import { prepareGetCapabilititesUrl } from '../../../ows-lib/OwsContext/utils';
import { createElementIfDefined } from '../../../utils';
import ProxySettingsTab from './ProxySettings';
import SpatialSecureTab from './SpatialSecureTab';
import WebMapServiceOperationUrlsTab from './WebMapServiceOperationUrlsTab';
import WmsLayers from './WmsLayerTab';
const { VITE_API_SCHEMA, VITE_API_BASE_URL } = import.meta.env;

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


    const meta = useMemo(()=>{
        const jsonApiParams: any = {
                include: 'layers,operationUrls',
            }
        const _meta = {
            jsonApiParams: jsonApiParams
        }
        jsonApiParams['fields[Layer]'] = 'mptt_lft,mptt_rgt,mptt_depth,title,string_representation'
        return _meta
    },[])

    const getCapabilititesUrl = useCallback((wms: RaRecord)=>(
        wms.operationUrls.find((operationUrl: RaRecord)=> (operationUrl.operation === 1 && operationUrl.method === 1))
    ),[])

    return (
        <Show 
            queryOptions={{meta: meta}}
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
                <UrlField source="xmlBackupFile" label='show stored capabilitites'/>
                <WithRecord 
                    label="show remote capabilities" 
                    render={(record: RaRecord) => {
                        const url = record.operationUrls?.find((operationUrl: RaRecord)=> (operationUrl.operation === 1 && operationUrl.method === 1));
                        url.url = prepareGetCapabilititesUrl(
                                url.url,
                                "WMS",
                                record.version.toString().split('').join('.')
                            ).href
                        return url ? <UrlField record={url} source="url"/> : null; 
                    }}/>
                <WithRecord 
                    label="show securited capabilities" 
                    render={(record: RaRecord) => {                      
                        const url = {
                            url: prepareGetCapabilititesUrl(
                                `${VITE_API_SCHEMA}://${VITE_API_BASE_URL}/mrmap-proxy/wms/${record.id}`,
                                "WMS",
                                record.version.toString().split('').join('.')
                            ).href
                        }
                        return <UrlField record={url} source="url"/>
                    }} />
           
           
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
