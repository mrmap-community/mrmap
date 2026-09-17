import { ResourceContext } from 'react-admin';
import ListWebMapServiceMonitoringSetting from '../Monitoring/Wms/ListWebMapServiceMonitoringSetting';


export const MonitoringSettingsTab = () => {
  return (
    <ResourceContext
      value='WebMapServiceMonitoringSetting'
    >
      <ListWebMapServiceMonitoringSetting/>
    </ResourceContext>
  )
}

export default MonitoringSettingsTab