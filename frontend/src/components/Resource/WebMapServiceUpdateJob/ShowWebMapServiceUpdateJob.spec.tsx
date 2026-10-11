import { fireEvent, render, screen, within } from "@testing-library/react";
import { type ReactNode } from "react";
import { AdminContext, type RaRecord } from "react-admin";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ShowWebMapServiceUpdate } from "./ShowWebMapServiceUpdateJob";
const { job, current, incoming, refetch, queryState } = vi.hoisted(() => ({
  job: {
    id: 2,
    doneAt: null as string | null,
    statusCode: 2,
    service: { id: "service" },
    updateCandidate: { id: "candidate" },
    mappings: [
      { id: 1, newLayer: { id: 101 }, isConfirmed: false },
      {
        id: 2,
        newLayer: { id: 102 },
        oldLayer: { id: 201 },
        isConfirmed: false,
        delta: [
          { field: "abstract", old: "Old description", new: "New description" },
        ],
      },
      {
        id: 3,
        newLayer: { id: 103 },
        oldLayer: { id: 202 },
        isConfirmed: true,
      },
    ],
  },
  current: {
    id: "service",
    title: "DWD GeoServer WMS",
    layers: [
      { id: 201, title: "Previous rain" },
      { id: 202, title: "Places" },
    ],
  },
  incoming: {
    id: "candidate",
    layers: [
      { id: 101, title: "New rain" },
      { id: 102, title: "Updated rain" },
      { id: 103, title: "Places" },
    ],
  },
  refetch: vi.fn(),
  queryState: { error: null as Error | null },
}));
vi.mock("react-admin", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-admin")>()),
  Show: ({ children }: { children: ReactNode }) => <>{children}</>,
  useRecordContext: () => job,
  useShowContext: () => ({ refetch }),
  useGetOne: (_resource: string, { id }: { id: string }) => ({
    data: id === "candidate" ? incoming : current,
    isPending: false,
    error: queryState.error,
  }),
}));
vi.mock("../WebMapService/TreeView/WmsTreeView", () => ({
  default: () => <div>Layer tree</div>,
}));
vi.mock("./CompletedUpdateJob", () => ({
  default: () => <div>Completed job summary</div>,
}));
vi.mock("./EditLayerMapping", () => ({
  EditLayerMapping: ({
    mapping,
    mutationOptions,
  }: {
    mapping: RaRecord;
    mutationOptions: { onSuccess: () => void };
  }) => (
    <button onClick={mutationOptions.onSuccess}>
      Save mapping {mapping.id}
    </button>
  ),
}));
beforeEach(() => {
  queryState.error = null;
  job.doneAt = null;
  job.statusCode = 2;
  window.history.replaceState(null, "", window.location.pathname);
});
const renderReview = () =>
  render(
    <AdminContext>
      <ShowWebMapServiceUpdate />
    </AdminContext>,
  );
describe("update job review", () => {
  it("replaces review controls with the completed summary", () => {
    job.doneAt = "2026-10-05T08:01:00Z";
    job.statusCode = 5;
    renderReview();
    expect(screen.getByText("Completed job summary")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.queryByText("Layer tree")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Save mapping/ }),
    ).not.toBeInTheDocument();
  });
  it("shows a load error without offering an incomplete review", () => {
    queryState.error = new Error("Offline");
    renderReview();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "updateReview.loadError",
    );
    expect(
      screen.queryByRole("button", { name: /Save mapping/ }),
    ).not.toBeInTheDocument();
  });
  it("shows pending changes and progress, with confirmed changes available under All", () => {
    renderReview();
    expect(
      Number(screen.getByRole("progressbar").getAttribute("aria-valuenow")),
    ).toBeCloseTo(100 / 3);
    expect(screen.getByText("updateReview.noMatch")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Places/ }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "updateReview.all" }));
    expect(screen.getByRole("button", { name: /Places/ })).toBeInTheDocument();
  });
  it("selects numeric layer IDs and compares the selected mapping", () => {
    renderReview();
    fireEvent.click(screen.getByRole("button", { name: /Updated rain/ }));
    expect(
      screen.getByRole("button", { name: "Save mapping 2" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Previous rain")).toBeInTheDocument();
    expect(screen.getByText("Old description")).toBeInTheDocument();
    expect(screen.getByText("New description")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save mapping 2" }));
    expect(refetch).toHaveBeenCalled();
  });
  it("searches the change list and shows an empty result", () => {
    renderReview();
    fireEvent.change(
      screen.getByRole("textbox", { name: "updateReview.searchChanges" }),
      { target: { value: "updated" } },
    );
    const list = screen.getByRole("list", { name: "updateReview.changes" });
    expect(within(list).queryByText("New rain")).not.toBeInTheDocument();
    expect(within(list).getByText("Updated rain")).toBeInTheDocument();
    fireEvent.change(
      screen.getByRole("textbox", { name: "updateReview.searchChanges" }),
      { target: { value: "absent" } },
    );
    expect(screen.getByText("updateReview.noChanges")).toBeInTheDocument();
  });
});
