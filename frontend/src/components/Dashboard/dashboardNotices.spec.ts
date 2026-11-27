import type { NoticeRow, NoticeSource } from "./dashboardNotices";

import { describe, expect, it } from "vitest";

import {
  dashboardNotices,
  MAX_NOTICE_ROWS,
  MAX_ROWS_PER_SOURCE,
  noticeWindow,
  NOTICE_WINDOW_DAYS,
} from "./dashboardNotices";

const NOW = Date.parse("2026-11-26T12:00:00Z");

const row = (overrides: Partial<NoticeRow> & { id: string; source: string }): NoticeRow => ({
  origin: "alert",
  kind: "warning",
  occurredAt: "2026-11-26T10:00:00Z",
  target: `record ${overrides.id}`,
  link: { pathname: `/ServiceAlert/${overrides.id}/show` },
  ...overrides,
});

const source = (
  resource: string,
  status: NoticeSource["status"],
  rows: NoticeRow[] = [],
  total?: number,
): NoticeSource => ({
  resource,
  origin: rows[0]?.origin ?? "alert",
  status,
  rows,
  total,
});

const ready = (resource: string, rows: NoticeRow[], total?: number): NoticeSource =>
  source(resource, "ready", rows, total);

/** the moments of the rows of the answer, newest first */
const momentsOf = (rows: NoticeRow[]): (string | null)[] => rows.map((r) => r.occurredAt);

/** the identifiers of the rows of the answer, in the order the table shows them */
const idsOf = (rows: NoticeRow[]): string[] => rows.map((r) => `${r.source}:${r.id}`);

