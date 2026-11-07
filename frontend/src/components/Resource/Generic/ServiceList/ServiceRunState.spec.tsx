import {
  AdminContext,
  RecordContextProvider,
  ResourceDefinitionContextProvider,
} from "react-admin";

import { render, screen } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it } from "vitest";

import en from "../../../../i18n/en";
import ServiceRunState, { type ServiceRunStateProps } from "./ServiceRunState";

/** a moment the given days before now - the column answers relative distances */
const daysAgo = (days: number) =>
  new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

const UPDATE_FLAGS = ["updateFailed", "updateReviewRequired"];
const HARVEST_FLAGS = ["harvestAborted", "harvestIncomplete"];

const RUNNING_HARVEST = {
  source: "runningHarvestingJob",
  resource: "HarvestingJob",
  label: "serviceAttention.records.HarvestingJob",
};

/** the column of the named kind of run, inside the row of the given service */
const renderColumn = (
  props: Pick<ServiceRunStateProps, "flags" | "running">,
  service: Record<string, unknown>,
) =>
  render(
    <AdminContext i18nProvider={polyglotI18nProvider(() => en, "en")}>
      <ResourceDefinitionContextProvider definitions={{
        HarvestingJob: { name: "HarvestingJob", hasShow: true },
      }}>
        <RecordContextProvider value={{ id: "s-1", ...service }}>
          <ServiceRunState locales="en" {...props} />
        </RecordContextProvider>
      </ResourceDefinitionContextProvider>
    </AdminContext>,
  );

describe("ServiceRunState", () => {
  it("answers the states of its kind of run with their moment from the row", () => {
    renderColumn(
      { flags: UPDATE_FLAGS },
      {
        updateFailed: true,
        updateFailedAt: daysAgo(3),
        updateReviewRequired: true,
        updateReviewRequiredAt: daysAgo(2),
      },
    );
    expect(screen.getByText("Update failed")).toBeInTheDocument();
    expect(screen.getByText("3 days ago")).toBeInTheDocument();
    expect(screen.getByText("Review required")).toBeInTheDocument();
    expect(screen.getByText("2 days ago")).toBeInTheDocument();
  });

  it("keeps the states of the harvesting out of the column of the updates", () => {
    const service = { harvestAborted: true, harvestFailedAt: daysAgo(1) };
    const { unmount } = renderColumn({ flags: UPDATE_FLAGS }, service);
    // a row which answers nothing of the updates says so instead of staying blank
    expect(screen.getByText("Nothing reported")).toBeInTheDocument();
    unmount();
    // the same row answered by the column of the harvesting, which a catalogue
    // answers - with the shared moment of a badly ended harvesting
    renderColumn({ flags: HARVEST_FLAGS }, service);
    expect(screen.getByText("Harvesting aborted")).toBeInTheDocument();
    expect(screen.getByText("yesterday")).toBeInTheDocument();
  });

  it("asks nothing per row: an unfinished row is answered by its own attributes", () => {
    renderColumn({ flags: HARVEST_FLAGS, running: RUNNING_HARVEST }, {
      runningHarvestingJob: { id: "hj-9" },
    });
    // the running harvesting is the one the row names, led to by the row itself
    expect(screen.getByRole("link", { name: "Show the harvesting" })).toHaveAttribute(
      "href", expect.stringContaining("HarvestingJob/hj-9/show"),
    );
    expect(screen.queryByText("Nothing reported")).toBeNull();
  });

  it("says that a row answers nothing, which is no health", () => {
    renderColumn({ flags: HARVEST_FLAGS, running: RUNNING_HARVEST }, {
      hasAlert: false,
    });
    expect(screen.getByText("Nothing reported")).toBeInTheDocument();
  });
});
