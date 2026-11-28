import type { InventoryCountSource, InventorySource } from "./dashboardInventory";
import type { DashboardPeriod } from "./dashboardStatistics";

import { useGetList } from "react-admin";

import { useDashboardStatistics } from "./useDashboardStatistics";

/** the seven inventory kinds of the dashboard, in the order the mockup answers them */
export const inventoryKpiResources = [
  "WebMapService",
  "Layer",
  "WebFeatureService",
  "FeatureType",
  "CatalogueService",
  "DatasetMetadataRecord",
  "ServiceMetadataRecord",
] as const;

/** the count-only read of one resource, identical to the one of `ResourceListCard` */
const useInventoryCount = (resource: string, resources: string[]) => {
  // Matches ResourceListCard's count-only ListBase query, including its sparse fieldset.
  return useGetList(resource, {
    pagination: { page: 1, perPage: 1 },
    sort: { field: "id", order: "ASC" },
    filter: {},
    meta: { jsonApiParams: { [`fields[${resource}]`]: "id" } },
  }, { enabled: resources.includes(resource) });
};

const useInventorySource = (
  resource: string,
  resources: string[],
  period: DashboardPeriod,
): InventorySource => {
  const enabled = resources.includes(resource);
  const count = useInventoryCount(resource, resources);
  const statistics = useDashboardStatistics(resource, count, period, enabled);
  if (statistics.status !== "ready") return { resource, status: statistics.status };
  return { resource, status: "ready", days: statistics.days, count: count.total };
};

/**
 * The verified stock and the registered counts of every inventory kind.
 *
 * The three complementary charts of the dashboard (#1820) read their numbers
 * from mounts of this hook, which asks the same two queries per resource the
 * KPI cards (#1817) and the activity chart (#1818) ask: the count-only list of
 * the resource and the daily statistics of it. One screen therefore reads each
 * of them once, whatever it draws.
 */
export const useDashboardInventory = (
  resources: string[],
  period: DashboardPeriod,
): InventorySource[] => {
  const services = useInventorySource("WebMapService", resources, period);
  const layers = useInventorySource("Layer", resources, period);
  const features = useInventorySource("WebFeatureService", resources, period);
  const featureTypes = useInventorySource("FeatureType", resources, period);
  const catalogue = useInventorySource("CatalogueService", resources, period);
  const dataset = useInventorySource("DatasetMetadataRecord", resources, period);
  const records = useInventorySource("ServiceMetadataRecord", resources, period);
  return [services, layers, features, featureTypes, catalogue, dataset, records]
    .filter(source => resources.includes(source.resource));
};

const useInventoryCountSource = (
  resource: string,
  resources: string[],
): InventoryCountSource => {
  const { total, isPending, error } = useInventoryCount(resource, resources);
  if (!resources.includes(resource)) return { resource, status: "unsupported" };
  if (isPending) return { resource, status: "loading" };
  if (error) return { resource, status: "error" };
  if (total === undefined) return { resource, status: "partial" };
  return { resource, status: "ready", count: total };
};

/**
 * The registered counts of every inventory kind today.
 *
 * The donut answers an inventory, not a history: a resource without verified
 * statistics (#1817) still counts today, so this reads the count-only list of
 * each kind alone. Those are the very queries the KPI cards ask, which is why
 * the donut costs the screen nothing of its own.
 */
export const useDashboardCounts = (resources: string[]): InventoryCountSource[] => {
  const services = useInventoryCountSource("WebMapService", resources);
  const layers = useInventoryCountSource("Layer", resources);
  const features = useInventoryCountSource("WebFeatureService", resources);
  const featureTypes = useInventoryCountSource("FeatureType", resources);
  const catalogue = useInventoryCountSource("CatalogueService", resources);
  const dataset = useInventoryCountSource("DatasetMetadataRecord", resources);
  const records = useInventoryCountSource("ServiceMetadataRecord", resources);
  return [services, layers, features, featureTypes, catalogue, dataset, records]
    .filter(source => resources.includes(source.resource));
};
