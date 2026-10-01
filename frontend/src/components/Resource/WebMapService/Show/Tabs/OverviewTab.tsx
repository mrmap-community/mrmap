import ServiceHistoryCard from "../../../Generic/ServiceShow/ServiceHistoryCard";
import ServiceOverview from "../../../Generic/ServiceShow/ServiceOverview";
import ServiceUpdateJobsCard from "../../../Generic/ServiceShow/ServiceUpdateJobsCard";
import MonitoringRunsCard from "../Overview/MonitoringRuns/MonitoringRunsCard";

const OverviewTab = () => {
  return (
    <ServiceOverview
      protocol="WMS"
      history={
        <ServiceHistoryCard/>
      }
    >
      <ServiceUpdateJobsCard resource="WebMapServiceUpdateJob" />
      <MonitoringRunsCard resource="WebMapServiceMonitoringRun" />
    </ServiceOverview>
  );
};

export default OverviewTab;
