import { useGetList } from "react-admin";

import { useHttpClientContext } from "../../context/HttpClientContext";
import {
  dashboardStatistics, dashboardToday, hasDashboardHistory,
  type DashboardPeriod, type DashboardStatistics,
} from "./dashboardStatistics";

/** The count comes from the card's authorized resource list query. */
export const useDashboardStatistics = (
  resource: string,
  count: {
    total?: number;
    isPending: boolean;
    error?: unknown;
    filterValues?: Record<string, unknown>;
  },
  period: DashboardPeriod = 30,
  enabled = true,
): DashboardStatistics => {
  const { api, isPending, error } = useHttpClientContext();
  const supported = enabled && hasDashboardHistory(resource)
    && Object.keys(count.filterValues ?? {}).length === 0
    && Boolean(api?.getOperation(`list_Statistical${resource}`));
  const today = dashboardToday();
  const history = useGetList(`Statistical${resource}`, {
    sort: { field: "id", order: "DESC" },
    pagination: { page: 1, perPage: 90 },
    meta: { dashboardDay: today },
  }, { enabled: supported });
  if (error) return { status: "error" };
  if (isPending) return { status: "loading" };
  if (!supported) return { status: "unsupported" };
  if (history.error || count.error) return { status: "error" };
  if (count.isPending || history.isPending || history.isPlaceholderData) return { status: "loading" };
  if (!history.data) return { status: "partial" };
  return dashboardStatistics(history.data, history.total, count.total, period, today);
};