describe("dashboard notices", () => {
  it("merges the sources of the deployment newest first", () => {
    const notices = dashboardNotices([
      ready("ServiceAlert", [
        row({ id: "a1", source: "ServiceAlert", occurredAt: "2026-11-25T08:00:00Z" }),
        row({ id: "a2", source: "ServiceAlert", occurredAt: "2026-11-26T09:00:00Z" }),
      ]),
      ready("CatalogueService", [
        row({ id: "c1", source: "CatalogueService", origin: "audit", kind: "updated", occurredAt: "2026-11-26T07:00:00Z" }),
      ]),
    ]);
    expect(notices.status).toBe("ready");
    if (notices.status !== "ready") return;
    expect(idsOf(notices.rows)).toEqual([
      "ServiceAlert:a2", "CatalogueService:c1", "ServiceAlert:a1",
    ]);
    expect(notices.unavailable).toEqual([]);
  });

  it("orders a source which answered out of order before it merges", () => {
    const notices = dashboardNotices([
      ready("ServiceAlert", [
        row({ id: "old", source: "ServiceAlert", occurredAt: "2026-11-20T08:00:00Z" }),
        row({ id: "new", source: "ServiceAlert", occurredAt: "2026-11-26T08:00:00Z" }),
      ]),
    ]);
    expect(notices.status).toBe("ready");
    if (notices.status !== "ready") return;
    expect(idsOf(notices.rows)).toEqual(["ServiceAlert:new", "ServiceAlert:old"]);
  });

  it("breaks a tie by the order of the sources and the identifier, deterministically", () => {
    const same = "2026-11-26T08:00:00Z";
    const build = (): NoticeRow[] => [
      row({ id: "b", source: "ServiceAlert", occurredAt: same }),
      row({ id: "a", source: "ServiceAlert", occurredAt: same }),
    ];
    const first = dashboardNotices([
      ready("ServiceAlert", build()),
      ready("CatalogueService", [row({ id: "z", source: "CatalogueService", origin: "audit", occurredAt: same })]),
    ]);
    const second = dashboardNotices([
      ready("ServiceAlert", [...build()].reverse()),
      ready("CatalogueService", [row({ id: "z", source: "CatalogueService", origin: "audit", occurredAt: same })]),
    ]);
    expect(first.status).toBe("ready");
    expect(second.status).toBe("ready");
    if (first.status !== "ready" || second.status !== "ready") return;
    // the merge is reproducible whatever order a source answered its rows in
    expect(idsOf(first.rows)).toEqual(idsOf(second.rows));
    // the alerts answer before the audit rows of the same moment, because the
    // card asks them first
    expect(idsOf(first.rows)).toEqual([
      "ServiceAlert:a", "ServiceAlert:b", "CatalogueService:z",
    ]);
  });

  it("answers a row the api does not date last, never with an invented moment", () => {
    const notices = dashboardNotices([
      ready("ServiceAlert", [
        row({ id: "undated", source: "ServiceAlert", occurredAt: null }),
        row({ id: "dated", source: "ServiceAlert", occurredAt: "2026-11-20T08:00:00Z" }),
      ]),
    ]);
    expect(notices.status).toBe("ready");
    if (notices.status !== "ready") return;
    expect(momentsOf(notices.rows)).toEqual(["2026-11-20T08:00:00Z", null]);
  });

  it("treats a moment the api answered unusably as no moment", () => {
    const notices = dashboardNotices([
      ready("ServiceAlert", [
        row({ id: "garbage", source: "ServiceAlert", occurredAt: "yesterday" }),
      ]),
    ]);
    expect(notices.status).toBe("ready");
    if (notices.status !== "ready") return;
    expect(notices.rows[0].occurredAt).toBe("yesterday");
  });

  it("bounds every source by its quota and the table by its limit", () => {
    const many = (resource: string, count: number): NoticeRow[] =>
      Array.from({ length: count }, (_, index) => row({
        id: `${resource}-${index}`,
        source: resource,
        origin: "audit",
        occurredAt: new Date(NOW - index * 3600000).toISOString(),
      }));
    const notices = dashboardNotices([
      ready("ServiceAlert", many("ServiceAlert", 10), 40),
      ready("CatalogueService", many("CatalogueService", 10), 10),
      ready("DatasetMetadataRecord", many("DatasetMetadataRecord", 10), 10),
      ready("ServiceMetadataRecord", many("ServiceMetadataRecord", 10), 10),
    ]);
    expect(notices.status).toBe("ready");
    if (notices.status !== "ready") return;
    expect(notices.rows.length).toBeLessThanOrEqual(MAX_NOTICE_ROWS);
    const perSource = notices.rows.reduce<Record<string, number>>((counts, entry) => {
      counts[entry.source] = (counts[entry.source] ?? 0) + 1;
      return counts;
    }, {});
    // a chatty source cannot crowd the notices of the others out
    for (const resource of Object.keys(perSource)) {
      expect(perSource[resource]).toBeLessThanOrEqual(MAX_ROWS_PER_SOURCE);
    }
    expect(notices.truncated).toBe(true);
  });

  it("says truncation only when a source holds more than the table shows", () => {
    const few = dashboardNotices([
      ready("ServiceAlert", [row({ id: "a", source: "ServiceAlert" })], 1),
    ]);
    expect(few.status).toBe("ready");
    if (few.status !== "ready") return;
    expect(few.truncated).toBe(false);

    const more = dashboardNotices([
      ready("ServiceAlert", [row({ id: "a", source: "ServiceAlert" })], 7),
    ]);
    expect(more.status).toBe("ready");
    if (more.status !== "ready") return;
    expect(more.truncated).toBe(true);
  });

  it("names every source which did not answer instead of dropping it", () => {
    const notices = dashboardNotices([
      source("ServiceAlert", "forbidden"),
      ready("CatalogueService", [row({ id: "c1", source: "CatalogueService", origin: "audit" })]),
      source("DatasetMetadataRecord", "error"),
      source("ServiceMetadataRecord", "unsupported"),
    ]);
    expect(notices.status).toBe("ready");
    if (notices.status !== "ready") return;
    expect(notices.unavailable).toEqual([
      { resource: "ServiceAlert", status: "forbidden" },
      { resource: "DatasetMetadataRecord", status: "error" },
      { resource: "ServiceMetadataRecord", status: "unsupported" },
    ]);
  });

  it("keeps loading, failing, refused and unsupported answers apart", () => {
    expect(dashboardNotices([source("ServiceAlert", "loading")]).status).toBe("loading");
    expect(dashboardNotices([source("ServiceAlert", "error")]).status).toBe("error");
    expect(dashboardNotices([source("ServiceAlert", "forbidden")]).status).toBe("forbidden");
    expect(dashboardNotices([source("ServiceAlert", "unsupported")]).status).toBe("unsupported");
    expect(dashboardNotices([]).status).toBe("unsupported");
    // a read which merely failed is a problem of the deployment and says so,
    // it never answers the emptiness of a deployment without notices
    expect(dashboardNotices([
      source("ServiceAlert", "error"),
      source("CatalogueService", "loading"),
    ]).status).toBe("error");
    // a caller who may read nothing sees no table
    expect(dashboardNotices([
      source("ServiceAlert", "forbidden"),
      source("CatalogueService", "unsupported"),
    ]).status).toBe("forbidden");
  });

  it("answers readiness while a single source is still readable", () => {
    const notices = dashboardNotices([
      source("ServiceAlert", "loading"),
      ready("CatalogueService", [row({ id: "c1", source: "CatalogueService", origin: "audit" })]),
    ]);
    expect(notices.status).toBe("ready");
    if (notices.status !== "ready") return;
    expect(notices.rows).toHaveLength(1);
    expect(notices.unavailable).toEqual([{ resource: "ServiceAlert", status: "loading" }]);
  });

  it("names the bounded window the table answers, in calendar days", () => {
    expect(noticeWindow(NOW)).toEqual({
      from: "2026-11-20",
      to: "2026-11-26",
    });
    expect(NOTICE_WINDOW_DAYS).toBe(7);
  });

  it("keeps the window a whole number of calendar days across the clock change", () => {
    const spread = (now: number): number => {
      const { from, to } = noticeWindow(now);
      return (Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86400000 + 1;
    };
    // 2026-03-28/29 is the German clock change: the day lengths differ, the
    // number of calendar days the table names must not
    expect(spread(Date.parse("2026-03-28T23:30:00Z"))).toBe(NOTICE_WINDOW_DAYS);
    expect(spread(Date.parse("2026-03-29T23:30:00Z"))).toBe(NOTICE_WINDOW_DAYS);
  });
});
