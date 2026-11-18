import { CanAccess } from "react-admin";

import CollectionActivityCard from "../../../Generic/ServiceShow/CollectionActivityCard";
import ServiceOverview from "../../../Generic/ServiceShow/ServiceOverview";
import ServiceUpdateJobsCard from "../../../Generic/ServiceShow/ServiceUpdateJobsCard";
import MonitoringRunsCard from "../../../WebMapService/Show/Overview/MonitoringRuns/MonitoringRunsCard";

/**
 * The overview of a web feature service: the service record stands for an
 * anonymous visitor of a published service (#833), while each card below it
 * reads a collection of its own and is asked at `canAccess`.
 */
const OverviewTab = () => {
  return (
    <ServiceOverview
      protocol="WFS"
      collection={
        <CanAccess action="list" resource="BackgroundProcess">
          <CollectionActivityCard />
        </CanAccess>
      }
    >
      <CanAccess action="list" resource="WebFeatureServiceUpdateJob">
        <ServiceUpdateJobsCard resource="WebFeatureServiceUpdateJob" />
      </CanAccess>
      <CanAccess action="list" resource="WebFeatureServiceMonitoringRun">
        <MonitoringRunsCard resource="WebFeatureServiceMonitoringRun" />
      </CanAccess>
    </ServiceOverview>
  );
};

export default OverviewTab;
