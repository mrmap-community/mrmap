import ServiceOverview from "../../../Generic/ServiceShow/ServiceOverview";
import ServiceUpdateJobsCard from "../../../Generic/ServiceShow/ServiceUpdateJobsCard";
import MonitoringRunsCard from "../../../WebMapService/Show/Overview/MonitoringRuns/MonitoringRunsCard";


const OverviewTab = () => {
  return (
    <ServiceOverview
      protocol="WFS"
    >
      <ServiceUpdateJobsCard resource="WebFeatureServiceUpdateJob" />
      <MonitoringRunsCard resource="WebFeatureServiceMonitoringRun" />
    </ServiceOverview>
  );
};

export default OverviewTab;
