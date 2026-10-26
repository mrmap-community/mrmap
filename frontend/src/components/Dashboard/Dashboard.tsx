import { type ReactNode } from "react";

import { Box, Grid, Stack } from "@mui/material";

import ResourceListCard from "./Cards/ResourceListCard";
import ServiceAttentionCard from "./Cards/ServiceAttentionCard";
import WorkQueueCard from "./Cards/WorkQueueCard";

/**
 * The dashboard of the deployment.
 *
 * It answers the work before the inventory: what waits for an administrator,
 * which services carry a problem and which work the deployment is doing right
 * now are answered above the counts of the registered resources, because an
 * administrator opens this screen to decide what to do next and not to read the
 * size of the registry. The inventory stays below and is the same as before.
 *
 * The inventory is answered in three rows of MUI grid cells: four cards on the
 * wide screens of the registry, two by two on a tablet and one below the other
 * on a phone, so a card is never cramped and never widens the dashboard.
 */
const Dashboard = (): ReactNode => {
  return (
    <Box sx={{ py: 2 }}>
      {/* the queues of work and the alerts of the services answer the work which
          waits - on a narrow screen they are asked one below the other */}
      <Stack spacing={2} sx={{ mb: 2 }}>
        <WorkQueueCard />
        <ServiceAttentionCard />
      </Stack>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <ResourceListCard resource={"WebMapService"} withList={false} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <ResourceListCard resource={"Layer"} withList={false} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <ResourceListCard resource={"WebFeatureService"} withList={false} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <ResourceListCard resource={"FeatureType"} withList={false} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 4 }}>
          <ResourceListCard resource={"CatalogueService"} withList={false} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 4 }}>
          <ResourceListCard resource={"DatasetMetadataRecord"} withList={false} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 4 }}>
          <ResourceListCard resource={"ServiceMetadataRecord"} withList={false} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 6 }}>
          <ResourceListCard resource={"Organization"} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 6 }}>
          <ResourceListCard resource={"User"} />
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;
