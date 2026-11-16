import { type RaRecord } from "react-admin";

/**
 * The frontend contract of the operational incident api (#1321).
 *
 * The api itself is #1319 and not merged yet; epic #1104 explicitly allows
 * building the center against this contract before the publishers (#1320)
 * exist. Until the endpoint answers, every read of the incident windows ends
 * in an error - the data provider knows no `list_OperationalIncident`
 * operation - and the center stays silent (see IncidentCenterIndicator);
 * nothing here invents data.
 *
 * What the api owns and what the screens may assume:
 *
 * - ONE record per recurring incident: the server deduplicates by its stable
 *   key and folds retries into `occurrenceCount`, so ten retries of one
 *   incident are one row with an updated count - never ten notifications.
 *   The record `id` is that stable identity and the frontend key.
 * - Permission filtering is entirely server side: the visible count and the
 *   rows are the totals and records of the permitted list itself, so a
 *   private incident's title, id and any share of the count never reach a
 *   client which may not see it.
 * - `targetPath` is answered as a plain path only when the client is
 *   permitted to open the affected resource - the `targetPath` answer of
 *   ServiceAlert, which ListServiceAlert already navigates on. A row without
 *   the field has no destination and the client never derives one.
 * - `summary` is a safe, redacted human-readable message: no credentials,
 *   tokens or raw stack traces, as #1319 sanitizes it.
 * - `retryAttempt`/`retryTotal`/`nextRetryAt` are present only when the
 *   retry state is actually known; their absence is not zero.
 *
 * The fields are camelCase as the JSON:API layer exposes them, like every
 * other resource; the endpoint behind `INCIDENT_RESOURCE` is a list with the
 * `state` filter facet - the only term this UI puts into a query. Severity
 * and source filtering run over the bounded window client-side; they move to
 * the filterset once #1319 declares them there, because a `filter[...]` a
 * screen sends is an api contract (#1080) and an undeclared one is answered
 * with a 400, never ignored.
 */

/** the JSON:API type of the incident endpoint (#1319) */
export const INCIDENT_RESOURCE = "OperationalIncident";

/** the severity of an incident; the words of AttentionIndicator are reused,
 *  an operational incident is as severe as a service alert at most */
export type IncidentSeverity = "warning" | "error";

/** the lifecycle of an incident (#1319, epic #1104): temporarily retrying,
 *  suspected stalled (watchdog evidence, #1320), terminally failed, and
 *  resolved by recovery - a retry is not automatically a failure */
export type IncidentState = "retrying" | "stalled" | "failed" | "resolved";

/** the states which still ask for attention - a resolved incident left the
 *  active window and its count while it stays visible in the history */
export const ACTIVE_INCIDENT_STATES: readonly IncidentState[] = [
  "retrying",
  "stalled",
  "failed",
];

/** both severities, in the order the facet chips present them */
export const INCIDENT_SEVERITIES: readonly IncidentSeverity[] = [
  "warning",
  "error",
];

export interface OperationalIncidentRecord extends RaRecord {
  /** stable machine code, e.g. "harvest.chord_stalled" (#1319) */
  code: string;
  /** the domain which reported the incident, e.g. "harvesting"; the words
   *  live under incidentCenter.sources and fall back to the raw value */
  sourceType: string;
  severity: IncidentSeverity;
  state: IncidentState;
  /** safe human-readable message, redacted server-side */
  summary: string;
  /** the occurrences folded into this one incident, including the first */
  occurrenceCount: number;
  firstOccurrence: string;
  lastOccurrence: string;
  /** the retry state, answered only when known */
  retryAttempt?: number | null;
  retryTotal?: number | null;
  nextRetryAt?: string | null;
  /** the moment recovery resolved the incident */
  resolvedAt?: string | null;
  /** the path of the affected resource, answered only when permitted */
  targetPath?: string | null;
}

/** whether the incident left the active set */
export const isResolvedIncident = (
  record: OperationalIncidentRecord,
): boolean => record.state === "resolved";

/** the query of the active window; one read answers the badge, the tab label
 *  and the rows, so all of them agree with the same permitted result */
export const ACTIVE_INCIDENT_FILTER = {
  state: ACTIVE_INCIDENT_STATES.join(","),
} as const;

/** the query of the resolved window - recovery remains inspectable */
export const RESOLVED_INCIDENT_FILTER = { state: "resolved" } as const;

/** newest activity first, for both windows */
export const INCIDENT_SORT = {
  field: "lastOccurrence",
  order: "DESC",
} as const;

/** the bounded cadence the windows are re-read with (#1321: polling is
 *  bounded; the realtime bus may shorten the distance but never replaces
 *  this floor - unlike the job center the incident api may not push at all);
 *  the same distance the attention chip of ServiceAlert polls at */
export const INCIDENT_POLL_MILLISECONDS = 20000;

/** the rows each window answers; the drawer is an indicator's quick look,
 *  not the incident history screen - beyond the window the drawer says so
 *  instead of pretending the list were complete */
export const INCIDENT_WINDOW_SIZE = 25;
