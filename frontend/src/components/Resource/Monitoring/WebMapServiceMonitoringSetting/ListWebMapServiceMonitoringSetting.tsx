import { RelatedResource } from "../../../../providers/dataProvider"
import ListMonitoringSetting from "../ListMonitoringSetting"


export interface ListWebMapServiceMonitoringSettingProps {
  relatedResource?: Partial<RelatedResource>
}

const ListWebMapServiceMonitoringSetting = ({
  relatedResource
}: ListWebMapServiceMonitoringSettingProps) => {
  return (
    <ListMonitoringSetting
      resource="WebMapServiceMonitoringSetting"
      probes={[
        { reference: "GetCapabilitiesProbe", source: "getCapabilititesProbes" },
        { reference: "GetMapProbe", source: "getMapProbes" }
      ]}
      defaultSelectedColumns={["scheduleInterval", "getCapabilititesProbes", "getMapProbes"]}
      relatedResource={relatedResource}
    />
  )
}

export default ListWebMapServiceMonitoringSetting
