import { type ShowProps } from "react-admin";
import ShowMonitoringRun from "./ShowMonitoringRun";

const ShowWebMapServiceMonitoringRun = (props: ShowProps) => (
  <ShowMonitoringRun
    {...props}
    settingResource="WebMapServiceMonitoringSetting"
    probeResults={[
      {
        resource: "GetCapabilitiesProbeResult",
        type: "GetCapabilities",
        source: "getCapabilititesProbeResults",
      },
      {
        resource: "GetMapProbeResult",
        type: "GetMap",
        source: "getMapProbeResults",
      },
    ]}
  />
);

export default ShowWebMapServiceMonitoringRun;
