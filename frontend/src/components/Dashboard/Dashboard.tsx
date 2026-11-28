import { type ReactNode, useState } from "react";
import { useCanAccessResources } from "react-admin";

import { Box, Grid, Skeleton, Stack } from "@mui/material";

import ActivityChart from "./Cards/ActivityChart";
import BackgroundProcessesCard from "./Cards/BackgroundProcessesCard";
import CriticalAlerts from "./Cards/CriticalAlerts";
import DailyChangesChart from "./Cards/DailyChangesChart";
import InventoryChart from "./Cards/InventoryChart";
import InventoryDistributionCard from "./Cards/InventoryDistributionCard";
import RecentNoticesCard from "./Cards/RecentNoticesCard";
import ResourceListCard from "./Cards/ResourceListCard";
import ServiceAttentionCard from "./Cards/ServiceAttentionCard";
import WorkQueueCard from "./Cards/WorkQueueCard";
import DashboardHeader from "./DashboardHeader";
import {
  inventoryKpiResources,
  useDashboardCounts,
  useDashboardInventory,
} from "./useDashboardInventory";
import { useDashboardPeriod } from "./useDashboardPeriod";

/**
 * The width one of the seven KPI tiles takes at each breakpoint, so the row
 * answers the mockup with all seven of them side by side on a wide desktop and
 * wraps into readable tiles on a tablet and a phone instead of clipping them.
 * `100 / 7` is what the mockup draws at ~1728 CSS px.
 */
const KPI_SIZE = { xs: 6, sm: 4, md: 3, lg: 2, xl: 100 / 7 } as const;

/** the shape a KPI tile keeps while its permission is still unanswered */
const KpiSkeleton = () => <Skeleton variant="rounded" sx={{ minHeight: 104 }} />;

/**
 * The dashboard of the deployment, in the order an administrator reads it.
 *
 * What is broken answers first, then the inventory with its changes, then the
 * work which waits and the notices of the deployment (#1820 follows the final
 * mockup of #1813). The header decides over which window the KPI tiles, the two
 * time series, the stacked daily changes and the distribution answer — one
 * period for the whole screen, so no two of them ever disagree about the days
 * they name — and one refresh answers the whole screen at once.
 *
 * The critical answers answer nothing while the deployment is healthy, so a
 * healthy deployment with nothing to do reads as its inventory, and none of the
 * queues grows into a banner above the content.
 *
 * The numbers of the charts are read once per resource and shared by every card
 * which draws them: the counts of the KPI tiles are the counts of the donut and
 * the verified daily statistics of the sparklines are the series of the
 * inventory line and of the stacked bars. The screen never asks the api the same
 * thing twice for what it draws (#1814).
 */
const Dashboard = (): ReactNode => {
  const { canAccess, isPending } = useCanAccessResources({
    action: "list",
    resources: [...inventoryKpiResources],
  });
  // the end of the bounded window the notices table reads, fixed for the mount:
  // a window read from the clock of every render would key a new request per
  // render and never let the bounded page of a source settle (#1819)
  const [noticesNow] = useState(() => Date.now());
  const { period, setPeriod, refresh, refreshedAt } = useDashboardPeriod();
  const permitted = (resources: readonly string[]) =>
    resources.filter(resource => canAccess?.[resource] === true);
  const kpiResources = isPending ? [] : permitted(inventoryKpiResources);
  // the reads of the screen: the verified stock of the window and the counts of
  // today, which the KPI tiles ask with the very same queries
  const inventory = useDashboardInventory(kpiResources, period);
  const counts = useDashboardCounts(kpiResources);

  return (
    <Box sx={{ py: 2 }}>
      <Stack spacing={2} sx={{ mb: 2 }}>
        <DashboardHeader
          period={period}
          onPeriodChange={setPeriod}
          onRefresh={refresh}
          refreshedAt={refreshedAt}
        />
        {/* the critical states of the deployment precede everything the dashboard
            answers - they answer nothing while the deployment is healthy */}
        <CriticalAlerts />
      </Stack>
      {/* the inventory answers the mockup in one row of compact tiles: what a
          deployment holds, before anything is said about it */}
      <Grid container spacing={1.5}>
        {isPending
          ? inventoryKpiResources.map(resource => (
            <Grid key={resource} size={KPI_SIZE}>
              <KpiSkeleton />
            </Grid>
          ))
          : kpiResources.map(resource => (
            <Grid key={resource} size={KPI_SIZE}>
              <ResourceListCard resource={resource} withList={false} compact />
            </Grid>
          ))}
      </Grid>
      {!isPending && (
        <Grid container spacing={2} sx={{ mt: 2 }}>
          {/* the two time series of the mockup: the audit events of the window
              (#1818) and the stock it verified (#1817), one half each */}
          <Grid size={{ xs: 12, md: 6 }}>
            <ActivityChart resources={kpiResources} period={period} />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <InventoryChart sources={inventory} />
          </Grid>
        </Grid>
      )}
      {!isPending && (
        <Grid container spacing={2} sx={{ mt: 2 }}>
          {/* the three panels of the mockup: how the inventory changed, how it is
              distributed, and whether the deployment does its work */}
          <Grid size={{ xs: 12, md: 4 }}>
            <DailyChangesChart sources={inventory} period={period} />
          </Grid>
          <Grid size={{ xs: 12, md: 4 }}>
            <InventoryDistributionCard sources={counts} />
          </Grid>
          <Grid size={{ xs: 12, md: 4 }}>
            <Stack spacing={2}>
              <WorkQueueCard />
              <ServiceAttentionCard />
            </Stack>
          </Grid>
        </Grid>
      )}
      {!isPending && (
        <Grid container spacing={2} sx={{ mt: 2 }}>
          {/* the two bounded tables of the bottom of the mockup: the notices of
              the deployment (#1819) beside the processes which run (#1815) */}
          <Grid size={{ xs: 12, md: 6 }}>
            <RecentNoticesCard resources={kpiResources} now={noticesNow} />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <BackgroundProcessesCard />
          </Grid>
        </Grid>
      )}
    </Box>
  );
};

export default Dashboard;
