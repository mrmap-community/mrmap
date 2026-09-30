import ListWithDialogs from "../../../../jsonapi/components/ListWithDialogs"
import { RelatedResource } from "../../../../providers/dataProvider"
import useGuesserProps from "./useGuesserProps"


export interface ListWebMapServiceMonitoringSettingProps {
  relatedResource?: Partial<RelatedResource>
}

const ListWebMapServiceMonitoringSetting = ( {
  relatedResource
}: ListWebMapServiceMonitoringSettingProps) => {
  const guesserProps = useGuesserProps()
  return (
    <ListWithDialogs
      editGuesserProps={guesserProps}
      createGuesserProps={guesserProps}
      listGuesserProps={
        {
          relatedResource: relatedResource,
          defaultSelectedColumns: ["scheduleInterval", "getCapabilititesProbes", "getMapProbes", ]
        }
      }
    />
  )
}

export default ListWebMapServiceMonitoringSetting