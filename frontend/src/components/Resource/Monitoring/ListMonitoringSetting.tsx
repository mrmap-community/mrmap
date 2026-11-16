import ListWithDialogs from "../../../jsonapi/components/ListWithDialogs"
import { RelatedResource } from "../../../providers/dataProvider"
import ScheduleWarningsField from "../../Field/ScheduleWarningsField"
import useMonitoringSettingGuesserProps, { MonitoringProbeConfig } from "./useMonitoringSettingGuesserProps"

export interface ListMonitoringSettingProps {
  /** resource of the monitoring setting of the service */
  resource: string
  /** probes which are configurable for the setting */
  probes: MonitoringProbeConfig[]
  /** columns of the settings list */
  defaultSelectedColumns: string[]
  relatedResource?: Partial<RelatedResource>
}

const ListMonitoringSetting = ({
  resource,
  probes,
  defaultSelectedColumns,
  relatedResource
}: ListMonitoringSettingProps) => {
  const guesserProps = useMonitoringSettingGuesserProps(resource, probes)
  return (
    <ListWithDialogs
      editGuesserProps={guesserProps}
      createGuesserProps={guesserProps}
      listGuesserProps={
        {
          relatedResource: relatedResource,
          // every monitoring list shows the state of its schedule beside the
          // schedule itself - without opening the edit form (#1332)
          defaultSelectedColumns: [...defaultSelectedColumns, "scheduleWarnings"],
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

export default ListMonitoringSetting
