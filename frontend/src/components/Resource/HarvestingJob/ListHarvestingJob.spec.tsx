import {
  AdminContext,
  Datagrid,
  ListContextProvider,
  ResourceContextProvider,
  ResourceDefinitionContextProvider,
  ShowButton,
  WrapperField,
  testDataProvider,
  useList,
} from "react-admin";

import { render, screen, waitFor, within } from "@testing-library/react";
import { snakeCase } from "lodash";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi } from "vitest";

import en from "../../../i18n/en";
import defaultRecordRepresentation from "../defaultRecordRepresentation";
import { LIST_FIELDS, RUN_COLUMNS } from "./ListHarvestingJob";

import "@testing-library/jest-dom/vitest";

const runs = [
  {
    id: "41",
    service: { id: "csw-1" },
    phase: 3,
    phaseLabel: "Records to db",
    dateCreated: "2026-11-05T13:00:00Z",
    doneAt: null,
    totalRecords: 1284,
    doneSteps: 30,
    totalSteps: 48,
    progress: 62.4,
    recordsPerMinute: null,
    maxStepSize: 150,
    unhandledRecordsCount: 1284,
    importErrorCount: 3,
  },
  {
    id: "39",
    service: { id: "csw-2" },
    phase: 1,
    phaseLabel: "Get total records count",
    dateCreated: null,
    doneAt: null,
    totalRecords: null,
    doneSteps: null,
    totalSteps: null,
    progress: 0,
    recordsPerMinute: null,
    maxStepSize: null,
    unhandledRecordsCount: 0,
    importErrorCount: 0,
  },
  {
    id: "37",
    service: { id: "csw-1" },
    phase: 4,
    phaseLabel: "Completed",
    dateCreated: "2026-11-05T08:00:00Z",
    doneAt: "2026-11-05T08:48:03Z",
    totalRecords: 411704,
    doneSteps: 2062,
    totalSteps: 2062,
    progress: 100,
    recordsPerMinute: 1480.2,
    maxStepSize: 200,
    unhandledRecordsCount: 0,
    importErrorCount: 0,
  },
];

const Columns = () => {
  const list = useList({ data: runs, sort: { field: "doneAt", order: "DESC" } });
  return (
    <ListContextProvider value={list}>
      <Datagrid bulkActionButtons={false} rowClick={false}>
        {RUN_COLUMNS}
        <WrapperField label="ra.list.actions">
          <ShowButton />
        </WrapperField>
      </Datagrid>
    </ListContextProvider>
  );
};

// the reference field asks the catalogues of its rows in one getMany
const getMany = vi.fn();
getMany.mockImplementation((_resource: string, { ids }: { ids: string[] }) =>
  Promise.resolve({
    data: ids.map((id) => ({
      id,
      stringRepresentation: id === "csw-1" ? "GDI-BW" : id,
    })),
  }),
);

const renderColumns = () =>
  render(
    <AdminContext
      i18nProvider={polyglotI18nProvider(() => en, "en")}
      dataProvider={testDataProvider({ getMany })}
    >
      {/* the app gives every resource its default representation (#1045) */}
      <ResourceDefinitionContextProvider
        definitions={{
          CatalogueService: {
            name: "CatalogueService",
            recordRepresentation: defaultRecordRepresentation,
          },
        }}
      >
        <ResourceContextProvider value="HarvestingJob">
          <Columns />
        </ResourceContextProvider>
      </ResourceDefinitionContextProvider>
    </AdminContext>,
  );

// the caption's parts are sibling text nodes, so a partial match finds the row
const row = async (text: RegExp) =>
  (await screen.findByText(text)).closest("tr")!;

describe("the list of harvesting runs", () => {
  it("answers one column per question a row of a run asks", async () => {
    renderColumns();
    await waitFor(() =>
      expect(screen.getAllByRole("columnheader").map(cell => cell.textContent)).toEqual([
        "Catalogue · run",
        "Phase",
        "Progress",
        "Throughput",
        "Time",
        "Records",
        "Actions",
      ]),
    );
  });

  it("names the catalogue, the run and the step size it harvests with", async () => {
    renderColumns();
    const run = await row(/Run #41/);
    expect(await within(run).findByText("GDI-BW")).toBeInTheDocument();
    expect(run.textContent).toContain("Run #41 · page size 150");
    expect(within(run).getByText("1,284 awaiting import")).toBeInTheDocument();
    expect(within(run).getByText("3 import errors")).toBeInTheDocument();
  });

  it("tells how far a working run is and that it measured no throughput yet", async () => {
    renderColumns();
    const run = await row(/Run #41/);
    expect(within(run).getByText("62.40%")).toBeInTheDocument();
    expect(within(run).getByText("30 of 48 steps")).toBeInTheDocument();
    expect(within(run).getByText("—")).toBeInTheDocument();
    expect(within(run).getByText("no throughput measured")).toBeInTheDocument();
    // a run which is still working has no time left to tell (#1071)
    expect(within(run).getByText("no estimate")).toBeInTheDocument();
  });

  it("says that a run which is still counting records knows nothing", async () => {
    renderColumns();
    const run = await row(/Run #39/);
    expect(within(run).getByText("counting")).toBeInTheDocument();
    expect(within(run).getAllByText("total unknown").length).toBeGreaterThan(0);
    expect(within(run).getByText("no estimate: the total is unknown")).toBeInTheDocument();
    expect(within(run).getByText("Not recorded")).toBeInTheDocument();
    // nothing measured is never drawn as a zero
    expect(within(run).queryByText("0.00%")).not.toBeInTheDocument();
    expect(within(run).queryByText("0 records")).not.toBeInTheDocument();
  });

  it("tells what a run which ended brought and how fast it was", async () => {
    renderColumns();
    const run = await row(/Run #37/);
    expect(within(run).getByText("411,704 records")).toBeInTheDocument();
    expect(within(run).getByText("1,480 rec / min")).toBeInTheDocument();
    expect(within(run).getByText("measured at page size 200")).toBeInTheDocument();
    expect(within(run).getByText(/^ended /)).toBeInTheDocument();
    expect(within(run).queryByText("awaiting import")).not.toBeInTheDocument();
  });

  it("asks the api for exactly the attributes its columns read", () => {
    const sources = RUN_COLUMNS.map(
      (column) => snakeCase((column.props as { source: string }).source),
    );
    for (const source of sources) {
      expect(LIST_FIELDS).toContain(source);
    }
    expect(LIST_FIELDS).not.toContain("fetch_record_duration");
  });

  it("keeps the columns of the screen closed to the column chooser", () => {
    const labels = RUN_COLUMNS.map(
      (column) => (column.props as { label: string }).label,
    );
    expect(labels).toEqual([
      "harvestRun.list.runHeading",
      "harvestRun.list.phaseHeading",
      "harvestRun.list.progressHeading",
      "harvestRun.list.throughputHeading",
      "harvestRun.list.timeHeading",
      "harvestRun.list.recordsHeading",
    ]);
  });
});
