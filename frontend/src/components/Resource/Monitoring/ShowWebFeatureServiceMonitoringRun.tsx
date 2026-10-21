import { type ShowProps } from "react-admin";

import ShowMonitoringRun from "./ShowMonitoringRun";

const ShowWebFeatureServiceMonitoringRun = (props: ShowProps) => (
  <ShowMonitoringRun
    {...props}
    settingResource="WebFeatureServiceMonitoringSetting"
    probeResults={[
      {
        resource: "WebFeatureServiceGetCapabilitiesProbeResult",
        type: "GetCapabilities",
        source: "getCapabilitiesProbeResults",
      },
      {
        resource: "WebFeatureServiceGetFeatureProbeResult",
        type: "GetFeature",
        source: "getFeatureProbeResults",
      },
    ]}
  />
);

export default ShowWebFeatureServiceMonitoringRun;
