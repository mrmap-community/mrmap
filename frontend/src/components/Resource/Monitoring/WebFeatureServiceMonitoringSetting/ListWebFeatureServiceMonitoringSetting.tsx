import ListMonitoringSetting from "../ListMonitoringSetting"
import { RelatedResource } from "../../../../providers/dataProvider"


export interface ListWebFeatureServiceMonitoringSettingProps {
  relatedResource?: Partial<RelatedResource>
}

const ListWebFeatureServiceMonitoringSetting = ({
  relatedResource
}: ListWebFeatureServiceMonitoringSettingProps) => {
  return (
    <ListMonitoringSetting
      resource="WebFeatureServiceMonitoringSetting"
      probes={[
        { reference: "WebFeatureServiceGetCapabilitiesProbe", source: "getCapabilitiesProbes" },
        { reference: "WebFeatureServiceGetFeatureProbe", source: "getFeatureProbes" }
      ]}
      defaultSelectedColumns={["scheduleInterval", "getCapabilitiesProbes", "getFeatureProbes"]}
      relatedResource={relatedResource}
    />
  )
}

export default ListWebFeatureServiceMonitoringSetting
