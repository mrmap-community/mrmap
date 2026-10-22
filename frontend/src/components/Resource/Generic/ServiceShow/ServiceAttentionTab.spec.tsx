import type { ReactNode } from "react";
import {
  useRecordContext,
  useResourceContext,
  useResourceDefinitions,
} from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ServiceAttentionTab from "./ServiceAttentionTab";

import "@testing-library/jest-dom/vitest";

vi.mock("react-admin", () => ({
  BasenameContextProvider: ({ children }: { children: ReactNode }) => (
    <>{children}</>
  ),
  DateField: ({ source }: { source: string }) => <span>{source}</span>,
  ShowButton: ({
    resource,
    record,
    label,
  }: {
    resource: string;
    record: { id: string | number };
    label: string;
  }) => (
    <a href={`#/${resource}/${record.id}/show`}>
      {label.split(".").pop() ?? label}
    </a>
  ),
  useRecordContext: vi.fn(),
  useRefresh: () => () => undefined,
  useResourceContext: vi.fn(),
  useResourceDefinitions: vi.fn(),
  useTranslate: () => (key: string) => key.split(".").pop() ?? key,
}));

/** the kinds of records this deployment has a screen to show */
const SCREENS = [
  "WebMapServiceMonitoringRun",
  "WebFeatureServiceMonitoringRun",
  "WebFeatureServiceUpdateJob",
  "HarvestingJob",
];

beforeEach(() => {
  vi.mocked(useRecordContext, { partial: true }).mockReturnValue(undefined);
  vi.mocked(useResourceContext, { partial: true }).mockReturnValue(
    "WebMapService",
  );
  vi.mocked(useResourceDefinitions, { partial: true }).mockReturnValue(
    Object.fromEntries(
      SCREENS.map((resource) => [resource, { name: resource, hasShow: true }]),
    ),
  );
});

const renderTabWith = (
  record: Record<string, unknown>,
  resource = "WebMapService",
) => {
  vi.mocked(useRecordContext, { partial: true }).mockReturnValue(record);
  vi.mocked(useResourceContext, { partial: true }).mockReturnValue(resource);
  render(<ServiceAttentionTab />);
};

const links = () =>
  screen.queryAllByRole("link").map((link) => link.getAttribute("href"));

describe("attention of a service", () => {
  it("asks for nothing when the service needs nothing to do", () => {
    renderTabWith({ id: "wms-1", hasAlert: false });
    expect(screen.getByText("none")).toBeInTheDocument();
    expect(screen.queryByText("monitoringFailed")).not.toBeInTheDocument();
  });

  it("lists the state which needs attention with the time it appeared at", () => {
    renderTabWith({
      id: "wms-1",
      hasAlert: true,
      monitoringFailed: true,
      monitoringFailedAt: "2026-10-13T10:00:00Z",
    });
    expect(screen.getByText("monitoringFailed")).toBeInTheDocument();
    expect(screen.getByText("monitoringFailedAt")).toBeInTheDocument();
    // the date of a failing monitoring is the end of the run which found the
    // state and not the point in time the service began to hurt
    expect(screen.getByText("lastRunDone")).toBeInTheDocument();
    expect(screen.queryByText("updateFailed")).not.toBeInTheDocument();
  });

  it("lists the errors of a service before its warnings", () => {
    renderTabWith({
      id: "wms-1",
      hasAlert: true,
      updateReviewRequired: true,
      updateReviewRequiredAt: "2026-10-13T11:00:00Z",
      monitoringFailed: true,
      monitoringFailedAt: "2026-10-13T10:00:00Z",
    });
    const alerts = screen.getAllByRole("alert");
    expect(alerts.map((alert) => alert.textContent)).toEqual([
      expect.stringContaining("monitoringFailed"),
      expect.stringContaining("updateReviewRequired"),
    ]);
  });

  it("lists the state of the harvesting of a catalogue", () => {
    renderTabWith(
      {
        id: "csw-1",
        hasAlert: true,
        harvestIncomplete: true,
        harvestFailedAt: "2026-10-13T09:00:00Z",
      },
      "CatalogueService",
    );
    expect(screen.getByText("harvestIncomplete")).toBeInTheDocument();
    expect(screen.getByText("harvestFailedAt")).toBeInTheDocument();
  });

  it("asks for a state which has no time to answer", () => {
    renderTabWith({ id: "wms-1", hasAlert: true, updateFailed: true });
    expect(screen.getByText("updateFailed")).toBeInTheDocument();
    expect(screen.queryByText("monitoringFailedAt")).not.toBeInTheDocument();
    expect(screen.queryByText("updateFailedAt")).not.toBeInTheDocument();
  });
});

describe("the way to the record which decided an alert", () => {
  it("links a failing run to the screen of the run of its kind", () => {
    renderTabWith(
      {
        id: "wfs-1",
        hasAlert: true,
        monitoringFailed: true,
        monitoringFailedRun: "run-7",
      },
      "WebFeatureService",
    );
    expect(links()).toEqual(["#/WebFeatureServiceMonitoringRun/run-7/show"]);
  });

  it("links the harvesting of a catalogue to the job which ran it", () => {
    renderTabWith(
      {
        id: "csw-1",
        hasAlert: true,
        harvestIncomplete: true,
        harvestJob: 12,
      },
      "CatalogueService",
    );
    // a harvesting job is a resource of its own and not named after the service
    expect(links()).toEqual(["#/HarvestingJob/12/show"]);
  });

  it("asks about a state which no record decides at the service", () => {
    // an update which waits only because a candidate of it dangles has no job
    // to decide about it
    renderTabWith({ id: "wms-1", hasAlert: true, updateReviewRequired: true });
    expect(screen.getByText("noRecord")).toBeInTheDocument();
    expect(links()).toEqual([]);
  });

  it("asks about a record this deployment has no screen for", () => {
    // the update of a catalogue has no screen of its own to show a job at
    renderTabWith(
      {
        id: "csw-1",
        hasAlert: true,
        updateReviewRequired: true,
        updateReviewJob: 3,
      },
      "CatalogueService",
    );
    expect(screen.getByText("noRecord")).toBeInTheDocument();
    expect(links()).toEqual([]);
  });
});
