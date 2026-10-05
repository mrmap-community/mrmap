import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AdminContext, testDataProvider } from "react-admin";
import { describe, expect, it, vi } from "vitest";
import CompletedUpdateJob from "./CompletedUpdateJob";

const job = {
  id: 2,
  statusCode: 5,
  status: "Updated",
  service: { id: "service", title: "DWD GeoServer WMS" },
  dateCreated: "2026-10-05T08:00:00Z",
  doneAt: "2026-10-05T08:01:00Z",
};
const records = [
  {
    id: "changed",
    title: "Temperature",
    identifier: "temp",
    historyType: "updated",
    historyDate: job.doneAt,
    delta: [
      { field: "abstract", old: "Old description", new: "New description" },
    ],
  },
  {
    id: "added",
    title: "Rain",
    identifier: "rain",
    abstract: "New layer",
    historyType: "updated",
    historyDate: job.doneAt,
    delta: null,
  },
  {
    id: "removed",
    title: "Legacy",
    identifier: "legacy",
    abstract: "Deleted layer",
    historyType: "deleted",
    historyDate: job.doneAt,
    delta: [],
  },
];
const renderJob = (
  getList = vi.fn().mockResolvedValue({ data: records, total: records.length }),
  record = job,
) => {
  render(
    <AdminContext dataProvider={testDataProvider({ getList })}>
      <CompletedUpdateJob job={record} />
    </AdminContext>,
  );
  return getList;
};
describe("completed update job", () => {
  it("requests each change category on the server and can return to All", async () => {
    const getList = renderJob();
    await screen.findByText("Temperature");
    for (const category of ["modified", "unchanged", "removed", "added"]) {
      fireEvent.mouseDown(
        screen.getByRole("combobox", { name: /updateReview.change/ }),
      );
      fireEvent.click(
        screen.getByRole("option", { name: `updateReview.${category}` }),
      );
      await waitFor(() =>
        expect(getList).toHaveBeenLastCalledWith(
          "HistoricalLayer",
          expect.objectContaining({
            filter: {
              history_change_reason: "updatejob_id: 2",
              service: "service",
              change_type: category,
            },
            pagination: { page: 1, perPage: 10 },
          }),
        ),
      );
    }
    fireEvent.mouseDown(
      screen.getByRole("combobox", { name: /updateReview.change/ }),
    );
    fireEvent.click(screen.getByRole("option", { name: "ra.action.clear_input_value" }));
    await waitFor(() =>
      expect(getList).toHaveBeenLastCalledWith(
        "HistoricalLayer",
        expect.objectContaining({
          filter: {
            history_change_reason: "updatejob_id: 2",
            service: "service",
          },
        }),
      ),
    );
  });
  it("loads only the job's service history and shows a read-only diff", async () => {
    const getList = renderJob();
    await screen.findByText("Temperature");
    expect(getList).toHaveBeenCalledWith(
      "HistoricalLayer",
      expect.objectContaining({
        filter: {
          history_change_reason: "updatejob_id: 2",
          service: "service",
        },
        pagination: { page: 1, perPage: 10 },
      }),
    );
    fireEvent.click(screen.getByText("Temperature"));
    expect(await screen.findByText("Old description")).toBeInTheDocument();
    expect(screen.getByText("New description")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "updateReview.viewService" }),
    ).toHaveAttribute("href", "#/WebMapService/service/show");
  });
  it("shows promoted layers as added and deleted layers using snapshots", async () => {
    renderJob();
    await screen.findByText("Rain");
    expect(screen.getByText("updateReview.added")).toBeInTheDocument();
    expect(screen.getByText("updateReview.removed")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Rain"));
    expect(await screen.findByText("New layer")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Legacy"));
    expect(await screen.findByText("Deleted layer")).toBeInTheDocument();
  });
  it("shows an honest empty history message", async () => {
    renderJob(vi.fn().mockResolvedValue({ data: [], total: 0 }));
    expect(
      await screen.findByText("updateReview.noRecordedChanges"),
    ).toBeInTheDocument();
  });
  it("shows a history load failure separately from completion", async () => {
    renderJob(vi.fn().mockRejectedValue(new Error("Offline")));
    expect(
      await screen.findByText(
        "updateReview.historyLoadError",
        {},
        { timeout: 10000 },
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("updateReview.completedTitle")).toBeInTheDocument();
  });
  it("does not label failed jobs successful", async () => {
    renderJob(vi.fn().mockResolvedValue({ data: [], total: 0 }), {
      ...job,
      statusCode: 3,
      status: "Error",
    });
    expect(screen.getByText("updateReview.failedTitle")).toBeInTheDocument();
    await screen.findByText("updateReview.noRecordedChanges");
  });
});
