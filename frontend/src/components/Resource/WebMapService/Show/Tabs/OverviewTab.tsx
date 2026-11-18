import { CanAccess } from "react-admin";

import CollectionActivityCard from "../../../Generic/ServiceShow/CollectionActivityCard";
import ServiceOverview from "../../../Generic/ServiceShow/ServiceOverview";
import ServiceUpdateJobsCard from "../../../Generic/ServiceShow/ServiceUpdateJobsCard";
import MonitoringRunsCard from "../Overview/MonitoringRuns/MonitoringRunsCard";
import SpatialSecurityCard from "../Overview/SpatialSecurity/SpatialSecurityCard";

/**
 * The overview of a web map service. The service record itself answers the
 * details, so it also stands for an anonymous visitor of a published service
 * (#833); every card below it reads a collection of its own - the runs, jobs,
 * elements and security rules behind the service - and is therefore asked at
 * `canAccess`, which an anonymous visitor does not pass.
 */
const OverviewTab = () => {
  return (
    <ServiceOverview
      protocol="WMS"
      collection={
        <CanAccess action="list" resource="BackgroundProcess">
          <CollectionActivityCard />
        </CanAccess>
      }
      spatialSecurity={
        <CanAccess action="list" resource="AllowedWebMapServiceOperation">
          <SpatialSecurityCard />
        </CanAccess>
      }
    >
      <CanAccess action="list" resource="WebMapServiceUpdateJob">
        <ServiceUpdateJobsCard resource="WebMapServiceUpdateJob" />
      </CanAccess>
      <CanAccess action="list" resource="WebMapServiceMonitoringRun">
        <MonitoringRunsCard resource="WebMapServiceMonitoringRun" />
      </CanAccess>
    </ServiceOverview>
  );
};

export default OverviewTab;
