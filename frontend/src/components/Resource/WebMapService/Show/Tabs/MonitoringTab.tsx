import ListWebMapServiceMonitoringSetting from '../../../Monitoring/WebMapServiceMonitoringSetting/ListWebMapServiceMonitoringSetting';
import ServiceMonitoringTab from '../../../Monitoring/ServiceMonitoringTab';


export const MonitoringTab = () => (
  <ServiceMonitoringTab
    settingResource='WebMapServiceMonitoringSetting'
    ListComponent={ListWebMapServiceMonitoringSetting}
  />
)

export default MonitoringTab
