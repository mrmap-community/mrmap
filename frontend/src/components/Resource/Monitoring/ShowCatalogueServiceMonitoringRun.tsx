import { type ShowProps } from "react-admin";
import ShowMonitoringRun from "./ShowMonitoringRun";

const ShowCatalogueServiceMonitoringRun = (props: ShowProps) => (
  <ShowMonitoringRun
    {...props}
    settingResource="CatalogueServiceMonitoringSetting"
    probeResults={[
      {
        resource: "CatalogueServiceGetCapabilitiesProbeResult",
        type: "GetCapabilities",
        source: "getCapabilitiesProbeResults",
      },
      {
        resource: "CatalogueServiceGetRecordsProbeResult",
        type: "GetRecords",
        source: "getRecordsProbeResults",
      },
    ]}
  />
);

export default ShowCatalogueServiceMonitoringRun;
