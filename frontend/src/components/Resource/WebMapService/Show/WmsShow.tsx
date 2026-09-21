import AutoGraphIcon from '@mui/icons-material/AutoGraph';
import LinearScaleIcon from '@mui/icons-material/LinearScale';
import { Badge, Tabs, TabsProps } from '@mui/material';
import { Children, cloneElement, Fragment, isValidElement, ReactElement, ReactNode, useMemo } from 'react';
import { BasenameContextProvider, RaRecord, Show, SimpleShowLayoutProps, TabbedShowLayout, UrlField, useLocation, useResourceDefinitions, useTranslate, WithRecord } from 'react-admin';
import { prepareGetCapabilititesUrl } from '../../../../ows-lib/OwsContext/utils';
import { createElementIfDefined } from '../../../../utils';
import MetadataEditTab from './Tabs/MetadataEditTab';
import MonitoringSettingsTab from './Tabs/MonitoringSettingsTab';
import OverviewtTab from './Tabs/OverviewTab';
import ProxySettingsTab from './Tabs/ProxySettingsTab';
import SpatialSecureTab from './Tabs/SpatialSecureTab';
import UpdateSettingTab from './Tabs/UpdateSettingTab';
import { WebMapServiceOperationUrlsTab } from './Tabs/WebMapServiceOperationUrlsTab';
import WmsLayers from './Tabs/WmsLayerTab';

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
        <Tabs
            value={syncWithLocation ? activePath : value}
            variant="scrollable"
            scrollButtons="auto"
            {...rest}
        >
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

interface TabHeaderIcon {
    icon: ReactNode
    countAttr?: string
}

const TabHeaderIcon = (
    {
        icon,
        countAttr
    }: TabHeaderIcon
) => {

    return (
        <Fragment>
            {createElementIfDefined(icon)}
            <WithRecord 
                label="author" 
                render={
                    record => {
                        const  content = countAttr ? record[countAttr]?.length: 0
                        return ( 
                            <Badge
                                badgeContent={content}
                                color="secondary"
                                //max={maxVisibleNotifications}
                            ></Badge>
                        )
                    }
                } 
            />
        </Fragment>
    )
}

export const WmsShow = (props: SimpleShowLayoutProps) => {
    const translate = useTranslate()
    
    const resourceDefinitions = useResourceDefinitions();

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
        jsonApiParams['fields[Layer]'] = 'mptt_lft,mptt_rgt,mptt_depth,title,string_representation,is_active,is_searchable'
        return _meta
    },[])


    return (
        <Show 
            queryOptions={{meta: meta}}
            actions={false}

        >
        <TabbedShowLayout tabs={<WmsShowTabs />} >
            <TabbedShowLayout.Tab label={translate('ra.page.dashboard')} icon={<AutoGraphIcon/>} >
                <OverviewtTab/>
            </TabbedShowLayout.Tab>
            <TabbedShowLayout.Tab 
                label={resourceDefinitions["WebMapService"].name} 
                icon={createElementIfDefined(resourceDefinitions["WebMapService"].icon)} 
                path="metadata"
            >
                <MetadataEditTab/>
            </TabbedShowLayout.Tab>
            <TabbedShowLayout.Tab label={"Interfaces"} icon={<LinearScaleIcon/>} path="interfaces">
                <UrlField source="xmlBackupFile" label='show stored capabilitites'/>
                <WithRecord 
                    label="show remote capabilities" 
                    render={(record: RaRecord) => {
                        console.log(record)
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
            <TabbedShowLayout.Tab 
                label={resourceDefinitions["WebMapServiceOperationUrl"].name} 
                icon={<TabHeaderIcon icon={resourceDefinitions["WebMapServiceOperationUrl"].icon} countAttr='operationUrls'/>} 
                path='WebMapServiceOperationUrl/*'
            >
                <BasenameContextProvider
                    basename={tabBasename}
                >
                    <WebMapServiceOperationUrlsTab/>
                </BasenameContextProvider>
            </TabbedShowLayout.Tab>   
            <TabbedShowLayout.Tab 
                label={resourceDefinitions["Layer"].name} 
                icon={<TabHeaderIcon icon={resourceDefinitions["Layer"].icon} countAttr='layers'/>} 
                path='layers' 
            >    
                <WmsLayers/>
            </TabbedShowLayout.Tab>
            <TabbedShowLayout.Tab 
                label="proxy settings" 
                path='ProxySetting'
            >
                <BasenameContextProvider
                    basename={tabBasename}
                >
                    <ProxySettingsTab/>
                </BasenameContextProvider>
            </TabbedShowLayout.Tab>
            
            <TabbedShowLayout.Tab 
                label={resourceDefinitions["AllowedWebMapServiceOperation"].name}
                icon={<TabHeaderIcon icon={resourceDefinitions["AllowedWebMapServiceOperation"].icon} countAttr='allowedOperations'/>} 
                path='AllowedWebMapServiceOperation/*'
            >
                <BasenameContextProvider
                    basename={tabBasename}
                >
                    <SpatialSecureTab/>
                </BasenameContextProvider>
            </TabbedShowLayout.Tab>
            <TabbedShowLayout.Tab 
                label={resourceDefinitions["WebMapServiceMonitoringSetting"].name}
                icon={<TabHeaderIcon icon={resourceDefinitions["WebMapServiceMonitoringSetting"].icon} countAttr='webMapServiceMonitoringSettings'/>} 
                path='WebMapServiceMonitoringSetting/*'
            >
                <BasenameContextProvider
                    basename={tabBasename}
                >
                    <MonitoringSettingsTab/>
                </BasenameContextProvider>
            </TabbedShowLayout.Tab>
            <TabbedShowLayout.Tab 
                label={resourceDefinitions["WebMapServiceUpdateSetting"].name}
                icon={<TabHeaderIcon icon={resourceDefinitions["WebMapServiceUpdateSetting"].icon} countAttr='webMapServiceUpdateSettings'/>}
                path='WebMapServiceUpdateSetting/*'>
                <BasenameContextProvider
                    basename={tabBasename}
                >
                    <UpdateSettingTab/>
                </BasenameContextProvider>
            </TabbedShowLayout.Tab>

        </TabbedShowLayout>
        </Show>
    )
};
