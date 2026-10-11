import ServiceOverview from "../../Generic/ServiceShow/ServiceOverview";
import ServiceUpdateJobsCard from "../../Generic/ServiceShow/ServiceUpdateJobsCard";
import HarvestingSchedulesCard from "./HarvestingSchedulesCard";
import HarvestingActivityCard from "./HarvestingActivityCard";

const Overview = () => (
  <ServiceOverview protocol="CSW">
    <ServiceUpdateJobsCard resource="CatalogueServiceUpdateJob" />
    <HarvestingSchedulesCard />
    <HarvestingActivityCard />
  </ServiceOverview>
);

export default Overview;
