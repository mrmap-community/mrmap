import type { DashboardPeriod } from "./dashboardStatistics";

import { useCallback, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { inventoryKpiResources } from "./useDashboardInventory";

/** the periods the single shared selector of the dashboard offers (#1820) */
export const DASHBOARD_PERIODS = [7, 30, 90] as const;

/** the period a first read of the dashboard verifies over */
export const DEFAULT_DASHBOARD_PERIOD: DashboardPeriod = 30;

/** the resources the dashboard reads, which one refresh re-reads together: the
 *  inventories and their daily statistics, the audit trails and the alerts of
 *  the notices, the windows of the job center and the state of the deployment */
const DASHBOARD_READS = new Set<string>([
  ...inventoryKpiResources,
  ...inventoryKpiResources.map(resource => `Statistical${resource}`),
  "CatalogueService", "DatasetMetadataRecord", "ServiceMetadataRecord",
  "HistoricalCatalogueService", "HistoricalDatasetMetadataRecord", "HistoricalServiceMetadataRecord",
  "ServiceAlert", "BackgroundProcess", "SystemStatus",
]);

/**
 * The single period and refresh of the dashboard (#1820).
 *
 * The period belongs to the screen and not to a card: the KPI tiles, the two
 * time series, the stacked daily changes and the donut all verify the same
 * window, so the header answers one selector and every card reads it. The state
 * deliberately stays in the dashboard and never reaches the location — the
 * layout renders `Dashboard` outside a route which carries list parameters, and
 * a period is presentation, not a bookmarkable query.
 *
 * The refresh invalidates the queries of the screen alone: a card which
 * refreshed for itself would leave the others answering an older window beside
 * it, which is what the single selector exists to prevent, and a refresh of
 * every query of the app would re-read the OpenAPI schema and the permissions
 * for a change of one number. A new period needs no refresh at all — the key of
 * a statistics read carries the window it was verified over, so the cards ask
 * exactly the window their period names.
 *
 * The moment of the last refresh is the moment of the click, which is the
 * honest one: the screen says when it last re-read the deployment, and each card
 * alone knows whether its own read came back.
 */
export const useDashboardPeriod = () => {
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState<DashboardPeriod>(DEFAULT_DASHBOARD_PERIOD);
  const [refreshedAt, setRefreshedAt] = useState<number | null>(null);

  const refresh = useCallback(() => {
    queryClient.invalidateQueries({
      predicate: query => Array.isArray(query.queryKey) && DASHBOARD_READS.has(String(query.queryKey[0])),
    });
    setRefreshedAt(Date.now());
  }, [queryClient]);

  return { period, setPeriod, refresh, refreshedAt };
};
