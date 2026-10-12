import ListCatalogueServiceMonitoringSetting from '../../Monitoring/CatalogueServiceMonitoringSetting/ListCatalogueServiceMonitoringSetting';
import ServiceMonitoringTab from '../../Monitoring/ServiceMonitoringTab';


export const MonitoringTab = () => (
  <ServiceMonitoringTab
    settingResource='CatalogueServiceMonitoringSetting'
    ListComponent={ListCatalogueServiceMonitoringSetting}
  />
)

export default MonitoringTab
