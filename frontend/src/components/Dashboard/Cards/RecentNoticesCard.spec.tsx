import type { NoticeRow, NoticeSource } from "../dashboardNotices";

import type { ReactNode } from "react";

import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import de from "../../../i18n/de";
import en from "../../../i18n/en";
import RecentNoticesCard from "./RecentNoticesCard";

const state = vi.hoisted(() => ({
  sources: [] as NoticeSource[],
  locale: "en",
  asked: [] as string[],
}));

const lookup = (key: string) => {
  let value: unknown = state.locale === "de" ? de : en;
  for (const part of key.split(".")) value = (value as Record<string, unknown>)?.[part];
  return typeof value === "string" ? value : key;
};

vi.mock("react-admin", () => ({
  useLocaleState: () => [state.locale],
  useCreatePath: () => ({ resource }: { resource: string }) => `/${resource}/list`,
  useTranslate: () => (key: string, options: Record<string, unknown> = {}) => {
    const message = lookup(key);
    return (message === key ? String(options._ ?? key) : message)
      .replace(/%\{(\w+)\}/g, (_all: string, name: string) => String(options[name]));
  },
  // the card composes its links over react-admin's Link; the mock resolves the
  // target the router would follow - a string or a path object - so the
  // assertions read the real entrances of the card
  Link: ({ to, children }: { to: string | { pathname: string; search?: string }; children?: ReactNode }) => (
    <a href={typeof to === "string" ? to : `${to.pathname}${to.search ?? ""}`}>{children}</a>
  ),
}));

vi.mock("../useDashboardNotices", () => ({
  useDashboardNotices: (resources: string[]) => {
    state.asked = resources;
    return state.sources;
  },
}));

const NOW = Date.parse("2026-11-26T12:00:00Z");
const ALL = ["CatalogueService", "DatasetMetadataRecord", "ServiceMetadataRecord"];

const alertRow = (overrides: Partial<NoticeRow> = {}): NoticeRow => ({
  id: "a1",
  source: "ServiceAlert",
  origin: "alert",
  kind: "error",
  occurredAt: "2026-11-26T09:00:00Z",
  target: "Weather service",
  link: { pathname: "/CatalogueService/c1/show" },
  ...overrides,
});

const auditRow = (overrides: Partial<NoticeRow> = {}): NoticeRow => ({
  id: "h1",
  source: "CatalogueService",
  origin: "audit",
  kind: "updated",
  occurredAt: "2026-11-26T08:00:00Z",
  target: "Catalogue of things",
  link: { pathname: "/CatalogueService/h1/show" },
  delta: [{ field: "title" }],
  ...overrides,
});

const answered = (resource: string, rows: NoticeRow[], total?: number): NoticeSource => ({
  resource,
  origin: rows[0]?.origin ?? (resource === "ServiceAlert" ? "alert" : "audit"),
  status: "ready",
  rows,
  total,
});

const stateOf = (
  resource: string,
  status: NoticeSource["status"],
  origin: NoticeSource["origin"] = resource === "ServiceAlert" ? "alert" : "audit",
): NoticeSource => ({ resource, origin, status });

const renderCard = (resources: string[] = ALL) =>
  render(<RecentNoticesCard resources={resources} now={NOW} />);

/** the first column of every body row, in the order the table shows them */
const momentsShown = (table: HTMLElement) =>
  within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[0].textContent ?? "");

beforeEach(() => {
  state.locale = "en";
  state.sources = [];
  state.asked = [];
});

