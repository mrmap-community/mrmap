import { BasenameContextProvider, DeleteButton, EditButton, RaRecord, SaveButton, Show, SimpleShowLayoutProps, TabbedShowLayout, Toolbar, TopToolbar, UrlField, useLocation, useResourceDefinition, WithRecord } from 'react-admin';

import LinearScaleIcon from '@mui/icons-material/LinearScale';
import { Tabs, TabsProps } from '@mui/material';
import { Children, cloneElement, isValidElement, ReactElement, ReactNode, useMemo } from 'react';
import EditGuesser from '../../../jsonapi/components/EditGuesser';
import { prepareGetCapabilititesUrl } from '../../../ows-lib/OwsContext/utils';
import { createElementIfDefined } from '../../../utils';
import { MonitoringSettingsTab } from './MonitoringSettingsTab';
import ProxySettingsTab from './ProxySettings';
import SpatialSecureTab from './SpatialSecureTab';
import WebMapServiceOperationUrlsTab from './WebMapServiceOperationUrlsTab';
import WmsLayers from './WmsLayerTab';

const WmsShowActions = () => (
    <TopToolbar>
        <EditButton/>
    </TopToolbar>
);

interface WmsShowTabsProps extends Omit<TabsProps, 'value'> {
    children?: ReactNode;
    syncWithLocation?: boolean;
    value?: number | string;
}

interface WmsShowTabProps {
    context?: 'header' | 'content';
    path?: string;
    syncWithLocation?: boolean;
    to?: unknown;
    value?: number | string;
}

const WmsShowTabs = ({ children, syncWithLocation = true, value, ...rest }: WmsShowTabsProps) => {
    const location = useLocation();
    const showPathIndex = location.pathname.search(/\/show(?:\/|$)/);
    const showBase = showPathIndex === -1
        ? `${location.pathname}/show`
        : location.pathname.slice(0, showPathIndex + '/show'.length);
    const activePath = location.pathname
        .slice(showBase.length)
        .replace(/^\/+/, '')
        .split('/')[0] ?? '';

    return (
        <Tabs value={syncWithLocation ? activePath : value} {...rest}>
            {Children.map(children, (tab, index) => {
                if (!isValidElement(tab)) {
                    return null;
                }

                const tabProps = (tab as ReactElement<WmsShowTabProps>).props;
                const path = typeof tabProps.path === 'string'
                    ? tabProps.path.replace(/\/\*$/, '')
                    : index > 0 ? index : '';

                return cloneElement(tab as ReactElement<WmsShowTabProps>, {
                    context: 'header',
                    value: syncWithLocation ? path : index,
                    syncWithLocation,
                    to: {
                        ...location,
                        pathname: `${showBase}/${path}`,
                    },
                });
            })}
        </Tabs>
    );
};


export const WmsShow = (props: SimpleShowLayoutProps) => {
    const { name: layerName, icon: layerIcon } = useResourceDefinition({resource: 'Layer'})
    const { name: wmsName, icon: wmsIcon } = useResourceDefinition({resource: 'WebMapService'})
    const { name: operationUrlName, icon: operationUrlIcon } = useResourceDefinition({resource: 'WebMapServiceOperationUrl'})

    const { pathname } = useLocation()
    const tabBasename = useMemo(() => {
        const tabPath = '/show'
        const tabPathIndex = pathname.indexOf(tabPath)

        return tabPathIndex === -1
            ? pathname
            : pathname.slice(0, tabPathIndex + tabPath.length)
    }, [pathname])
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

    return (
        <Show 
            queryOptions={{meta: meta}}
            actions={<WmsShowActions/>}
        >
        <TabbedShowLayout tabs={<WmsShowTabs />}>
            <TabbedShowLayout.Tab label={wmsName} icon={createElementIfDefined(wmsIcon)}>
                <EditGuesser 
                    resource='WebMapService'
                    //id={settingId}
                    redirect={false}
                    simpleFormProps={{
                        toolbar:
                        <Toolbar sx={{ display: 'flex', justifyContent: 'space-between' }}>
                            <SaveButton alwaysEnable/>
                            <DeleteButton/>
                        </Toolbar>
                    
                    }}
                />
            </TabbedShowLayout.Tab>
            <TabbedShowLayout.Tab label={"Interfaces"} icon={<LinearScaleIcon/>} path="interfaces">
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
                    }}
                />
                <UrlField source="xmlBackupFileSecured" label='show secured capabilitites'/>
            </TabbedShowLayout.Tab>
            <TabbedShowLayout.Tab label={operationUrlName} icon={createElementIfDefined(operationUrlIcon)} path='WebMapServiceOperationUrl/*'>
                <BasenameContextProvider
                    basename={tabBasename}
                >
                    <WebMapServiceOperationUrlsTab/>
                </BasenameContextProvider>
            </TabbedShowLayout.Tab>   
            <TabbedShowLayout.Tab label={layerName} icon={createElementIfDefined(layerIcon)} path='layers' >
                
                <WmsLayers/>
            </TabbedShowLayout.Tab>
            <TabbedShowLayout.Tab label="proxy settings" path='ProxySetting'>
                <BasenameContextProvider
                    basename={tabBasename}
                >
                    <ProxySettingsTab/>
                </BasenameContextProvider>
            </TabbedShowLayout.Tab>
            
            <TabbedShowLayout.Tab label="Security Rules" path='AllowedWebMapServiceOperation/*'>
                <BasenameContextProvider
                    basename={tabBasename}
                >
                    <SpatialSecureTab/>
                </BasenameContextProvider>
            </TabbedShowLayout.Tab>
            <TabbedShowLayout.Tab label="Monitoring Settings" path='WebMapServiceMonitoringSetting/*'>
                <BasenameContextProvider
                    basename={tabBasename}
                >
                    <MonitoringSettingsTab/>
                </BasenameContextProvider>
            </TabbedShowLayout.Tab>

        </TabbedShowLayout>
        </Show>
    )
};
