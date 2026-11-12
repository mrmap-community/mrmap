import { AdminContext, testDataProvider, type RaRecord } from "react-admin";

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ShowCatalogueServiceUpdateJob from "./ShowCatalogueServiceUpdateJob";

const cswJob: RaRecord = {
  id: 17,
  status: "Review required",
  statusCode: 2,
  dateCreated: "2026-11-01T08:00:00Z",
  doneAt: null,
  service: { id: 3, title: "Kataster-Portal" },
};

const renderJob = (
  job: RaRecord,
  providerOptions: Parameters<typeof testDataProvider>[0] = {},
) =>
  render(
    <AdminContext
      dataProvider={testDataProvider({
        getOne: vi.fn().mockResolvedValue({ data: job }),
        getList: vi.fn().mockResolvedValue({ data: [], total: 0 }),
        ...providerOptions,
      })}
    >
      <ShowCatalogueServiceUpdateJob
        id={job.id}
        resource="CatalogueServiceUpdateJob"
      />
    </AdminContext>,
  );

describe("ShowCatalogueServiceUpdateJob", () => {
  it("answers the waiting job with the wait it is in", async () => {
    renderJob(cswJob);
    expect(
      await screen.findByText(
        "resources.CatalogueServiceUpdateJob.reviewRequiredMessage",
      ),
    ).toBeInTheDocument();
    // the chip above the details and the state line of the details both name it
    expect(screen.getAllByText("Review required").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("alert").className).toContain(
      "MuiAlert-colorWarning",
    );
  });

  it("leads from the job to the catalogue it was made for", async () => {
    renderJob(cswJob);
    // the catalogue is named twice - once as the trail, once as the subject
    const links = await screen.findAllByRole("link", {
      name: "Kataster-Portal",
    });
    expect(links[0]).toHaveAttribute(
      "href",
      expect.stringContaining("/CatalogueService/3/show"),
    );
  });

  it("colours the state which ended with an error as an error", async () => {
    renderJob({
      ...cswJob,
      status: "Error",
      statusCode: 3,
      doneAt: "2026-11-01T08:05:00Z",
    });
    await screen.findByText("updateReview.failedMessage");
    expect(screen.getByRole("alert").className).toContain(
      "MuiAlert-colorError",
    );
  });

  it("says that a job which is not ended has no end yet", async () => {
    renderJob(cswJob);
    expect(
      await screen.findByText("resources.CatalogueServiceUpdateJob.running"),
    ).toBeInTheDocument();
  });

  it("reads the changes of the job from the history of the catalogue", async () => {
    const getList = vi.fn().mockResolvedValue({ data: [], total: 0 });
    renderJob({ ...cswJob, status: "Updated", statusCode: 5 }, { getList });
    await screen.findByText("updateReview.changesMade");
    await waitFor(() => expect(getList).toHaveBeenCalled());
    const [resource, params] = getList.mock.calls.at(-1) as [
      string,
      { filter: Record<string, string> },
    ];
    expect(resource).toBe("HistoricalCatalogueService");
    // the reason with which an update writes the history of its catalogue
    expect(params.filter.history_change_reason).toBe("updatejob_id: 17");
    expect(
      screen.getByText("updateReview.noRecordedChanges"),
    ).toBeInTheDocument();
  });
});