describe("RecentNoticesCard", () => {
  it("answers the bounded window, the merged rows and their entrances", () => {
    state.sources = [
      answered("ServiceAlert", [alertRow({ category: "harvest_aborted", message: "harvest_aborted" })], 1),
      answered("CatalogueService", [auditRow()], 1),
      stateOf("DatasetMetadataRecord", "loading"),
    ];
    renderCard();

    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      en.dashboard.notices.title,
    );
    // the period the sources were asked for is said, so a bounded table is
    // never read as the whole activity of the deployment
    expect(screen.getByText(/20 Nov 2026/)).toBeInTheDocument();
    expect(screen.getByText(/26 Nov 2026/)).toBeInTheDocument();

    const table = screen.getByRole("table");
    // the rows of both sources, newest first, over both kinds of notice
    expect(momentsShown(table)).toEqual(["26 Nov, 09:00", "26 Nov, 08:00"]);
    // the alert answers its severity, the audit row the field it changed
    expect(screen.getByRole("columnheader", { name: en.dashboard.notices.columns.time }))
      .toBeInTheDocument();
    expect(screen.getByText(en.serviceAlerts.error)).toBeInTheDocument();
    expect(screen.getByText(en.historyList.updated)).toBeInTheDocument();
    expect(screen.getByText("Title changed")).toBeInTheDocument();
    // a row links to the record behind it, never to a copy of that record
    expect(screen.getByRole("link", { name: "Weather service" })).toHaveAttribute(
      "href", "/CatalogueService/c1/show",
    );
    expect(screen.getByRole("link", { name: "Catalogue of things" })).toHaveAttribute(
      "href", "/CatalogueService/h1/show",
    );
    // the entrances to the screens the rows come out of
    expect(screen.getByRole("link", { name: en.serviceAlerts.viewAll })).toHaveAttribute(
      "href", "/ServiceAlert/list",
    );
    // a source which is still being read is named beside the rows it misses,
    // it never vanishes from the table
    expect(screen.getByRole("status")).toHaveTextContent(
      en.dashboard.notices.loadingSource.replace("%{resource}", "DatasetMetadataRecord"),
    );
  });

  it("answers a read which is out without inventing a row", () => {
    state.sources = [
      stateOf("ServiceAlert", "loading"),
      stateOf("CatalogueService", "loading"),
      stateOf("DatasetMetadataRecord", "loading"),
      stateOf("ServiceMetadataRecord", "loading"),
    ];
    renderCard();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    // not one row is answered while the sources are out - the card never shows
    // a table of rows it did not read
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("row")).toHaveLength(0);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("keeps a failed read, an empty window and an unreadable deployment apart", () => {
    state.sources = [
      stateOf("ServiceAlert", "error"),
      stateOf("CatalogueService", "unsupported"),
      stateOf("DatasetMetadataRecord", "unsupported"),
      stateOf("ServiceMetadataRecord", "unsupported"),
    ];
    const failed = renderCard();
    expect(failed.getByRole("alert")).toHaveTextContent(en.dashboard.notices.loadError);
    // the sources which did not answer are named one by one, so the card never
    // reads as a deployment whose notices of that kind do not exist
    // the resources are named with the words of the resource registry, not with
    // the JSON:API type, where the registry knows them
    expect(failed.getAllByRole("status").map((node) => node.textContent)).toEqual([
      en.dashboard.notices.errorSource.replace("%{resource}", en.resources.ServiceAlert.name),
      en.dashboard.notices.unsupportedSource.replace("%{resource}", en.resources.CatalogueService.plural),
      en.dashboard.notices.unsupportedSource.replace("%{resource}", "DatasetMetadataRecord"),
      en.dashboard.notices.unsupportedSource.replace("%{resource}", "ServiceMetadataRecord"),
    ]);
    failed.unmount();

    state.sources = [
      answered("ServiceAlert", [], 0),
      answered("CatalogueService", [], 0),
      answered("DatasetMetadataRecord", [], 0),
      answered("ServiceMetadataRecord", [], 0),
    ];
    const empty = renderCard();
    expect(empty.getByRole("status")).toHaveTextContent(en.dashboard.notices.empty);
    expect(empty.queryByRole("alert")).not.toBeInTheDocument();
    expect(empty.queryByRole("table")).not.toBeInTheDocument();
    // every source answered nothing: none of them is missing, so none is named
    expect(empty.getAllByRole("status")).toHaveLength(1);
    empty.unmount();

    state.sources = [
      stateOf("ServiceAlert", "unsupported"),
      stateOf("CatalogueService", "unsupported"),
    ];
    renderCard();
    expect(screen.getByRole("status")).toHaveTextContent(en.dashboard.notices.unsupported);
  });

  it("shows no card to a caller who may read none of the sources and never redirects", () => {
    state.sources = [
      stateOf("ServiceAlert", "forbidden"),
      stateOf("CatalogueService", "forbidden"),
      stateOf("DatasetMetadataRecord", "forbidden"),
      stateOf("ServiceMetadataRecord", "forbidden"),
    ];
    const { container } = renderCard();
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("says the bounded scope when the sources hold more notices than it shows", () => {
    const many = (source: string, count: number): NoticeRow[] =>
      Array.from({ length: count }, (_unused, index) => alertRow({
        id: `${source}-${index}`,
        source,
        occurredAt: new Date(NOW - index * 3600000).toISOString(),
      }));
    state.sources = [
      answered("ServiceAlert", many("ServiceAlert", 6), 40),
      answered("CatalogueService", many("CatalogueService", 6), 40),
      answered("DatasetMetadataRecord", many("DatasetMetadataRecord", 6), 40),
      answered("ServiceMetadataRecord", many("ServiceMetadataRecord", 6), 40),
    ];
    renderCard();
    expect(screen.getByRole("status")).toHaveTextContent(
      en.dashboard.notices.truncated.replace("%{rows}", "8"),
    );
    // the table stays compact however many notices the sources hold
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(9);
  });

  it("answers a row the api does not date with the word of the api, never with now", () => {
    state.sources = [answered("ServiceAlert", [alertRow({ id: "undated", occurredAt: null })])];
    renderCard();
    expect(screen.getByText(en.dashboard.notices.noTime)).toBeInTheDocument();
    expect(screen.queryByText(new Date(NOW).toLocaleString("en-GB"))).not.toBeInTheDocument();
  });

  it("leaves a kind the api invented neutral and keeps its category word", () => {
    state.sources = [answered("ServiceAlert", [
      alertRow({ kind: "critical", category: "geoportal_error", message: undefined }),
    ])];
    renderCard();
    // an unknown severity is neither green nor red, it is answered as it is
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText("geoportal_error")).toBeInTheDocument();
  });

  it("links only the changelogs the deployment answers and asks only permitted resources", () => {
    state.sources = [
      answered("ServiceAlert", [alertRow()]),
      answered("CatalogueService", [auditRow()]),
      stateOf("DatasetMetadataRecord", "unsupported"),
    ];
    renderCard(["CatalogueService", "DatasetMetadataRecord"]);
    expect(state.asked).toEqual(["CatalogueService", "DatasetMetadataRecord"]);
    expect(screen.getByRole("link", { name: /All changes to Catalogue Service/ }))
      .toHaveAttribute("href", "/CatalogueService/history");
    // the history route of a resource without a changelog is not registered, so
    // the table does not promise it
    expect(screen.queryByRole("link", { name: /Dataset Metadata Record/ }))
      .not.toBeInTheDocument();
  });

  it("offers no entrance the caller is refused or the deployment does not answer", () => {
    state.sources = [
      stateOf("ServiceAlert", "forbidden"),
      answered("CatalogueService", [auditRow()]),
      stateOf("DatasetMetadataRecord", "forbidden"),
    ];
    renderCard(["CatalogueService", "DatasetMetadataRecord"]);
    // a list which answers "access denied" is not promised as a link
    expect(screen.queryByRole("link", { name: en.serviceAlerts.viewAll }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Dataset Metadata Record/ }))
      .not.toBeInTheDocument();
    // the source which is readable keeps its own entrance
    expect(screen.getByRole("link", { name: /All changes to Catalogue Service/ }))
      .toHaveAttribute("href", "/CatalogueService/history");
  });

  it("reads the window, the moments and the kinds in the locale of the screen", () => {
    state.locale = "de";
    // every word the card answers in German must exist in the German catalog,
    // a missing one would otherwise render its own key and still answer the card
    for (const key of [
      "dashboard.notices.title", "dashboard.notices.columns.time",
      "serviceAlerts.warning", "historyList.created", "historyList.noFieldChanges",
    ]) expect(lookup(key)).not.toBe(key);
    state.sources = [
      answered("ServiceAlert", [alertRow({ kind: "warning", category: "update_failed", message: "update_failed" })]),
      answered("DatasetMetadataRecord", [auditRow({ source: "DatasetMetadataRecord", kind: "created", delta: undefined })]),
    ];
    renderCard();
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      lookup("dashboard.notices.title"),
    );
    expect(screen.getByRole("columnheader", { name: lookup("dashboard.notices.columns.time") }))
      .toBeInTheDocument();
    expect(screen.getByText(/26\. Nov\., 09:00/)).toBeInTheDocument();
    expect(screen.getByText(lookup("serviceAlerts.warning"))).toBeInTheDocument();
    expect(screen.getByText(lookup("historyList.created"))).toBeInTheDocument();
    expect(screen.getByText(/20\. Nov\. 2026/)).toBeInTheDocument();
    // the row without a field change says that, it does not repeat its type
    expect(screen.getByText(lookup("historyList.noFieldChanges"))).toBeInTheDocument();
  });
});
