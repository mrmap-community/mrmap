import AutoGraphIcon from "@mui/icons-material/AutoGraph";
import ServiceShow, {
  type ServiceTab,
} from "../../Generic/ServiceShow/ServiceShow";
import ServiceMetadataTab from "../../Generic/ServiceShow/ServiceMetadataTab";
import ServiceRelatedTab from "../../Generic/ServiceShow/ServiceRelatedTab";
import MonitoringTab from "./Tabs/MonitoringTab";
import OverviewTab from "./Tabs/OverviewTab";
import ProxySettingsTab from "./Tabs/ProxySettingsTab";
import SpatialSecureTab from "./Tabs/SpatialSecureTab";
import UpdateSettingTab from "./Tabs/UpdateSettingTab";
import WmsLayers from "./Tabs/WmsLayerTab";

const tabs: ServiceTab[] = [
  {
    path: "",
    label: "serviceShow.overview",
    icon: <AutoGraphIcon />,
    content: <OverviewTab />,
  },
  {
    path: "metadata",
    label: "serviceShow.metadata",
    resource: "WebMapService",
    operation: "partial_update_WebMapService",
    content: <ServiceMetadataTab />,
  },
  {
    path: "WebMapServiceOperationUrl/*",
    label: "serviceShow.operationUrls",
    resource: "WebMapServiceOperationUrl",
    countSource: "operationUrls",
    operation: "list_related_WebMapServiceOperationUrl_of_WebMapService",
    content: (
      <ServiceRelatedTab
        resource="WebMapServiceOperationUrl"
        defaultSelectedColumns={["operation", "url", "method"]}
      />
    ),
  },
  {
    path: "layers",
    label: "serviceShow.layers",
    resource: "Layer",
    countSource: "layers",
    content: <WmsLayers />,
  },
  {
    path: "ProxySetting",
    label: "serviceShow.proxy",
    operation: "list_related_WebMapServiceProxySetting_of_WebMapService",
    content: <ProxySettingsTab />,
  },
  {
    path: "AllowedWebMapServiceOperation/*",
    label: "serviceShow.access",
    resource: "AllowedWebMapServiceOperation",
    countSource: "allowedOperations",
    operation: "list_related_AllowedWebMapServiceOperation_of_WebMapService",
    content: <SpatialSecureTab />,
  },
  {
    path: "WebMapServiceMonitoringSetting/*",
    label: "serviceShow.monitoring",
    resource: "WebMapServiceMonitoringSetting",
    countSource: "webMapServiceMonitoringSettings",
    operation: "list_related_WebMapServiceMonitoringSetting_of_WebMapService",
    content: <MonitoringTab />,
  },
  {
    path: "WebMapServiceUpdateSetting/*",
    label: "serviceShow.updates",
    resource: "WebMapServiceUpdateSetting",
    countSource: "webMapServiceUpdateSettings",
    operation: "list_related_WebMapServiceUpdateSetting_of_WebMapService",
    content: <UpdateSettingTab />,
  },
];

export const WmsShow = () => <ServiceShow tabs={tabs} />;
