/**
 * The recent notices of the dashboard (#1819).
 *
 * The table answers the newest notices of the deployment out of the sources the
 * caller is authorized to read: the attention of its services and the audit
 * trail of its services and metadata records. Nothing here reads an api - the
 * module merges what the hooks answered, so the ordering and the states of the
 * card are testable without react-admin and cannot disagree with the card.
 *
 * Three rules keep the answer honest:
 *
 * - nothing is invented: a row is the record of a source and carries only what
 *   that record answered; a row without a moment is never given one;
 * - nothing is unbounded: every source is asked for a bounded page and
 *   contributes a bounded number of rows, so one chatty source cannot crowd the
 *   notices of the others out and the table cannot grow over its region;
 * - nothing is silently missing: a source which is loading, which failed, which
 *   the caller may not read or which the deployment does not answer is reported
 *   as unavailable instead of vanishing from the table.
 */

/** the days of changes the table asks for: the bounded window of the mockup row */
export const NOTICE_WINDOW_DAYS = 7;

/** the rows the table answers at most, however many sources read */
export const MAX_NOTICE_ROWS = 8;

/** the rows one source may contribute, so a chatty source cannot fill the table */
export const MAX_ROWS_PER_SOURCE = 3;

/** the milliseconds of one day, the arithmetic of the bounded window */
const DAY_MS = 86400000;

/** what a source answered about itself, which is never a count of its rows */
export type NoticeSourceStatus =
  | "ready"
  | "loading"
  | "error"
  | "forbidden"
  | "unsupported";

/** where a row comes from: the attention of a service or the audit trail */
export type NoticeOrigin = "alert" | "audit";

/** the link of a row, the shape the react-admin `Link` of the project accepts */
export interface NoticeLink {
  pathname: string;
  search?: string;
}

/** one notice, which is one record of one source and nothing else */
export interface NoticeRow {
  /** the identifier of the record behind the row, unique within its source */
  id: string;
  /** the JSON:API type of the row: `ServiceAlert` or the audited resource */
  source: string;
  origin: NoticeOrigin;
  /** the kind of the row: the severity of an alert, the history type of an event */
  kind: string;
  /** the moment of the notice, null when the api does not answer one */
  occurredAt: string | null;
  /** the affected service or record, named as the api names it */
  target: string;
  /** the record behind the notice */
  link: NoticeLink;
  /** an alert only: the category the api of the alerts answers */
  category?: string;
  /** an alert only: its message, which says more than the category can */
  message?: string;
  /** an audit row only: the fields the record changed */
  delta?: { field: string }[];
}

/** what one source of the table answered */
export interface NoticeSource {
  /** the JSON:API type of the source, which is also its translation scope */
  resource: string;
  origin: NoticeOrigin;
  status: NoticeSourceStatus;
  /** the rows of the source as it answered them, in any order */
  rows?: NoticeRow[];
  /** the records the source holds, when its answer knows them */
  total?: number;
}

/** the answer of the table */
export type Notices =
  | { status: Exclude<NoticeSourceStatus, "ready"> }
  | {
      status: "ready";
      /** the rows of the table, newest first, bounded by `limit` */
      rows: NoticeRow[];
      /** the sources which did not answer, which the card names one by one */
      unavailable: { resource: string; status: NoticeSourceStatus }[];
      /** whether the sources hold more notices than the table shows */
      truncated: boolean;
    };

/** the yyyy-mm-dd of a moment, which is what the window of the card names */
const dayOf = (moment: number): string =>
  new Date(moment).toISOString().slice(0, 10);

/**
 * The window the audit sources are asked for.
 *
 * The bounded period the table reads is said by the card, because a table of
 * the last week of notices is not the activity of the deployment; the window is
 * derived from the moment of the read so header and rows always answer the same
 * days.
 */
export const noticeWindow = (now: number): { from: string; to: string } => ({
  from: dayOf(now - (NOTICE_WINDOW_DAYS - 1) * DAY_MS),
  to: dayOf(now),
});

/** the moment a row happened, `null` for anything the api does not date */
const momentOf = (row: NoticeRow): number | null => {
  if (row.occurredAt === null) return null;
  const moment = Date.parse(row.occurredAt);
  return Number.isNaN(moment) ? null : moment;
};

/** the order of two rows: newest first, a row without a moment last, then the
 *  order the sources were asked in and finally the identifier of the record -
 *  the stable tie-break which makes one answer reproducible */
const compareRows = (
  order: Map<string, number>,
): ((a: NoticeRow, b: NoticeRow) => number) => {
  return (a, b) => {
    const first = momentOf(a);
    const second = momentOf(b);
    if (first !== second) {
      if (first === null) return 1;
      if (second === null) return -1;
      return second - first;
    }
    const sources = (order.get(a.source) ?? 0) - (order.get(b.source) ?? 0);
    if (sources !== 0) return sources;
    if (a.id === b.id) return 0;
    return a.id < b.id ? -1 : 1;
  };
};

export interface NoticesOptions {
  /** the rows the table answers at most */
  limit?: number;
  /** the rows one source may contribute */
  quota?: number;
}

/**
 * The recent notices of the deployment, merged from the sources which answered.
 *
 * Every source is ordered by its own moments first, so a source which answered
 * out of order cannot push an older notice above a newer one; its newest
 * `quota` rows then enter the merge, which orders all candidates by their
 * moment and breaks a tie by the order the sources were asked in and by the
 * identifier of the record. The merge is bounded by `limit` and never sums,
 * renames or completes anything: what no source answered, the table does not
 * know. A source the caller may not read is not an empty source and is never
 * counted as one.
 *
 * This is the bounded alternative to a merge over the whole history, which the
 * api of the alerts and of the changelogs does not answer efficiently: each
 * source is read as its own newest page - ordered by the api - so the merge
 * costs the quota of every source instead of the size of the changelogs. What
 * that bound costs the reader is said by `truncated`.
 */
export const dashboardNotices = (
  sources: NoticeSource[],
  { limit = MAX_NOTICE_ROWS, quota = MAX_ROWS_PER_SOURCE }: NoticesOptions = {},
): Notices => {
  if (!sources.length) return { status: "unsupported" };
  const answers = sources.map((source) => source.status);
  const readable = sources.filter((source) => source.status === "ready");
  if (!readable.length) {
    // a read which merely failed is a problem of the deployment and says so; a
    // caller who may read nothing sees no table at all; a source which is out
    // is waited for before the table answers an empty deployment
    if (answers.includes("error")) return { status: "error" };
    if (answers.includes("loading")) return { status: "loading" };
    if (answers.includes("forbidden")) return { status: "forbidden" };
    return { status: "unsupported" };
  }

  const order = new Map(sources.map((source, index) => [source.resource, index]));
  const byMoment = compareRows(order);
  const candidates: NoticeRow[] = [];
  let truncated = false;
  for (const source of readable) {
    const rows = [...(source.rows ?? [])].sort(byMoment);
    candidates.push(...rows.slice(0, quota));
    // the source holds more notices than the table shows once its own count
    // says so, or once it answered more rows than the merge may take from it
    const held = source.total ?? rows.length;
    if (held > rows.length || rows.length > quota) truncated = true;
  }
  const rows = candidates.sort(byMoment).slice(0, limit);
  if (candidates.length > limit) truncated = true;

  return {
    status: "ready",
    rows,
    unavailable: sources
      .filter((source) => source.status !== "ready")
      .map(({ resource, status }) => ({ resource, status })),
    truncated,
  };
};
