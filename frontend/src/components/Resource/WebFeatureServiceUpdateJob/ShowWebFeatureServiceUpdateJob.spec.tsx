import { type ReactNode } from "react";
import { AdminContext, type RaRecord } from "react-admin";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ShowWebFeatureServiceUpdateJob from "./ShowWebFeatureServiceUpdateJob";
const {
  job,
  current,
  incoming,
  refetch,
  queryState,
  getOne,
  completed,
  editor,
} = vi.hoisted(() => ({
  job: {
    id: 2,
    doneAt: null as string | null,
    statusCode: 2,
    service: { id: "service" },
    updateCandidate: { id: "candidate" },
    mappings: [
      { id: 1, newFeaturetype: { id: 101 }, isConfirmed: false },
      {
        id: 2,
        newFeaturetype: { id: 102 },
        oldFeaturetype: { id: 201 },
        isConfirmed: false,
      },
      {
        id: 3,
        newFeaturetype: { id: 103 },
        oldFeaturetype: { id: 202 },
        isConfirmed: true,
      },
    ],
  },
  current: {
    id: "service",
    title: "DWD GeoServer WFS",
    featuretypes: [
      { id: 201, title: "Previous rain", abstract: "Old description" },
      { id: 202, title: "Places" },
    ],
  },
  incoming: {
    id: "candidate",
    featuretypes: [
      { id: 101, title: "New rain" },
      { id: 102, title: "Updated rain", abstract: "New description" },
      { id: 103, title: "Places" },
    ],
  },
  getOne: vi.fn(),
  completed: vi.fn(),
  editor: vi.fn(),
  refetch: vi.fn(),
  queryState: { error: null as Error | null },
}));
vi.mock("react-admin", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-admin")>()),
  Show: ({ children }: { children: ReactNode }) => <>{children}</>,
  useRecordContext: () => job,
  useShowContext: () => ({ refetch }),
  useGetOne: (resource: string, params: { id: string }, options: unknown) => {
    getOne(resource, params, options);
    return {
      data: params.id === "candidate" ? incoming : current,
      isPending: false,
      error: queryState.error,
    };
  },
}));
vi.mock("../WebMapService/TreeView/WmsTreeView", () => ({
  default: () => {
    throw new Error("WFS must not render a WMS tree");
  },
}));
vi.mock("../WebMapServiceUpdateJob/CompletedUpdateJob", () => ({
  default: (props: unknown) => {
    completed(props);
    return <div>Completed job summary</div>;
  },
}));
vi.mock("../WebMapServiceUpdateJob/EditLayerMapping", () => ({
  EditLayerMapping: ({
    mapping,
    mutationOptions,
    ...props
  }: {
    config: { mappingResource: string };
    mapping: RaRecord;
    mutationOptions: { onSuccess: () => void };
  }) => {
    editor({ mapping, ...props });
    return (
      <button onClick={mutationOptions.onSuccess}>
        Save mapping {mapping.id}
      </button>
    );
  },
}));
beforeEach(() => {
  vi.clearAllMocks();
  queryState.error = null;
  job.doneAt = null;
  job.statusCode = 2;
  window.history.replaceState(null, "", window.location.pathname);
});
const renderReview = () =>
  render(
    <AdminContext>
      <ShowWebFeatureServiceUpdateJob />
    </AdminContext>,
  );
describe("WFS update job review", () => {
  it.each([0, 3, 5])(
    "replaces review controls for terminal status %s",
    (status) => {
      job.doneAt = "2026-10-05T08:01:00Z";
      job.statusCode = status;
      renderReview();
      expect(screen.getByText("Completed job summary")).toBeInTheDocument();
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
      expect(completed).toHaveBeenCalledWith(
        expect.objectContaining({
          config: expect.objectContaining({
            historyResource: "HistoricalFeatureType",
          }),
        }),
      );
      expect(getOne.mock.calls.every((call) => !call[2].enabled)).toBe(true);
      expect(screen.queryByText("Layer tree")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Save mapping/ }),
      ).not.toBeInTheDocument();
    },
  );
  it("shows a load error without offering an incomplete review", () => {
    queryState.error = new Error("Offline");
    renderReview();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "wfsUpdateReview.loadError",
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
    expect(screen.getByText("wfsUpdateReview.noMatch")).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("list", { name: "updateReview.changes" }),
      ).queryByRole("button", { name: /Places/ }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "wfsUpdateReview.all" }),
    );
    expect(
      within(
        screen.getByRole("list", { name: "updateReview.changes" }),
      ).getByRole("button", { name: /Places/ }),
    ).toBeInTheDocument();
  });
  it("selects numeric feature type IDs and compares the selected mapping", () => {
    renderReview();
    fireEvent.click(
      within(
        screen.getByRole("list", { name: "updateReview.changes" }),
      ).getByRole("button", { name: /Updated rain/ }),
    );
    expect(
      screen.getByRole("button", { name: "Save mapping 2" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Previous rain")).toBeInTheDocument();
    expect(screen.getByText("Old description")).toBeInTheDocument();
    expect(screen.getByText("New description")).toBeInTheDocument();
    expect(editor).toHaveBeenLastCalledWith(
      expect.objectContaining({
        config: expect.objectContaining({
          mappingResource: "FeatureTypeMapping",
        }),
        mapping: expect.objectContaining({ id: 2 }),
      }),
    );
    expect(getOne).toHaveBeenCalledWith(
      "WebFeatureService",
      { id: "candidate", meta: { jsonApiParams: { include: "featuretypes" } } },
      { enabled: true },
    );
    expect(getOne).toHaveBeenCalledWith(
      "WebFeatureService",
      { id: "service", meta: { jsonApiParams: { include: "featuretypes" } } },
      { enabled: true },
    );
    fireEvent.click(screen.getByRole("button", { name: "Save mapping 2" }));
    expect(refetch).toHaveBeenCalled();
  });
  it("searches incoming feature types and selects their mappings", () => {
    renderReview();
    const list = within(
      screen.getByRole("list", { name: "wfsUpdateReview.tree" }),
    );
    fireEvent.change(
      screen.getByRole("textbox", { name: "wfsUpdateReview.findLayer" }),
      { target: { value: "places" } },
    );
    // The selected item remains visible while searching, as in the WMS tree.
    expect(list.queryByText("Updated rain")).not.toBeInTheDocument();
    fireEvent.click(list.getByRole("button", { name: "Places" }));
    expect(
      screen.getByRole("button", { name: "Save mapping 3" }),
    ).toBeInTheDocument();
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
