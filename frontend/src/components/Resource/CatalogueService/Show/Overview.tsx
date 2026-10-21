import ServiceOverview from "../../Generic/ServiceShow/ServiceOverview";
import ServiceUpdateJobsCard from "../../Generic/ServiceShow/ServiceUpdateJobsCard";
import HarvestingActivityCard from "./HarvestingActivityCard";
import HarvestingSchedulesCard from "./HarvestingSchedulesCard";

const Overview = () => (
  <ServiceOverview protocol="CSW">
    <ServiceUpdateJobsCard resource="CatalogueServiceUpdateJob" />
    <HarvestingSchedulesCard />
    <HarvestingActivityCard />
  </ServiceOverview>
);

export default Overview;
