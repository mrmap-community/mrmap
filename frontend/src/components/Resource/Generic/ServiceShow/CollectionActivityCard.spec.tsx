import type { ReactNode } from "react";
import type { RaRecord } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CollectionActivityCard, {
  CollectionRun,
} from "./CollectionActivityCard";

/** the answers of the two requests the card makes, keyed by resource */
const state = vi.hoisted(() => ({
  processes: [] as RaRecord[],
  processesError: null as Error | null,
  processesPending: false,
  references: [] as RaRecord[],
  referencesError: null as Error | null,
}));
/** every request the card made, so a test can read what it asked for */
const calls = vi.hoisted(() => ({
  list: [] as [string, Record<string, unknown>, unknown][],
}));
/** the record the mocked fields of the card read their values from */
const runContext = vi.hoisted(() => ({
  record: undefined as RaRecord | undefined,
}));
/**
 * The keys the card is allowed to ask for: an unknown key answers the fallback
 * it carries, which is how a phase the api reported as free text stays
 * readable (#1267) - the same rule the mocked translate of this screen applies.
 */
const TRANSLATED = vi.hoisted(() => [
  "backgroundActivity.process",
  "backgroundActivity.progress",
  "backgroundActivity.steps",
  "backgroundActivity.status.running",
  "backgroundActivity.status.completed",
  "backgroundActivity.status.failed",
  "backgroundActivity.jobCenter.processTypes.registering",
  "backgroundActivity.phases.collect_metadata_records",
  "backgroundActivity.phases.persist_service",
  "backgroundActivity.viewDetails",
  "collectionActivity.title",
  "collectionActivity.unreadable",
  "collectionActivity.loadError",
  "collectionActivity.noHistory",
  "collectionActivity.notPlanned",
  "collectionActivity.notCollected",
  "collectionActivity.nothingReferenced",
  "collectionActivity.planned",
  "collectionActivity.stored",
  "collectionActivity.failed",
  "collectionActivity.skipped",
  "collectionActivity.unresolved",
  "collectionActivity.describes",
  "collectionActivity.describesMore",
  "collectionActivity.viewReferences",
  "harvestingActivity.started",
]);

vi.mock("react-admin", () => ({
  useRecordContext: () => ({ id: "wms-1" }),
  useTranslate: () => (key: string, options?: Record<string, unknown>) => {
    const text = TRANSLATED.includes(key) ? key : ((options?._ as string) ?? key);
    return options?.count === undefined ? text : `${text}: ${options.count}`;
  },
  useCreatePath: () =>
    ({
      resource,
      id,
      type,
    }: {
      resource: string;
      id: string | number;
      type: string;
    }) => `/${resource}/${id}/${type}`,
  useGetList: (
    resource: string,
    params: Record<string, unknown>,
    options?: unknown,
  ) => {
    calls.list.push([resource, params, options]);
    return resource === "BackgroundProcess"
      ? {
          data: state.processes,
          total: state.processes.length,
          isPending: state.processesPending,
          error: state.processesError,
        }
      : {
          data: state.references,
          total: state.references.length,
          isPending: false,
          error: state.referencesError,
        };
  },
  useFieldValue: ({ source }: { source: string }) =>
    runContext.record?.[source] as unknown,
  RecordContextProvider: ({
    value,
    children,
  }: {
    value: RaRecord;
    children: ReactNode;
  }) => {
    runContext.record = value;
    return <>{children}</>;
  },
  Link: ({ to, children }: { to: string; children: ReactNode }) => (
    <a href={to}>{children}</a>
  ),
  Button: ({ to, label }: { to: string; label: string }) => (
    <a href={to}>{label}</a>
  ),
  DateField: ({
    source,
    emptyText,
  }: {
    source: string;
    emptyText?: string;
  }) => <span>{runContext.record?.[source] ?? emptyText}</span>,
  Loading: () => <span>loading</span>,
}));

beforeEach(() => {
  calls.list = [];
  state.processes = [];
  state.processesError = null;
  state.processesPending = false;
  state.references = [];
  state.referencesError = null;
  runContext.record = undefined;
});

/** the parameters of the request the card made for one resource */
const listCall = (resource: string) =>
  calls.list.find(([name]) => name === resource)?.[1] as {
    filter: Record<string, unknown>;
    sort: Record<string, string>;
    pagination: Record<string, number>;
    meta: { jsonApiParams: Record<string, string> };
  };

