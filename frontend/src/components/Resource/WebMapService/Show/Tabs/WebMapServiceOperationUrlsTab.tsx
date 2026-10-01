import ServiceRelatedTab from "../../../Generic/ServiceShow/ServiceRelatedTab";

export const WebMapServiceOperationUrlsTab = () => (
  <ServiceRelatedTab
    resource="WebMapServiceOperationUrl"
    defaultSelectedColumns={["operation", "url", "method"]}
  />
);

export default WebMapServiceOperationUrlsTab;
