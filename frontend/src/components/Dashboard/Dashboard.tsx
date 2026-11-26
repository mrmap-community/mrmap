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
 * counts of the registered resources. The critical answers and the queues only
 * answer when they have something to say, so a healthy deployment with nothing
 * to do reads as the inventory.
 */
const Dashboard = (): ReactNode => {
  const { canAccess, isPending } = useCanAccessResources({
    action: "list",
    resources: [...inventoryResources],
  });

  return (
    <Box sx={{ py: 2 }}>
      {/* the critical states of the deployment precede the work which waits and
          the inventory - they answer nothing while the deployment is healthy */}
      <Stack spacing={2} sx={{ mb: 2 }}>
        <CriticalAlerts />
        {/* the queues of work and the alerts of the services answer the work
            which waits - on a narrow screen they are asked one below the
            other */}
        <WorkQueueCard />
        <ServiceAttentionCard />
      </Stack>
      <Grid container spacing={2}>
        {isPending
          ? inventoryResources.map(resource => (
              <Grid key={resource} size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                <Skeleton variant="rounded" height={180} />
              </Grid>
            ))
          : inventoryResources
              .filter(resource => canAccess?.[resource] === true)
              .map(resource => (
                <Grid key={resource} size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                  <ResourceListCard resource={resource} withList={false} compact />
                </Grid>
              ))}
      </Grid>
    </Box>
  );
};

export default Dashboard;
