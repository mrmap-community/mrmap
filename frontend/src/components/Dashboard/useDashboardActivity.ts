import type { ActivitySource } from "./dashboardActivity";
import type { DashboardPeriod } from "./dashboardStatistics";

import { useGetList } from "react-admin";

import { useDashboardStatistics } from "./useDashboardStatistics";

const useActivitySource = (resource: string, resources: string[], period: DashboardPeriod): ActivitySource => {
  const enabled = resources.includes(resource);
  // Matches ResourceListCard's count-only ListBase query, including its sparse fieldset.
  const count = useGetList(resource, {
    pagination: { page: 1, perPage: 1 },
    sort: { field: "id", order: "ASC" },
    filter: {},
    meta: { jsonApiParams: { [`fields[${resource}]`]: "id" } },
  }, { enabled });
  const statistics = useDashboardStatistics(resource, count, period, enabled);
  return { resource, statistics };
};

/** Keep observers mounted when filters change; the KPI cards share these query keys. */
export const useDashboardActivity = (resources: string[], period: DashboardPeriod): ActivitySource[] => {
  const catalogue = useActivitySource("CatalogueService", resources, period);
  const dataset = useActivitySource("DatasetMetadataRecord", resources, period);
  const service = useActivitySource("ServiceMetadataRecord", resources, period);
  return [catalogue, dataset, service].filter(source => resources.includes(source.resource));
};
