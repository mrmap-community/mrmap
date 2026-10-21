import ServiceMonitoringTab from '../../../Monitoring/ServiceMonitoringTab';
import ListWebFeatureServiceMonitoringSetting from '../../../Monitoring/WebFeatureServiceMonitoringSetting/ListWebFeatureServiceMonitoringSetting';


export const MonitoringTab = () => (
  <ServiceMonitoringTab
    settingResource='WebFeatureServiceMonitoringSetting'
    ListComponent={ListWebFeatureServiceMonitoringSetting}
  />
)

export default MonitoringTab
