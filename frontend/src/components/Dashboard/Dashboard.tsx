import { type ReactNode } from "react";
import { useCanAccessResources } from "react-admin";

import { Box, Grid, Skeleton, Stack } from "@mui/material";

import ActivityChart from "./Cards/ActivityChart";
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
 * It answers the work before the inventory: what waits for an administrator,
 * which services carry a problem and which work the deployment is doing right
 * now are answered above the counts of the registered resources.
 */
const Dashboard = (): ReactNode => {
  const { canAccess, isPending } = useCanAccessResources({
    action: "list",
    resources: [...inventoryResources],
  });

  return (
    <Box sx={{ py: 2 }}>
      <Stack spacing={2} sx={{ mb: 2 }}>
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
      {!isPending && <Box sx={{ mt: 2 }}>
        <ActivityChart resources={inventoryResources.filter(resource => canAccess?.[resource] === true)} />
      </Box>}
    </Box>
  );
};

export default Dashboard;
