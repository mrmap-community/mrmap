import { useMemo } from "react";
import { useGetList, type RaRecord } from "react-admin";

import { useHttpClientContext } from "../../context/HttpClientContext";
import useServiceAlerts from "../Resource/ServiceAlert/useServiceAlerts";
import {
  MAX_ROWS_PER_SOURCE,
  noticeWindow,
  type NoticeRow,
  type NoticeSource,
  type NoticeSourceStatus,
} from "./dashboardNotices";
import { hasDashboardHistory } from "./dashboardStatistics";

/** the resources the table audits: the same three whose dashboard history the
 *  activity chart (#1818) verifies, so one screen never claims an audit trail
 *  the other one reports as unverified */
export const noticeAuditResources = [
  "CatalogueService",
  "DatasetMetadataRecord",
  "ServiceMetadataRecord",
] as const;

/** whether an api error says the caller may not read what was asked for - the
 *  same reading of the http status by which the queues (#1816) and the system
 *  status (#833) decide: a read which is not allowed is an absent source, a
 *  read which merely failed is a problem of the deployment */
const isUnauthorized = (error: unknown): boolean => {
  const e = error as { status?: number; response?: { status?: number } };
  const status = e?.status ?? e?.response?.status;
  return status === 401 || status === 403;
};

/** the state a read answered, which is never guessed from a missing page */
const statusOf = (
  isPending: boolean,
  error: unknown,
  supported: boolean,
): NoticeSourceStatus => {
  if (!supported) return "unsupported";
  if (isPending) return "loading";
  if (error) return isUnauthorized(error) ? "forbidden" : "error";
  return "ready";
};

/** the text of a field the api answered, `null` when it answered none */
const textOf = (value: unknown): string | null =>
  typeof value === "string" && value !== "" ? value : null;

/** the rows of the attention card, which are records of `ServiceAlert` */
const alertRows = (data: RaRecord[] = []): NoticeRow[] =>
  data.map((record) => ({
    id: String(record.id),
    source: "ServiceAlert",
    origin: "alert",
    kind: textOf(record.severity) ?? "unknown",
    occurredAt: textOf(record.occurredAt),
    target: textOf(record.serviceTitle) ?? textOf(record.service) ?? String(record.id),
    link: { pathname: textOf(record.targetPath) ?? "/ServiceAlert/list" },
    category: textOf(record.category) ?? undefined,
    message: textOf(record.message) ?? undefined,
  }));

/** the rows of one audit trail: a row names the record it changed, never a
 *  reconstructed one, and carries no moment the api did not answer */
const auditRows = (resource: string, data: RaRecord[] = []): NoticeRow[] =>
  data.map((record) => {
    const relation = record.historyRelation as { id?: string | number } | undefined;
    return {
      id: String(record.id),
      source: resource,
      origin: "audit",
      kind: textOf(record.historyType) ?? "unknown",
      occurredAt: textOf(record.historyDate),
      target: textOf(record.title)
        ?? textOf(record.stringRepresentation)
        ?? (relation?.id !== undefined ? String(relation.id) : String(record.id)),
      link: { pathname: `/${resource}/${record.id}/show` },
      delta: Array.isArray(record.delta)
        ? (record.delta as { field: string }[]).map(({ field }) => ({ field }))
        : undefined,
    };
  });

/** the start of the bounded window as the changelog endpoint reads it: the
 *  first calendar day the card names, so the request is keyed by a date which
 *  does not move over the renders of a mount and answers exactly the window the
 *  subheader says */
const windowStartOf = (now: number): string => `${noticeWindow(now).from}T00:00:00Z`;

/**
 * The bounded read of one audit trail.
 *
 * One request answers the newest rows of the trail inside the window, sorted by
 * the api and bounded by the quota the merge gives a single source - the table
 * never downloads a changelog and never counts a page of one. A trail whose
 * operation the schema does not answer is `unsupported` and is asked nothing.
 */
const useAuditSource = (
  resource: string,
  resources: string[],
  since: string,
): NoticeSource => {
  const supported = resources.includes(resource) && hasDashboardHistory(resource);
  const { api } = useHttpClientContext();
  const hasTrail = Boolean(api?.getOperation(`list_Historical${resource}`));
  const { data, total, error, isPending } = useGetList(
    `Historical${resource}`,
    {
      pagination: { page: 1, perPage: MAX_ROWS_PER_SOURCE },
      // the order of the api, so the bounded page holds the newest rows
      sort: { field: "historyDate", order: "DESC" },
      // the dotted lookup of the changelog endpoint, which the data provider
      // answers for `_filter_lookup_` (#1080: a term the endpoint does not
      // declare is a 400, never an ignored parameter)
      filter: { historyDate_filter_lookup_gte: since },
    },
    { enabled: supported && hasTrail, retry: false },
  );
  const status = statusOf(isPending, error, supported && hasTrail);
  // a source which is loading, failed or refused answered nothing: rows of an
  // earlier read must not answer a table which says they could not be read
  return useMemo(() => ({
    resource,
    origin: "audit" as const,
    status,
    rows: status === "ready" ? auditRows(resource, data) : [],
    total: status === "ready" ? total : undefined,
  }), [resource, status, data, total]);
};

/**
 * The bounded reads behind the recent notices table (#1819).
 *
 * The attention of the services comes from `useServiceAlerts`, which the
 * attention card shares its react-query key with and which the realtime bus
 * invalidates; the changes come from the changelog of the three resources the
 * dashboard verifies its history over. Each source is asked for a bounded page
 * only, is never asked when the caller may not read it, and answers its own
 * state - so a source which is loading, refused or unsupported can be named by
 * the card instead of quietly missing from the table.
 *
 * `now` names the end of the window and comes from the caller, so the request
 * of a source is keyed by a date which does not move over the renders of one
 * mount: a window read from the clock of the render would answer a new query
 * key per render.
 */
export const useDashboardNotices = (
  resources: string[],
  now: number,
): NoticeSource[] => {
  const since = useMemo(() => windowStartOf(now), [now]);
  const alerts = useServiceAlerts();
  const catalogue = useAuditSource("CatalogueService", resources, since);
  const dataset = useAuditSource("DatasetMetadataRecord", resources, since);
  const service = useAuditSource("ServiceMetadataRecord", resources, since);
  return useMemo(() => {
    const audited = [catalogue, dataset, service]
      .filter((source) => resources.includes(source.resource));
    const alertsStatus = statusOf(alerts.isPending, alerts.error, true);
    const alertsSource: NoticeSource = {
      resource: "ServiceAlert",
      origin: "alert",
      status: alertsStatus,
      rows: alertsStatus === "ready" ? alertRows(alerts.data) : [],
      total: alertsStatus === "ready" ? alerts.total : undefined,
    };
    return [alertsSource, ...audited];
  }, [resources, alerts, catalogue, dataset, service]);
};
