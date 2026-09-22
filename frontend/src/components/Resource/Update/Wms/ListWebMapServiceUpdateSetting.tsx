import ListWithDialogs from "../../../../jsonapi/components/ListWithDialogs"
import { RelatedResource } from "../../../../providers/dataProvider"
import useGuesserProps from "./useGuesserProps"


export interface ListWebMapServiceUpdateSettingProps {
  relatedResource?: Partial<RelatedResource>
}

const ListWebMapServiceUpdateSetting = ({
  relatedResource
}: ListWebMapServiceUpdateSettingProps) => {
  const guesserProps = useGuesserProps()
  return (
    <ListWithDialogs
      editGuesserProps={guesserProps}
      createGuesserProps={guesserProps}
      listGuesserProps={
        {
          relatedResource: relatedResource,
          defaultSelectedColumns: ["scheduleInterval",  "enabled"]
        }
      }
    />
  )
}

export default ListWebMapServiceUpdateSetting