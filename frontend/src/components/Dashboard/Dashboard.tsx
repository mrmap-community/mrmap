import { type ReactNode } from "react";
import { useCanAccessResources } from "react-admin";

import { Box, Grid, Skeleton, Stack } from "@mui/material";

import CriticalAlerts from "./Cards/CriticalAlerts";
import ResourceListCard from "./Cards/ResourceListCard";
import ServiceAttentionCard from "./Cards/ServiceAttentionCard";
import WorkQueueCard from "./Cards/WorkQueueCard";

const inventoryResources = [
  "WebMapService",
  "Layer",
  "WebFeatureService",
  "FeatureType",
  "CatalogueService",
  "DatasetMetadataRecord",
  "ServiceMetadataRecord",
  "Organization",
  "User",
] as const;

/**
 * The dashboard of the deployment.
 *
 * It answers what is broken, then the work which waits, then the inventory: a
 * deployment whose workers do not run is answered above everything else, what
 * waits for an administrator and which services carry a problem above the
 * counts of the registered resources. The critical answers only answer when
 * they have something to say, so a healthy deployment with nothing to do reads
 * as the inventory.
 *
 * The health of the deployment and the alerts of its services are answered in a
 * column beside the inventory and not above it: an administrator reads the
 * exceptions in the same screen as the counts, without the queues pushing the
 * inventory down the page. A queue which holds nothing still answers its row,
 * but the column is as compact as its rows are and never grows into a banner.
 */
const Dashboard = (): ReactNode => {
  const { canAccess, isPending } = useCanAccessResources({
    action: "list",
    resources: [...inventoryResources],
  });

  return (
    <Box sx={{ py: 2 }}>
      {/* the critical states of the deployment precede everything the dashboard
          answers - they answer nothing while the deployment is healthy */}
      <Stack spacing={2} sx={{ mb: 2 }}>
        <CriticalAlerts />
      </Stack>
      <Grid container spacing={2}>
        {/* the inventory answers the wider region of the screen ... */}
        <Grid size={{ xs: 12, lg: 8 }}>
          <Grid container spacing={2}>
            {isPending
              ? inventoryResources.map(resource => (
                  <Grid key={resource} size={{ xs: 12, sm: 6, md: 4 }}>
                    <Skeleton variant="rounded" height={180} />
                  </Grid>
                ))
              : inventoryResources
                  .filter(resource => canAccess?.[resource] === true)
                  .map(resource => (
                    <Grid key={resource} size={{ xs: 12, sm: 6, md: 4 }}>
                      <ResourceListCard resource={resource} withList={false} compact />
                    </Grid>
                  ))}
          </Grid>
        </Grid>
        {/* ... and the health of the deployment with the alerts of its services
            answers the middle-right column beside it */}
        <Grid size={{ xs: 12, lg: 4 }}>
          <Stack spacing={2}>
            <WorkQueueCard />
            <ServiceAttentionCard />
          </Stack>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;
