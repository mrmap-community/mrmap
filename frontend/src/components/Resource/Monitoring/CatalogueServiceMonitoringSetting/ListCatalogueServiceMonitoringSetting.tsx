import { RelatedResource } from "../../../../providers/dataProvider"
import ListMonitoringSetting from "../ListMonitoringSetting"


export interface ListCatalogueServiceMonitoringSettingProps {
  relatedResource?: Partial<RelatedResource>
}

const ListCatalogueServiceMonitoringSetting = ({
  relatedResource
}: ListCatalogueServiceMonitoringSettingProps) => {
  return (
    <ListMonitoringSetting
      resource="CatalogueServiceMonitoringSetting"
      probes={[
        { reference: "CatalogueServiceGetCapabilitiesProbe", source: "getCapabilitiesProbes" },
        { reference: "CatalogueServiceGetRecordsProbe", source: "getRecordsProbes" }
      ]}
      defaultSelectedColumns={["scheduleInterval", "getCapabilitiesProbes", "getRecordsProbes"]}
      relatedResource={relatedResource}
    />
  )
}

export default ListCatalogueServiceMonitoringSetting
