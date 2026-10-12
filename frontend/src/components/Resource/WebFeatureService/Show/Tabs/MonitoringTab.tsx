import ListWebFeatureServiceMonitoringSetting from '../../../Monitoring/WebFeatureServiceMonitoringSetting/ListWebFeatureServiceMonitoringSetting';
import ServiceMonitoringTab from '../../../Monitoring/ServiceMonitoringTab';


export const MonitoringTab = () => (
  <ServiceMonitoringTab
    settingResource='WebFeatureServiceMonitoringSetting'
    ListComponent={ListWebFeatureServiceMonitoringSetting}
  />
)

export default MonitoringTab