describe("collection activity card", () => {
  it("asks the registrations of this service and the references they keep, with stored numbers only", () => {
    render(<CollectionActivityCard />);
    const processes = listCall("BackgroundProcess");
    expect(processes.filter).toEqual({
      relatedId: "wms-1",
      processType: "registering",
    });
    expect(processes.sort).toEqual({ field: "dateCreated", order: "DESC" });
    expect(processes.pagination).toEqual({ page: 1, perPage: 3 });
    const fieldset =
      processes.meta.jsonApiParams["fields[BackgroundProcess]"];
    // every number on the card is one of these stored counters (#1259, #1263)
    expect(fieldset).toContain("references_total");
    expect(fieldset).toContain("references_stored");
    expect(fieldset).toContain("references_failed");
    expect(fieldset).toContain("references_skipped");
    // the statistics which #1037 measured while a large import writes stay off
    expect(fieldset).not.toContain("count");
    // the references are read by the lookups #1263 declares for this card
    const references = listCall("TemporaryMdMetadataFile");
    expect(references.filter).toEqual({ "backgroundProcess.in": "" });
    expect(references.pagination.perPage).toBe(25);
  });
  it("says a running registration has not planned its references, rather than inventing zeroes", () => {
    state.processes = [
      {
        id: 7,
        status: "running",
        state: "running",
        processType: "registering",
        phase: "download_capabilities",
        progress: 12,
        referencesTotal: null,
      },
    ];
    render(<CollectionActivityCard />);
    expect(
      screen.getByText("backgroundActivity.status.running"),
    ).toBeInTheDocument();
    // an error text reported as the phase stays readable as it was written
    expect(screen.getByText(/download_capabilities/)).toBeInTheDocument();
    expect(
      screen.getByText("collectionActivity.notPlanned"),
    ).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
  it("renders the stored outcome counters of a decided run and links the outcomes which kept a row", () => {
    state.processes = [
      {
        id: 8,
        status: "completed",
        state: "completed",
        processType: "registering",
        phase: "collect_metadata_records",
        doneAt: "2026-11-11T08:31:00Z",
        referencesTotal: 18,
        referencesStored: 12,
        referencesFailed: 3,
        referencesSkipped: 3,
      },
    ];
    render(<CollectionActivityCard />);
    expect(
      screen.getByText("backgroundActivity.status.completed"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/backgroundActivity\.phases\.collect_metadata_records/),
    ).toBeInTheDocument();
    for (const key of ["planned", "stored", "failed", "skipped"]) {
      expect(
        screen.getByText(`collectionActivity.${key}`),
      ).toBeInTheDocument();
    }
    // failed and skipped carry the same number here, so the counts are
    // asserted by their number of occurrences, not by a single lookup
    expect(screen.getAllByText("18")).toHaveLength(1);
    expect(screen.getAllByText("12")).toHaveLength(1);
    expect(screen.getAllByText("3")).toHaveLength(2);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "collectionActivity.unresolved: 6",
    );
    const links = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    // one link per outcome, into the per-reference list of #1265's data
    expect(links).toEqual(
      expect.arrayContaining([
        `/TemporaryMdMetadataFile/list?filter=${encodeURIComponent(
          JSON.stringify({ backgroundProcess: "8", state: "2" }),
        )}`,
        `/TemporaryMdMetadataFile/list?filter=${encodeURIComponent(
          JSON.stringify({ backgroundProcess: "8", "state.in": "0,1" }),
        )}`,
      ]),
    );
    // a stored reference left no row behind, so its number is not a link
    expect(links).not.toEqual(
      expect.arrayContaining([
        `/TemporaryMdMetadataFile/list?filter=${encodeURIComponent(
          JSON.stringify({ backgroundProcess: "8", state: "1" }),
        )}`,
      ]),
    );
  });
  it("says references of this kind were not collected for a decided run which never planned any", () => {
    state.processes = [
      {
        id: 9,
        status: "completed",
        state: "completed",
        processType: "registering",
        phase: "persist_service",
        referencesTotal: null,
        referencesStored: null,
      },
    ];
    render(<CollectionActivityCard />);
    expect(
      screen.getByText("collectionActivity.notCollected"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("collectionActivity.notPlanned"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("collectionActivity.stored")).not.toBeInTheDocument();
  });
  it("distinguishes a planned collection which found nothing from one which found nothing to ask", () => {
    state.processes = [
      {
        id: 10,
        status: "completed",
        state: "completed",
        processType: "registering",
        phase: "collect_metadata_records",
        referencesTotal: 0,
        referencesStored: 0,
      },
    ];
    render(<CollectionActivityCard />);
    expect(
      screen.getByText("collectionActivity.nothingReferenced"),
    ).toBeInTheDocument();
  });
  it("names the elements the retained references describe, every element once", () => {
    state.processes = [
      {
        id: 11,
        status: "failed",
        state: "failed",
        processType: "registering",
        phase: "an error occurred: connection reset",
        errorSummary: "connection reset",
        referencesTotal: 2,
        referencesStored: 0,
        referencesFailed: 2,
      },
    ];
    state.references = [
      {
        id: "a",
        backgroundProcess: { id: 11 },
        describedLayer: { id: "layer-1" },
        describedDisplay: "axiale Rohrleitungsnetz",
      },
      {
        id: "b",
        backgroundProcess: { id: 11 },
        describedLayer: { id: "layer-1" },
        describedDisplay: "axiale Rohrleitungsnetz",
      },
      {
        id: "c",
        backgroundProcess: { id: 11 },
        describedFeaturetype: { id: "ft-1" },
        describedDisplay: "Gewaesser",
      },
      // a row of another process is not this run's story
      {
        id: "d",
        backgroundProcess: { id: 12 },
        describedFeaturetype: { id: "ft-9" },
        describedDisplay: "andere Registrierung",
      },
    ];
    render(<CollectionActivityCard />);
    // a failed run shows the summary the task stored, not only its phase
    expect(screen.getByText("connection reset")).toBeInTheDocument();
    expect(
      screen.getByText("backgroundActivity.status.failed"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("axiale Rohrleitungsnetz")).toHaveLength(1);
    const elementLinks = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(elementLinks).toEqual(
      expect.arrayContaining(["/Layer/layer-1/show", "/FeatureType/ft-1/show"]),
    );
    expect(elementLinks).not.toContain("/FeatureType/ft-9/show");
  });
  it("keeps the counters and drops the links when the reference list is not readable", () => {
    state.processes = [
      {
        id: 13,
        status: "completed",
        state: "completed",
        processType: "registering",
        phase: "collect_metadata_records",
        referencesTotal: 4,
        referencesStored: 3,
        referencesFailed: 1,
      },
    ];
    state.references = [];
    state.referencesError = Object.assign(new Error("Forbidden"), {
      status: 403,
    });
    render(<CollectionActivityCard />);
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("collectionActivity.stored")).toBeInTheDocument();
    // the job itself stays readable - it was the references the caller may not
    // read, so only their links go away
    const links = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(links).toContain("/BackgroundProcess/13/show");
    expect(
      links.filter((href) => href?.startsWith("/TemporaryMdMetadataFile/list")),
    ).toEqual([]);
  });
  it("answers a neutral no retained history when the processes are purged, not a claim about a run", () => {
    state.processes = [];
    render(<CollectionActivityCard />);
    expect(screen.getByText("collectionActivity.noHistory")).toBeInTheDocument();
    expect(
      screen.getByText("collectionActivity.title"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("says the processes are not readable without a failed request", () => {
    state.processesError = Object.assign(new Error("Forbidden"), {
      status: 403,
    });
    render(<CollectionActivityCard />);
    expect(screen.getByText("collectionActivity.unreadable")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
  it("shows the alert of a load failure which is not about permission", () => {
    state.processesError = new Error("Offline");
    render(<CollectionActivityCard />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "collectionActivity.loadError",
    );
  });
});

describe("one registration run", () => {
  it("shows the steps the process measured and its start, and never a percentage for a total it does not know", () => {
    render(
      <CollectionRun
        process={{
          id: 1,
          status: "running",
          state: "running_indeterminate",
          processType: "registering",
          phase: "download_capabilities",
          progress: 0,
          totalSteps: null,
          doneSteps: 0,
          referencesTotal: null,
        }}
        rows={[]}
        linksAllowed
      />,
    );
    expect(screen.getByRole("progressbar")).not.toHaveAttribute(
      "aria-valuenow",
    );
    expect(screen.queryByText("backgroundActivity.steps")).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
