import { type RaRecord } from "react-admin";

/**
 * The frontend contract of the operational incident api (#1321).
 *
 * The api is the read-only, permission-filtered `operational-incidents`
 * endpoint of #1319; its publishers are the retry/failure reporters and the
 * stalled-work watchdog of #1320. The fields below are the attributes the
 * OperationalIncidentSerializer answers, in the camelCase the JSON:API layer
 * exposes them; `status`, `severity`, `source` and `code` are declared
 * facets of its filterset and `lastOccurredAt` is a declared ordering field
 * of its viewset - the windows ask with `status` and that sort alone, the
 * only terms this center puts into a query (#1080).
 *
 * What the api owns and what the screens may assume:
 *
 * - ONE record per recurring incident: the server deduplicates by its stable
 *   key and folds retries into `occurrenceCount`, so ten retries of one
 *   incident are one row with an updated count - never ten notifications.
 *   The record `id` is a uuid and the frontend key.
 * - Permission filtering is entirely server side: the visible count and the
 *   rows are the totals and records of the permitted list itself, so a
 *   private incident's title, id and any share of the count never reach a
 *   client which may not see it.
 * - `affectedResource` names the resource the incident stands for by type
 *   and id - empty for a system incident. Because the list itself answers
 *   only incidents of resources the caller may view (#1319), every answered
 *   pair is also one the caller may open: the row links to that resource's
 *   show view. No path is ever derived from the code, the source or a
 *   half-known identifier.
 * - `summary` is a safe, redacted human-readable message: no credentials,
 *   tokens or raw stack traces, as #1319 sanitizes it.
 * - `retryCount` and `retryScheduledUntil` are as truthful as the reported
 *   operation's last report; an absent next attempt is not "no retry" and
 *   a count of zero is the number the operation told, not a guess.
 *
 * The lifecycle the api itself answers is two states - `active` while the
 * problem stands, `resolved` once recovery resolved it. #1321 shows the
 * operator four: `incidentDisplayState` reads the distinction the epic asks
 * for out of fields the server answers - a watchdog verdict (the code family
 * of #1320) is suspected stalled, an active `error` is an operation which
 * stands and an active `warning` one which still moves and retries, in the
 * api's own words about severity. Nothing here asks the endpoint for a
 * facet it does not declare.
 */

/** the JSON:API type of the incident endpoint (#1319) */
export const INCIDENT_RESOURCE = "OperationalIncident";

/** the severity of an incident; the words of AttentionIndicator are reused,
 *  an operational incident is as severe as a service alert at most */
export type IncidentSeverity = "warning" | "error";

/** the lifecycle the api stores (#1319): active while the problem stands,
 *  resolved once recovery resolved it - terminal in both directions */
export type IncidentStatus = "active" | "resolved";

/** the lifecycle the operator is shown (#1104): what of the active rows
 *  retries, what the watchdog suspects of standing still, what stands
 *  terminally and what recovery resolved */
export type IncidentDisplayState =
  | "retrying"
  | "stalled"
  | "failed"
  | "resolved";

/** the code prefix the watchdog verdicts of #1320 share - the frontend
 *  mirror of `WATCHDOG_CODE_PREFIX` in `notify/incident_reporting.py`: an
 *  expired retry window, a queue without a consumer. No other code family
 *  starts with it, which is why the prefix alone is a safe reading */
export const WATCHDOG_CODE_PREFIX = "operational_";

/** the display states which still ask for attention - a resolved incident
 *  left the active window and its count while it stays visible in the history */
export const ACTIVE_INCIDENT_DISPLAY_STATES: readonly IncidentDisplayState[] =
  ["retrying", "stalled", "failed"];

/** both severities, in the order the facet chips present them */
export const INCIDENT_SEVERITIES: readonly IncidentSeverity[] = [
  "warning",
  "error",
];

export interface OperationalIncidentRecord extends RaRecord {
  /** the uuid of the incident; the stable identity the drawer keys its rows by */
  id: string;
  /** stable machine code - `{process_type}_{task}` for an operation, the
   *  watchdog family for a verdict; integrations refer to codes, never to
   *  worded messages, so the row shows the code as the api answers it */
  code: string;
  /** the domain which raised the incident - harvesting, update, monitoring
   *  or the deployment itself; the words live under incidentCenter.sources
   *  and fall back to the raw value */
  source: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  /** whether the incident names an affected resource or reports about the
   *  deployment itself - a system incident has no destination to open */
  scope: "resource" | "system";
  /** the resource the incident stands for, answered for permitted incidents
   *  alone; empty for a system incident */
  affectedResource?: { type: string; id: string } | null;
  /** safe human-readable message, redacted server-side */
  summary: string;
  /** redacted, bounded structured metadata; the full evidence stays in the
   *  log of the reported process, so the drawer never renders it */
  details?: Record<string, unknown> | null;
  firstOccurredAt: string;
  lastOccurredAt: string;
  /** the occurrences folded into this one incident, including the first */
  occurrenceCount: number;
  /** the retries the reported operation told with its last report */
  retryCount?: number;
  /** until when the next attempt is due; while it lies ahead the incident
   *  reports a retry, not a failure */
  retryScheduledUntil?: string | null;
  /** the moment recovery resolved the incident */
  resolvedAt?: string | null;
}

/** whether the incident left the active set */
export const isResolvedIncident = (
  record: OperationalIncidentRecord,
): boolean => record.status === "resolved";

/** the display state of one incident, read from the fields the api answers:
 *  recovery resolved it; the watchdog of #1320 raised a verdict over it; it
 *  stands as an error; or it is a warning while the reported operation still
 *  moves, which for the reporters of #1320 means between attempts (#1104) */
export const incidentDisplayState = (
  record: OperationalIncidentRecord,
): IncidentDisplayState => {
  if (record.status === "resolved") {
    return "resolved";
  }
  if (record.code.startsWith(WATCHDOG_CODE_PREFIX)) {
    return "stalled";
  }
  if (record.severity === "error") {
    return "failed";
  }
  return "retrying";
};

/** the query of the active window; one read answers the badge, the tab label
 *  and the rows, so all of them agree with the same permitted result */
export const ACTIVE_INCIDENT_FILTER = { status: "active" } as const;

/** the query of the resolved window - recovery remains inspectable */
export const RESOLVED_INCIDENT_FILTER = { status: "resolved" } as const;

/** newest activity first, for both windows; the history tab reads the same
 *  field and the api also declares `resolvedAt` for a resolved-only sort */
export const INCIDENT_SORT = {
  field: "lastOccurredAt",
  order: "DESC",
} as const;

/** the bounded cadence the windows are re-read with (#1321: polling is
 *  bounded; the realtime bus may shorten the distance but never replaces
 *  this floor - the publishers of #1320 do not announce on it yet);
 *  the same distance the attention chip of ServiceAlert polls at */
export const INCIDENT_POLL_MILLISECONDS = 20000;

/** the rows each window answers; the drawer is an indicator's quick look,
 *  not the incident history screen - beyond the window the drawer says so
 *  instead of pretending the list were complete */
export const INCIDENT_WINDOW_SIZE = 25;
