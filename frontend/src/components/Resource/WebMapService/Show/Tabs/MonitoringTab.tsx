import ServiceMonitoringTab from '../../../Monitoring/ServiceMonitoringTab';
import ListWebMapServiceMonitoringSetting from '../../../Monitoring/WebMapServiceMonitoringSetting/ListWebMapServiceMonitoringSetting';


export const MonitoringTab = () => (
  <ServiceMonitoringTab
    settingResource='WebMapServiceMonitoringSetting'
    ListComponent={ListWebMapServiceMonitoringSetting}
  />
)

export default MonitoringTab
