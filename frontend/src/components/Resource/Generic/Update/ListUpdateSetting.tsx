import ListWithDialogs from "../../../../jsonapi/components/ListWithDialogs"
import { RelatedResource } from "../../../../providers/dataProvider"
import ScheduleWarningsField from "../../../Field/ScheduleWarningsField"
import useGuesserProps from "./useGuesserProps"


export interface ListWebMapServiceUpdateSettingProps {
  relatedResource?: Partial<RelatedResource>
}

const ListUpdateSetting = ({
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
          // the schedule warnings belong beside the schedule they judge,
          // not behind the edit dialog (#1332)
          defaultSelectedColumns: ["scheduleInterval",  "enabled", "scheduleWarnings"],
          updateFieldDefinitions: [
            {
              props: {
                source: "scheduleWarnings",
                label: "scheduleWarnings.columnLabel"
              },
              component: ScheduleWarningsField
            }
          ]
        }
      }
    />
  )
}

export default ListUpdateSetting