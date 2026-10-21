import ServiceOverview from "../../../Generic/ServiceShow/ServiceOverview";
import ServiceUpdateJobsCard from "../../../Generic/ServiceShow/ServiceUpdateJobsCard";
import MonitoringRunsCard from "../Overview/MonitoringRuns/MonitoringRunsCard";
import SpatialSecurityCard from "../Overview/SpatialSecurity/SpatialSecurityCard";

const OverviewTab = () => {
  return (
    <ServiceOverview
      protocol="WMS"
      spatialSecurity={<SpatialSecurityCard />}
    >
      <ServiceUpdateJobsCard resource="WebMapServiceUpdateJob" />
      <MonitoringRunsCard resource="WebMapServiceMonitoringRun" />
    </ServiceOverview>
  );
};

export default OverviewTab;
